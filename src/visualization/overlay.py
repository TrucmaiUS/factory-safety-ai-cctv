import cv2
import numpy as np

from src.perception.detection_types import DetectionBox
from src.perception.ppe_detector import is_head, is_helmet
from src.safety.simple_tracker import TrackState
from src.safety.zone_checker import draw_zone


SEVERITY_COLORS = {
    "normal": (70, 200, 70),
    "warning": (0, 210, 255),
    "high": (0, 140, 255),
    "critical": (0, 0, 255),
}
PPE_COLORS = {
    "helmet": (60, 220, 60),
    "head": (0, 120, 255),
}


def _clip_text(text: str, max_len: int = 82) -> str:
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


def draw_person_bbox(frame: np.ndarray, track: TrackState, risk: dict, helmet_state: dict | None) -> None:
    bbox = track.bbox
    severity = risk.get("severity", "normal")
    color = SEVERITY_COLORS.get(severity, (255, 255, 255))
    x1, y1, x2, y2 = [int(v) for v in [bbox.x1, bbox.y1, bbox.x2, bbox.y2]]

    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
    cv2.circle(frame, (int(track.bottom_center[0]), int(track.bottom_center[1])), 6, color, -1)

    ppe_label = ""
    if helmet_state:
        if helmet_state.get("no_helmet"):
            ppe_label = " | NO HELMET"
        elif helmet_state.get("has_helmet"):
            ppe_label = " | HELMET"
        elif helmet_state.get("uncertain"):
            ppe_label = " | PPE?"

    cv2.putText(
        frame,
        f"ID {track.track_id} | {severity.upper()} | {risk.get('risk_score', 0)}{ppe_label}",
        (x1, max(24, y1 - 8)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        color,
        2,
        cv2.LINE_AA,
    )


def draw_ppe_boxes(frame: np.ndarray, ppe_detections: list[DetectionBox]) -> None:
    for det in ppe_detections:
        if is_helmet(det.label):
            color = PPE_COLORS["helmet"]
            label = f"helmet {det.conf:.2f}"
        elif is_head(det.label):
            color = PPE_COLORS["head"]
            label = f"head {det.conf:.2f}"
        else:
            continue

        x1, y1, x2, y2 = [int(v) for v in [det.x1, det.y1, det.x2, det.y2]]
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(
            frame,
            label,
            (x1, max(18, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            2,
            cv2.LINE_AA,
        )


def draw_panel(
    frame: np.ndarray,
    camera_id: str,
    frame_index: int,
    max_risk: dict,
    active_tracks: int,
) -> None:
    panel_w = 760
    panel_h = 190
    x, y = 18, 18
    overlay = frame.copy()
    cv2.rectangle(overlay, (x, y), (x + panel_w, y + panel_h), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.72, frame, 0.28, 0, frame)

    severity = max_risk.get("severity", "normal")
    score = max_risk.get("risk_score", 0)
    reasons = _clip_text(", ".join(max_risk.get("reasons", [])) or "none")
    actions = _clip_text(", ".join(max_risk.get("actions", [])) or "none")
    details = max_risk.get("details", {})
    no_helmet_count = details.get("no_helmet_count", 0)
    color = SEVERITY_COLORS.get(severity, (255, 255, 255))

    lines = [
        f"{camera_id} | frame {frame_index} | tracks {active_tracks} | no_helmet {no_helmet_count}",
        f"risk: {score}/100 | alert: {severity.upper()}",
        f"trace: {reasons}",
        f"actions: {actions}",
    ]

    for i, text in enumerate(lines):
        cv2.putText(
            frame,
            text,
            (x + 16, y + 34 + i * 38),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.68,
            color if i == 1 else (245, 245, 245),
            2,
            cv2.LINE_AA,
        )


def render_overlay(
    frame: np.ndarray,
    camera_id: str,
    frame_index: int,
    zone_points: list[list[int]] | None,
    zone_label: str | None,
    track_risks: list[tuple[TrackState, dict, dict | None]],
    ppe_detections: list[DetectionBox] | None = None,
    frame_risks: list[dict] | None = None,
) -> np.ndarray:
    if zone_points:
        annotated = draw_zone(frame, zone_points, zone_label or "danger_zone")
    else:
        annotated = frame.copy()

    ppe_detections = ppe_detections or []
    frame_risks = frame_risks or []
    draw_ppe_boxes(annotated, ppe_detections)

    max_risk = {"risk_score": 0, "severity": "normal", "reasons": [], "actions": [], "details": {}}
    for track, risk, helmet_state in track_risks:
        draw_person_bbox(annotated, track, risk, helmet_state)
        if risk.get("risk_score", 0) > max_risk["risk_score"]:
            max_risk = risk

    for risk in frame_risks:
        if risk.get("risk_score", 0) > max_risk["risk_score"]:
            max_risk = risk

    draw_panel(
        annotated,
        camera_id=camera_id,
        frame_index=frame_index,
        max_risk=max_risk,
        active_tracks=len(track_risks),
    )
    return annotated
