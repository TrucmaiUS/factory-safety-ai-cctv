import argparse
from pathlib import Path
from typing import Any

import cv2
import yaml

from src.perception.detection_types import DetectionBox
from src.perception.person_detector import PersonDetector
from src.perception.ppe_detector import PPEDetector, is_head
from src.configs.runtime_settings import pipeline_settings, tracking_settings
from src.safety.action_engine import ActionEngine
from src.safety.event_state_manager import EventStateManager
from src.safety.helmet_matcher import count_unmatched_heads, match_helmet_to_person
from src.safety.history_logger import HistoryLogger, write_person_status
from src.safety.rule_engine import RuleEngine
from src.safety.risk_scoring import decision_policy, load_risk_rules, score_event
from src.safety.simple_tracker import CentroidTracker, TrackState
from src.safety.track_state_manager import (
    PPE_HELMET,
    PPE_NO_HELMET,
    PPE_UNKNOWN,
    TrackStateManager,
)
from src.safety.zone_checker import ZoneChecker, is_point_inside_zone
from src.utils.atomic_io import replace_with_retry, unique_tmp_path
from src.visualization.overlay import render_overlay


ROOT = Path(__file__).resolve().parents[2]
VIDEO_SOURCES_PATH = ROOT / "src" / "configs" / "video_sources.yaml"
OUTPUT_VIDEO_DIR = ROOT / "outputs" / "demo_videos"
LIVE_DIR = ROOT / "outputs" / "live"
CAMERAS = ("camera_1", "camera_2", "camera_3")


def load_video_sources() -> dict[str, Any]:
    with VIDEO_SOURCES_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_video_source(camera_id: str) -> Path:
    config = load_video_sources()
    camera_config = config.get(camera_id)
    if not camera_config:
        raise KeyError(f"Camera '{camera_id}' not found in {VIDEO_SOURCES_PATH}")

    source = camera_config.get("source")
    if not source:
        raise KeyError(f"Camera '{camera_id}' has no source in {VIDEO_SOURCES_PATH}")

    video_path = ROOT / source
    if not video_path.exists():
        raise FileNotFoundError(f"Video source not found: {video_path}")

    return video_path


def camera_uses_zone(camera_id: str) -> bool:
    camera_config = load_video_sources().get(camera_id, {})
    required = camera_config.get("required_signals", []) or []
    return "inside_danger_zone" in required


def camera_uses_ppe(camera_id: str) -> bool:
    camera_config = load_video_sources().get(camera_id, {})
    return bool(camera_config.get("detectors", {}).get("ppe", False))


def open_video_writer(output_path: Path, fps: float, width: int, height: int) -> cv2.VideoWriter:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))
    if not writer.isOpened():
        raise RuntimeError(f"Cannot open video writer: {output_path}")
    return writer


def save_latest_frame_atomic(
    camera_id: str,
    frame,
    live_width: int | None = 960,
    jpeg_quality: int = 82,
) -> None:
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    output_frame = frame
    if live_width and live_width > 0 and frame.shape[1] > live_width:
        scale = live_width / frame.shape[1]
        output_frame = cv2.resize(
            frame,
            (live_width, int(frame.shape[0] * scale)),
            interpolation=cv2.INTER_AREA,
        )

    final_path = LIVE_DIR / f"{camera_id}_latest.jpg"
    tmp_path = unique_tmp_path(final_path, ".tmp.jpg")
    ok = cv2.imwrite(
        str(tmp_path),
        output_frame,
        [cv2.IMWRITE_JPEG_QUALITY, int(jpeg_quality)],
    )
    if ok:
        replace_with_retry(tmp_path, final_path)


def should_emit_alert(
    event_key: tuple[int | str | None, str],
    timestamp_seconds: float,
    last_alert_times: dict[tuple[int | str | None, str], float],
    cooldown_seconds: float,
) -> bool:
    last_time = last_alert_times.get(event_key)
    if last_time is not None and timestamp_seconds - last_time < cooldown_seconds:
        return False
    last_alert_times[event_key] = timestamp_seconds
    return True


