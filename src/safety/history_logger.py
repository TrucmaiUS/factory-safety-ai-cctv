import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2

from src.perception.detection_types import DetectionBox
from src.safety.simple_tracker import TrackState
from src.safety.zone_checker import draw_zone
from src.utils.atomic_io import write_json_atomic
from src.visualization.overlay import SEVERITY_COLORS, draw_person_bbox


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HISTORY_PATH = ROOT / "outputs" / "alert_history.jsonl"
LIVE_DIR = ROOT / "outputs" / "live"
SNAPSHOT_DIR = ROOT / "outputs" / "alert_snapshots"


def _bbox_list(bbox: DetectionBox | None) -> list[float] | None:
    if bbox is None:
        return None
    return [bbox.x1, bbox.y1, bbox.x2, bbox.y2]


def _draw_event_bbox(
    frame,
    risk: dict[str, Any] | None = None,
    track: TrackState | None = None,
    helmet_state: dict[str, Any] | None = None,
    bbox: DetectionBox | None = None,
) -> None:
    if track is not None:
        draw_person_bbox(frame, track, risk or {}, helmet_state)
        return

    if bbox is None:
        return

    severity = (risk or {}).get("severity", "warning")
    color = SEVERITY_COLORS.get(severity, (0, 210, 255))
    x1, y1, x2, y2 = [int(v) for v in [bbox.x1, bbox.y1, bbox.x2, bbox.y2]]
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 4)

    label = f"{bbox.label} | Risk:{(risk or {}).get('risk_score', 0)}"
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


class HistoryLogger:
    def __init__(self, output_path: Path | str = DEFAULT_HISTORY_PATH) -> None:
        self.output_path = Path(output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.touch(exist_ok=True)

    def build_event(
        self,
        camera_id: str,
        risk: dict[str, Any],
        track: TrackState | None = None,
        zone_name: str | None = None,
        helmet_state: dict[str, Any] | None = None,
        bbox: DetectionBox | None = None,
        snapshot_path: str | None = None,
    ) -> dict[str, Any]:
        event_bbox = bbox or (track.bbox if track else None)
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "camera_id": camera_id,
            "track_id": track.track_id if track else None,
            "risk_score": risk["risk_score"],
            "severity": risk["severity"],
            "reasons": risk["reasons"],
            "actions": risk["actions"],
            "details": risk.get("details", {}),
            "bbox": _bbox_list(event_bbox),
            "zone_name": zone_name,
            "helmet_state": helmet_state,
            "snapshot_path": snapshot_path,
            "snapshot_url": f"/api/events/snapshots/{Path(snapshot_path).name}" if snapshot_path else None,
        }

    def save_snapshot(
        self,
        camera_id: str,
        frame,
        track_id: int | None = None,
        risk: dict[str, Any] | None = None,
        track: TrackState | None = None,
        helmet_state: dict[str, Any] | None = None,
        bbox: DetectionBox | None = None,
        zone_points: list[list[int]] | None = None,
        zone_name: str | None = None,
        max_width: int = 960,
        jpeg_quality: int = 86,
    ) -> str | None:
        if frame is None:
            return None

        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        name = f"{timestamp}_{camera_id}_track_{track_id if track_id is not None else 'frame'}.jpg"
        path = SNAPSHOT_DIR / name

        output = frame.copy()
        if zone_points:
            output = draw_zone(output, zone_points, zone_name or "danger_zone")
        _draw_event_bbox(output, risk=risk, track=track, helmet_state=helmet_state, bbox=bbox)
        if max_width and frame.shape[1] > max_width:
            scale = max_width / frame.shape[1]
            output = cv2.resize(output, (max_width, int(frame.shape[0] * scale)), interpolation=cv2.INTER_AREA)

        ok = cv2.imwrite(str(path), output, [cv2.IMWRITE_JPEG_QUALITY, int(jpeg_quality)])
        return str(path) if ok else None

    def append_event(self, event: dict[str, Any]) -> None:
        with self.output_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def log_event(
        self,
        camera_id: str,
        risk: dict[str, Any],
        track: TrackState | None = None,
        zone_name: str | None = None,
        helmet_state: dict[str, Any] | None = None,
        bbox: DetectionBox | None = None,
        snapshot_path: str | None = None,
    ) -> dict[str, Any]:
        event = self.build_event(
            camera_id=camera_id,
            risk=risk,
            track=track,
            zone_name=zone_name,
            helmet_state=helmet_state,
            bbox=bbox,
            snapshot_path=snapshot_path,
        )
        self.append_event(event)

        return event

    def read_recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.output_path.exists():
            return []

        events: list[dict[str, Any]] = []
        for line in self.output_path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]:
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events

    def write_latest_event(self, camera_id: str, event: dict[str, Any]) -> None:
        LIVE_DIR.mkdir(parents=True, exist_ok=True)
        path = LIVE_DIR / f"{camera_id}_latest_event.json"
        write_json_atomic(path, event)

    def read_latest_event(self, camera_id: str) -> dict[str, Any] | None:
        path = LIVE_DIR / f"{camera_id}_latest_event.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None


def append_event(event: dict[str, Any]) -> None:
    HistoryLogger().append_event(event)


def read_recent_events(limit: int = 50) -> list[dict[str, Any]]:
    return HistoryLogger().read_recent_events(limit)


def write_latest_event(camera_id: str, event: dict[str, Any]) -> None:
    HistoryLogger().write_latest_event(camera_id, event)


def read_latest_event(camera_id: str) -> dict[str, Any] | None:
    return HistoryLogger().read_latest_event(camera_id)


def write_current_decision(camera_id: str, payload: dict[str, Any] | None) -> None:
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    path = LIVE_DIR / f"{camera_id}_current_decision.json"
    if payload is None:
        path.unlink(missing_ok=True)
        return
    write_json_atomic(path, payload)


def write_person_status(camera_id: str, payload: dict[str, Any]) -> None:
    LIVE_DIR.mkdir(parents=True, exist_ok=True)
    path = LIVE_DIR / f"{camera_id}_person_status.json"
    write_json_atomic(path, payload)
