import argparse
import os
from pathlib import Path
from typing import Any

import cv2
import yaml

from src.perception.detection_types import DetectionBox
from src.perception.person_detector import PersonDetector
from src.perception.ppe_detector import PPEDetector, is_head
from src.safety.action_engine import ActionEngine
from src.safety.helmet_matcher import count_unmatched_heads, match_helmet_to_person
from src.safety.history_logger import HistoryLogger
from src.safety.risk_scoring import score_event
from src.safety.simple_tracker import CentroidTracker, TrackState
from src.safety.zone_checker import ZoneChecker, is_point_inside_zone
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
    return camera_id in {"camera_1", "camera_2"}


def camera_uses_ppe(camera_id: str) -> bool:
    return camera_id in {"camera_1", "camera_3"}


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
    tmp_path = LIVE_DIR / f"{camera_id}_latest.tmp.jpg"
    ok = cv2.imwrite(
        str(tmp_path),
        output_frame,
        [cv2.IMWRITE_JPEG_QUALITY, int(jpeg_quality)],
    )
    if ok:
        os.replace(tmp_path, final_path)


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
) -> None:
    if "save_history" not in risk.get("actions", []) or risk.get("severity") == "normal":
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
    )


def run_demo(
    camera_id: str,
    max_frames: int | None,
    save_video: bool,
    start_sec: float = 0.0,
    end_sec: float | None = None,
    realtime_logs: bool = False,
    snapshot_every: int = 5,
    event_cooldown_sec: float = 2.0,
    live_frame_width: int | None = 960,
) -> None:
    if camera_id not in CAMERAS:
        raise ValueError(f"Unsupported camera '{camera_id}'. Expected one of: {', '.join(CAMERAS)}")

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

    zone_name: str | None = None
    zone_points: list[list[int]] = []
    if camera_uses_zone(camera_id):
        zone = ZoneChecker().get_zone(camera_id)
        zone_name = zone["name"]
        zone_points = zone["points"]

    person_detector = PersonDetector()
    ppe_detector = PPEDetector() if camera_uses_ppe(camera_id) else None
    tracker = CentroidTracker(max_distance=max(width, height) * 0.045, max_missed_frames=20)
    history_logger = HistoryLogger()
    action_engine = ActionEngine(history_logger=history_logger, realtime_logs=realtime_logs)
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
    try:
        while True:
            if max_frames is not None and processed_frames >= max_frames:
                break
            if end_frame is not None and frame_index >= end_frame:
                break

            ok, frame = cap.read()
            if not ok:
                break

            timestamp_seconds = frame_index / fps
            person_detections = person_detector.detect(frame, conf=0.35)
            ppe_detections = ppe_detector.detect(frame, conf=0.25) if ppe_detector else []
            tracks = tracker.update(person_detections, frame_index=frame_index)
            active_tracks = [track for track in tracks if track.missed_frames == 0]

            helmet_states: dict[int, dict[str, Any]] = {}
            if ppe_detector:
                for track in active_tracks:
                    helmet_states[track.track_id] = match_helmet_to_person(track.bbox, ppe_detections)

            current_no_helmet_count = sum(
                1 for state in helmet_states.values()
                if state.get("no_helmet")
            )

            track_risks: list[tuple[TrackState, dict[str, Any], dict[str, Any] | None]] = []
            for track in active_tracks:
                inside_zone = False
                if zone_points:
                    inside_zone = is_point_inside_zone(track.bottom_center, zone_points)
                tracker.update_zone_state(track, inside_zone, timestamp_seconds)

                helmet_state = helmet_states.get(track.track_id)
                no_helmet = bool(helmet_state and helmet_state.get("no_helmet"))
                tracker.update_no_helmet_state(track, no_helmet, timestamp_seconds)

                risk = score_event(
                    camera_id=camera_id,
                    person_detected=True,
                    inside_danger_zone=inside_zone,
                    no_helmet=no_helmet,
                    total_inside_seconds=track.total_inside_seconds,
                    no_helmet_seconds=track.total_no_helmet_seconds,
                    no_helmet_count=current_no_helmet_count,
                    uncertain=bool(helmet_state and helmet_state.get("uncertain")),
                )
                track_risks.append((track, risk, helmet_state))

                maybe_handle_action(
                    camera_id=camera_id,
                    risk=risk,
                    timestamp_seconds=timestamp_seconds,
                    action_engine=action_engine,
                    last_alert_times=last_alert_times,
                    event_cooldown_sec=event_cooldown_sec,
                    track=track,
                    zone_name=zone_name,
                    helmet_state=helmet_state,
                )

            frame_risks: list[dict[str, Any]] = []
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
                    f"no_helmet={current_no_helmet_count}"
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
    parser = argparse.ArgumentParser(description="E2E CCTV safety demo")
    parser.add_argument("--camera", default="camera_2", help="Camera ID from video_sources.yaml")
    parser.add_argument("--all", action="store_true", help="Run all configured demo cameras")
    parser.add_argument("--max-frames", type=int, default=None, help="Maximum frames to process")
    parser.add_argument("--save-video", action="store_true", help="Save annotated output video")
    parser.add_argument("--start-sec", type=float, default=0.0, help="Start time in seconds")
    parser.add_argument("--end-sec", type=float, default=None, help="End time in seconds")
    parser.add_argument("--realtime-logs", action="store_true", help="Write AI/device serial-style logs")
    parser.add_argument("--snapshot-every", type=int, default=5, help="Save latest frame every N processed frames")
    parser.add_argument("--event-cooldown-sec", type=float, default=2.0, help="Minimum seconds between repeated events")
    parser.add_argument("--live-frame-width", type=int, default=960, help="Resize latest live frame to this width")
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
        )


if __name__ == "__main__":
    main()