def compact_helmet_state(state: dict[str, Any] | None) -> dict[str, Any] | None:
    if not state:
        return None
    return {
        "has_helmet": state.get("has_helmet"),
        "has_head": state.get("has_head"),
        "no_helmet": state.get("no_helmet"),
        "helmet_conf": state.get("helmet_conf"),
        "head_conf": state.get("head_conf"),
        "uncertain": state.get("uncertain"),
    }


def promote_ppe_visibility_warning(
    camera_id: str,
    risk: dict[str, Any],
    helmet_state: dict[str, Any] | None,
    ppe_warning_score: int,
) -> dict[str, Any]:
    if not camera_uses_ppe(camera_id) or not helmet_state:
        return risk
    if not helmet_state.get("has_head") or helmet_state.get("no_helmet"):
        return risk

    promoted = {
        **risk,
        "reasons": list(risk.get("reasons", [])),
        "actions": list(risk.get("actions", [])),
        "details": dict(risk.get("details", {})),
    }
    if "head_visible_ppe_warning" not in promoted["reasons"]:
        promoted["reasons"].append("head_visible_ppe_warning")
    promoted["risk_score"] = max(int(promoted.get("risk_score", 0)), int(ppe_warning_score))
    if promoted.get("severity") == "normal":
        promoted["severity"] = "warning"
    promoted["details"].update(
        {
            "ppe_warning": True,
            "ppe_warning_type": "head_visible_with_helmet" if helmet_state.get("has_helmet") else "head_visible",
            "decision_status": "WARNING",
        }
    )
    return promoted


def maybe_handle_action(
    camera_id: str,
    risk: dict[str, Any],
    timestamp_seconds: float,
    action_engine: ActionEngine,
    last_alert_times: dict[tuple[int | str | None, str], float],
    event_cooldown_sec: float,
    track: TrackState | None = None,
    zone_name: str | None = None,
    helmet_state: dict[str, Any] | None = None,
    bbox: DetectionBox | None = None,
    event_key: int | str | None = None,
    snapshot_frame=None,
    force_history: bool = False,
) -> None:
    if not force_history and ("save_history" not in risk.get("actions", []) or risk.get("severity") == "normal"):
        return

    key = (event_key if event_key is not None else (track.track_id if track else None), risk["severity"])
    if not should_emit_alert(key, timestamp_seconds, last_alert_times, event_cooldown_sec):
        return

    action_engine.handle_event(
        camera_id=camera_id,
        risk=risk,
        track=track,
        zone_name=zone_name,
        helmet_state=compact_helmet_state(helmet_state),
        bbox=bbox,
        snapshot_frame=snapshot_frame,
    )


