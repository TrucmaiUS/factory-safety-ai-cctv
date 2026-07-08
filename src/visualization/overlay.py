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
    details = risk.get("details", {})
    color = SEVERITY_COLORS.get(severity, (255, 255, 255))
    x1, y1, x2, y2 = [int(v) for v in [bbox.x1, bbox.y1, bbox.x2, bbox.y2]]

    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 4)
    cv2.circle(frame, (int(track.bottom_center[0]), int(track.bottom_center[1])), 8, color, -1)

    stable_ppe = details.get("stable_ppe")
    decision_status = details.get("decision_status", "SAFE")
    if stable_ppe:
        ppe_label = f" | {stable_ppe.upper()}"
    elif helmet_state:
        if helmet_state.get("no_helmet"):
            ppe_label = " | NO_HELMET"
        elif helmet_state.get("has_helmet"):
            ppe_label = " | HELMET"
        elif helmet_state.get("uncertain"):
            ppe_label = " | UNKNOWN"
        else:
            ppe_label = ""
    else:
        ppe_label = ""

    label = f"#{track.track_id}{ppe_label} | Risk:{risk.get('risk_score', 0)}"
    label_y = max(34, y1 - 12)
    label_scale = 0.9
    label_thickness = 2
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, label_scale, label_thickness)
    cv2.rectangle(
        frame,
        (x1, max(0, label_y - th - 10)),
        (x1 + tw + 14, label_y + 8),
        (0, 0, 0),
        -1,
    )
    cv2.putText(
        frame,
        label,
        (x1 + 7, label_y),
        cv2.FONT_HERSHEY_SIMPLEX,
        label_scale,
        color,
        label_thickness,
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
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
        cv2.putText(
            frame,
            label,
            (x1, max(18, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            color,
            3,
            cv2.LINE_AA,
        )


def draw_panel(
    frame: np.ndarray,
    camera_id: str,
    frame_index: int,
    max_risk: dict,
    active_tracks: int,
) -> None:
    scale = max(1.0, min(3.2, frame.shape[1] / 1280.0))
    severity = max_risk.get("severity", "normal")
    score = max_risk.get("risk_score", 0)
    details = max_risk.get("details", {})
    no_helmet_count = details.get("no_helmet_count", 0)
    color = SEVERITY_COLORS.get(severity, (255, 255, 255))
    line1 = f"{camera_id} | frame {frame_index} | tracks {active_tracks} | no_helmet {no_helmet_count}"
    line2 = f"MAX RISK {score}/100 | {severity.upper()}"
    line1_scale = 0.64 * scale
    line2_scale = 0.82 * scale
    line_thickness = max(2, int(round(2.0 * scale)))
    line1_size, _ = cv2.getTextSize(line1, cv2.FONT_HERSHEY_SIMPLEX, line1_scale, line_thickness)
    line2_size, _ = cv2.getTextSize(line2, cv2.FONT_HERSHEY_SIMPLEX, line2_scale, line_thickness)
    panel_w = min(int(620 * scale), max(line1_size[0], line2_size[0]) + int(42 * scale))
    panel_h = int(82 * scale)
    x, y = int(18 * scale), int(18 * scale)
    pad_x = int(20 * scale)
    line_1_y = int(30 * scale)
    line_2_y = int(62 * scale)
    overlay = frame.copy()
    cv2.rectangle(overlay, (x, y), (x + panel_w, y + panel_h), (20, 20, 20), -1)
    cv2.addWeighted(overlay, 0.82, frame, 0.18, 0, frame)

    lines = [(line1, line1_scale), (line2, line2_scale)]

    y_offsets = [line_1_y, line_2_y]
    for i, (text, font_scale) in enumerate(lines):
        cv2.putText(
            frame,
            text,
            (x + pad_x, y + y_offsets[i]),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            color if i == 1 else (245, 245, 245),
            line_thickness,
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
