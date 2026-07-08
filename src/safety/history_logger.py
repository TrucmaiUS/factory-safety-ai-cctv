import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.perception.detection_types import DetectionBox
from src.safety.simple_tracker import TrackState


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HISTORY_PATH = ROOT / "outputs" / "alert_history.jsonl"
LIVE_DIR = ROOT / "outputs" / "live"


def _bbox_list(bbox: DetectionBox | None) -> list[float] | None:
    if bbox is None:
        return None
    return [bbox.x1, bbox.y1, bbox.x2, bbox.y2]


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
        }

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
    ) -> dict[str, Any]:
        event = self.build_event(
            camera_id=camera_id,
            risk=risk,
            track=track,
            zone_name=zone_name,
            helmet_state=helmet_state,
            bbox=bbox,
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
        tmp_path = path.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(event, f, ensure_ascii=False, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)

    def read_latest_event(self, camera_id: str) -> dict[str, Any] | None:
        path = LIVE_DIR / f"{camera_id}_latest_event.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None


def append_event(event: dict[str, Any]) -> None:
    HistoryLogger().append_event(event)


def read_recent_events(limit: int = 50) -> list[dict[str, Any]]:
    return HistoryLogger().read_recent_events(limit)


def write_latest_event(camera_id: str, event: dict[str, Any]) -> None:
    HistoryLogger().write_latest_event(camera_id, event)


def read_latest_event(camera_id: str) -> dict[str, Any] | None:
    return HistoryLogger().read_latest_event(camera_id)