def run_demo(
    camera_id: str,
    max_frames: int | None,
    save_video: bool,
    start_sec: float = 0.0,
    end_sec: float | None = None,
    realtime_logs: bool = False,
    snapshot_every: int | None = None,
    event_cooldown_sec: float | None = None,
    live_frame_width: int | None = None,
    inference_every: int | None = None,
    person_conf: float | None = None,
    ppe_conf: float | None = None,
    smoothing_window: int | None = None,
    no_helmet_confirm_frames: int | None = None,
    risk_alpha: float | None = None,
    alert_duration_sec: float | None = None,
    loop_video: bool | None = None,
) -> None:
    if camera_id not in CAMERAS:
        raise ValueError(f"Unsupported camera '{camera_id}'. Expected one of: {', '.join(CAMERAS)}")
    runtime = pipeline_settings()
    tracking = tracking_settings()
    if snapshot_every is None:
        snapshot_every = int(runtime["snapshot_every"])
    if event_cooldown_sec is None:
        event_cooldown_sec = float(runtime["event_cooldown_sec"])
    if live_frame_width is None:
        live_frame_width = runtime["live_frame_width"]
    if inference_every is None:
        inference_every = int(runtime["inference_every"])
    if person_conf is None:
        person_conf = float(runtime["person_conf"])
    if ppe_conf is None:
        ppe_conf = float(runtime["ppe_conf"])
    if smoothing_window is None:
        smoothing_window = int(runtime["smoothing_window"])
    if no_helmet_confirm_frames is None:
        no_helmet_confirm_frames = int(runtime["no_helmet_confirm_frames"])
    if risk_alpha is None:
        risk_alpha = float(runtime["risk_alpha"])
    if alert_duration_sec is None:
        alert_duration_sec = float(runtime["alert_duration_sec"])
    if loop_video is None:
        loop_video = bool(runtime["loop_video"])

    video_path = load_video_source(camera_id)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    start_frame = max(0, int(start_sec * fps))
    end_frame = int(end_sec * fps) if end_sec is not None else None

    if end_frame is not None and end_frame <= start_frame:
        raise ValueError("--end-sec must be greater than --start-sec")

    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    rules = load_risk_rules()
    policy = decision_policy(rules)

    zone_name: str | None = None
    zone_points: list[list[int]] = []
    if camera_uses_zone(camera_id):
        zone = ZoneChecker().get_zone(camera_id)
        zone_name = zone["name"]
        zone_points = zone["points"]

    person_detector = PersonDetector()
    ppe_detector = PPEDetector() if camera_uses_ppe(camera_id) else None
    tracker = CentroidTracker(max_distance=max(width, height) * 0.045, max_missed_frames=20)
    decision_manager = TrackStateManager(
        window_size=smoothing_window,
        no_helmet_confirm_frames=no_helmet_confirm_frames,
        no_helmet_clear_frames=max(
            no_helmet_confirm_frames + int(tracking["no_helmet_clear_extra_frames"]),
            int(tracking["no_helmet_clear_min_frames"]),
        ),
        zone_confirm_frames=max(
            int(tracking["zone_confirm_min_frames"]),
            min(int(tracking["zone_confirm_max_frames"]), smoothing_window // 2),
        ),
        zone_clear_frames=max(
            int(tracking["zone_clear_min_frames"]),
            min(int(tracking["zone_clear_max_frames"]), smoothing_window),
        ),
        risk_alpha=risk_alpha,
        alert_duration_seconds=alert_duration_sec,
        stale_after_frames=int(tracking["stale_after_frames"]),
        warning_min_score=policy["warning_min_score"],
        violation_min_score=policy["violation_min_score"],
        stable_violation_min_score=policy["stable_violation_min_score"],
        combined_violation_score=policy["combined_violation_score"],
    )
    rule_engine = RuleEngine()
    history_logger = HistoryLogger()
    action_engine = ActionEngine(history_logger=history_logger, realtime_logs=realtime_logs)
    event_state_manager = EventStateManager(
        ongoing_cooldown_seconds=max(float(tracking["event_ongoing_cooldown_min_sec"]), event_cooldown_sec)
    )
    last_alert_times: dict[tuple[int | str | None, str], float] = {}

    writer = None
    output_path = OUTPUT_VIDEO_DIR / f"{camera_id}_output.mp4"
    if save_video:
        writer = open_video_writer(output_path, fps=fps, width=width, height=height)
    LIVE_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Running demo for {camera_id}")
    print(f"Video: {video_path}")
    print(f"Segment: start_sec={start_sec}, end_sec={end_sec}, max_frames={max_frames}")
    if zone_points:
        print(f"Zone: {zone_name}, points={len(zone_points)}")
    if ppe_detector:
        print("PPE: enabled")
    if save_video:
        print(f"Saving video: {output_path}")

    processed_frames = 0
    frame_index = start_frame
    cached_track_risks: list[tuple[TrackState, dict[str, Any], dict[str, Any] | None]] = []
    cached_ppe_detections = []
    cached_frame_risks: list[dict[str, Any]] = []
    try:
        while True:
            if max_frames is not None and processed_frames >= max_frames:
                break
            if end_frame is not None and frame_index >= end_frame:
                break

            ok, frame = cap.read()
            if not ok:
                if loop_video and end_frame is None:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
                    frame_index = start_frame
                    tracker = CentroidTracker(max_distance=max(width, height) * 0.045, max_missed_frames=20)
                    decision_manager = TrackStateManager(
                        window_size=smoothing_window,
                        no_helmet_confirm_frames=no_helmet_confirm_frames,
                        no_helmet_clear_frames=max(
                            no_helmet_confirm_frames + int(tracking["no_helmet_clear_extra_frames"]),
                            int(tracking["no_helmet_clear_min_frames"]),
                        ),
                        zone_confirm_frames=max(
                            int(tracking["zone_confirm_min_frames"]),
                            min(int(tracking["zone_confirm_max_frames"]), smoothing_window // 2),
                        ),
                        zone_clear_frames=max(
                            int(tracking["zone_clear_min_frames"]),
                            min(int(tracking["zone_clear_max_frames"]), smoothing_window),
                        ),
                        risk_alpha=risk_alpha,
                        alert_duration_seconds=alert_duration_sec,
                        stale_after_frames=int(tracking["stale_after_frames"]),
                        warning_min_score=policy["warning_min_score"],
                        violation_min_score=policy["violation_min_score"],
                        stable_violation_min_score=policy["stable_violation_min_score"],
                        combined_violation_score=policy["combined_violation_score"],
                    )
                    event_state_manager = EventStateManager(
                        ongoing_cooldown_seconds=max(
                            float(tracking["event_ongoing_cooldown_min_sec"]),
                            event_cooldown_sec,
                        )
                    )
                    cached_track_risks = []
                    cached_ppe_detections = []
                    cached_frame_risks = []
                    continue
                break

            timestamp_seconds = frame_index / fps
            should_infer = processed_frames % max(1, inference_every) == 0
            person_detections = []
            ppe_detections = cached_ppe_detections
            track_risks = cached_track_risks
            frame_risks = cached_frame_risks

            if should_infer:
                person_detections = person_detector.detect(frame, conf=person_conf)
                ppe_detections = ppe_detector.detect(frame, conf=ppe_conf) if ppe_detector else []
                tracks = tracker.update(person_detections, frame_index=frame_index)
                active_tracks = [track for track in tracks if track.missed_frames == 0]

                helmet_states: dict[int, dict[str, Any]] = {}
                if ppe_detector:
                    for track in active_tracks:
                        helmet_states[track.track_id] = match_helmet_to_person(track.bbox, ppe_detections)

                decisions = {}
                raw_context = {}
                for track in active_tracks:
                    raw_inside_zone = bool(zone_points and is_point_inside_zone(track.bottom_center, zone_points))
                    helmet_state = helmet_states.get(track.track_id)
                    raw_no_helmet = bool(helmet_state and helmet_state.get("no_helmet"))
                    if raw_no_helmet:
                        raw_ppe = PPE_NO_HELMET
                    elif helmet_state and helmet_state.get("has_helmet"):
                        raw_ppe = PPE_HELMET
                    else:
                        raw_ppe = PPE_UNKNOWN

                    raw_risk = score_event(
                        camera_id=camera_id,
                        person_detected=True,
                        inside_danger_zone=raw_inside_zone,
                        no_helmet=raw_no_helmet,
                        uncertain=bool(helmet_state and helmet_state.get("uncertain")),
                    )
                    decision = decision_manager.update(
                        track_id=track.track_id,
                        raw_ppe=raw_ppe,
                        raw_inside_zone=raw_inside_zone,
                        current_frame_risk=raw_risk["risk_score"],
                        timestamp_seconds=timestamp_seconds,
                        frame_index=frame_index,
                    )
                    decisions[track.track_id] = decision
                    raw_context[track.track_id] = (helmet_state, bool(helmet_state and helmet_state.get("uncertain")))

                stable_no_helmet_count = sum(1 for decision in decisions.values() if decision.no_helmet)
                track_risks = []
                person_status_rows = []
                for track in active_tracks:
                    decision = decisions[track.track_id]
                    helmet_state, uncertain = raw_context.get(track.track_id, (None, False))
                    tracker.update_zone_state(track, decision.stable_inside_zone, timestamp_seconds)
                    tracker.update_no_helmet_state(track, decision.no_helmet, timestamp_seconds)

                    risk = rule_engine.score_track(
                        camera_id=camera_id,
                        person_detected=True,
                        decision=decision,
                        total_inside_seconds=track.total_inside_seconds,
                        no_helmet_seconds=track.total_no_helmet_seconds,
                        no_helmet_count=stable_no_helmet_count,
                        uncertain=uncertain,
                    )
                    risk = promote_ppe_visibility_warning(
                        camera_id,
                        risk,
                        helmet_state,
                        ppe_warning_score=policy["ppe_visibility_warning_score"],
                    )
                    track_risks.append((track, risk, helmet_state))

                    person_status_rows.append(
                        {
                            "id": track.track_id,
                            "camera_id": camera_id,
                            "ppe_state": decision.stable_ppe,
                            "zone_state": "IN_ZONE" if decision.stable_inside_zone else "OUTSIDE",
                            "risk": risk["risk_score"],
                            "severity": risk["severity"],
                            "reasons": risk.get("reasons", []),
                            "actions": risk.get("actions", []),
                            "details": risk.get("details", {}),
                            "duration": round(decision.violation_duration_seconds, 2),
                            "status": risk.get("details", {}).get("decision_status", decision.status),
                        }
                    )

                    for violation_type, is_active in (
                        ("danger_zone", decision.stable_inside_zone),
                        ("no_helmet", decision.no_helmet),
                    ):
                        event_state = event_state_manager.update(
                            camera_id=camera_id,
                            person_id=track.track_id,
                            violation_type=violation_type,
                            active=is_active,
                            severity=risk["severity"],
                            timestamp_seconds=timestamp_seconds,
                        )
                        if not event_state:
                            continue

                        event_risk = {
                            **risk,
                            "reasons": [*risk.get("reasons", []), event_state],
                            "details": {
                                **risk.get("details", {}),
                                "event_state": event_state,
                                "violation_type": violation_type,
                            },
                        }
                        if event_state == "RESOLVED":
                            event_risk["severity"] = "normal"
                            event_risk["risk_score"] = 0
                            event_risk["actions"] = ["save_history", "ui_warning"]
                        maybe_handle_action(
                            camera_id=camera_id,
                            risk=event_risk,
                            timestamp_seconds=timestamp_seconds,
                            action_engine=action_engine,
                            last_alert_times=last_alert_times,
                            event_cooldown_sec=0.0,
                            track=track,
                            zone_name=zone_name,
                            helmet_state=helmet_state,
                            event_key=f"{track.track_id}:{violation_type}:{event_state}",
                            snapshot_frame=frame,
                            force_history=True,
                        )

                frame_risks = []
                if camera_id == "camera_3" and not active_tracks:
                    unmatched_head_count = count_unmatched_heads(ppe_detections)
                    if unmatched_head_count > 0:
                        risk = score_event(
                            camera_id="camera_3",
                            person_detected=False,
                            no_helmet=True,
                            no_helmet_count=unmatched_head_count,
                        )
                        frame_risks.append(risk)
                        head_bbox = next((det for det in ppe_detections if is_head(det.label)), None)
                        maybe_handle_action(
                            camera_id=camera_id,
                            risk=risk,
                            timestamp_seconds=timestamp_seconds,
                            action_engine=action_engine,
                            last_alert_times=last_alert_times,
                            event_cooldown_sec=event_cooldown_sec,
                            bbox=head_bbox,
                            event_key="frame_no_helmet",
                            snapshot_frame=frame,
                        )

                decision_manager.cleanup(frame_index)
                cached_track_risks = track_risks
                cached_ppe_detections = ppe_detections
                cached_frame_risks = frame_risks
                write_person_status(
                    camera_id,
                    {
                        "camera_id": camera_id,
                        "frame_index": frame_index,
                        "persons": person_status_rows,
                    },
                )

            annotated = render_overlay(
                frame,
                camera_id=camera_id,
                frame_index=frame_index,
                zone_points=zone_points,
                zone_label=zone_name,
                track_risks=track_risks,
                ppe_detections=ppe_detections,
                frame_risks=frame_risks,
            )

            if writer:
                writer.write(annotated)

            if snapshot_every > 0 and processed_frames % snapshot_every == 0:
                save_latest_frame_atomic(camera_id, annotated, live_width=live_frame_width)

            if processed_frames % 25 == 0:
                print(
                    f"frame={frame_index}, persons={len(person_detections)}, "
                    f"ppe={len(ppe_detections)}, tracks={len(track_risks)}, "
                    f"infer={should_infer}"
                )

            frame_index += 1
            processed_frames += 1
    finally:
        cap.release()
        if writer:
            writer.release()

    print(f"Done. Processed frames: {processed_frames}")
    if save_video:
        print(f"Output video: {output_path}")
    print(f"Alert history: {HistoryLogger().output_path}")


def parse_args() -> argparse.Namespace:
    defaults = pipeline_settings()
    parser = argparse.ArgumentParser(description="E2E CCTV safety demo")
    parser.add_argument("--camera", default="camera_2", help="Camera ID from video_sources.yaml")
    parser.add_argument("--all", action="store_true", help="Run all configured demo cameras")
    parser.add_argument("--max-frames", type=int, default=defaults["max_frames"], help="Maximum frames to process")
    parser.add_argument("--save-video", action=argparse.BooleanOptionalAction, default=bool(defaults["save_video"]), help="Save annotated output video")
    parser.add_argument("--start-sec", type=float, default=float(defaults["start_sec"]), help="Start time in seconds")
    parser.add_argument("--end-sec", type=float, default=defaults["end_sec"], help="End time in seconds")
    parser.add_argument("--realtime-logs", action=argparse.BooleanOptionalAction, default=bool(defaults["realtime_logs"]), help="Write AI/device serial-style logs")
    parser.add_argument("--snapshot-every", type=int, default=int(defaults["snapshot_every"]), help="Save latest frame every N processed frames")
    parser.add_argument("--event-cooldown-sec", type=float, default=float(defaults["event_cooldown_sec"]), help="Minimum seconds between repeated events")
    parser.add_argument("--live-frame-width", type=int, default=defaults["live_frame_width"], help="Resize latest live frame to this width")
    parser.add_argument("--inference-every", type=int, default=int(defaults["inference_every"]), help="Run YOLO every N frames and reuse stable overlay between runs")
    parser.add_argument("--person-conf", type=float, default=float(defaults["person_conf"]), help="Person detector confidence threshold")
    parser.add_argument("--ppe-conf", type=float, default=float(defaults["ppe_conf"]), help="PPE detector confidence threshold")
    parser.add_argument("--smoothing-window", type=int, default=int(defaults["smoothing_window"]), help="Temporal voting window per tracked person")
    parser.add_argument("--no-helmet-confirm-frames", type=int, default=int(defaults["no_helmet_confirm_frames"]), help="Frames needed to confirm no-helmet state")
    parser.add_argument("--risk-alpha", type=float, default=float(defaults["risk_alpha"]), help="EMA alpha for smoothed track risk")
    parser.add_argument("--alert-duration-sec", type=float, default=float(defaults["alert_duration_sec"]), help="Violation duration before alert/history emission")
    parser.add_argument("--loop-video", action=argparse.BooleanOptionalAction, default=bool(defaults["loop_video"]), help="Loop the configured video source when it reaches EOF")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    camera_ids = CAMERAS if args.all else (args.camera,)
    for camera_id in camera_ids:
        run_demo(
            camera_id=camera_id,
            max_frames=args.max_frames,
            save_video=args.save_video,
            start_sec=args.start_sec,
            end_sec=args.end_sec,
            realtime_logs=args.realtime_logs,
            snapshot_every=args.snapshot_every,
            event_cooldown_sec=args.event_cooldown_sec,
            live_frame_width=args.live_frame_width,
            inference_every=args.inference_every,
            person_conf=args.person_conf,
            ppe_conf=args.ppe_conf,
            smoothing_window=args.smoothing_window,
            no_helmet_confirm_frames=args.no_helmet_confirm_frames,
            risk_alpha=args.risk_alpha,
            alert_duration_sec=args.alert_duration_sec,
            loop_video=args.loop_video,
        )


if __name__ == "__main__":
    main()
