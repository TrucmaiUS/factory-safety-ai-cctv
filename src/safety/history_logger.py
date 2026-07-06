import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.perception.detection_types import DetectionBox
from src.safety.simple_tracker import TrackState


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HISTORY_PATH = ROOT / "outputs" / "alert_history.jsonl"


def _bbox_list(bbox: DetectionBox | None) -> list[float] | None:
    if bbox is None:
        return None
    return [bbox.x1, bbox.y1, bbox.x2, bbox.y2]


class HistoryLogger:
    def __init__(self, output_path: Path | str = DEFAULT_HISTORY_PATH) -> None:
        self.output_path = Path(output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.touch(exist_ok=True)

    def log_event(
        self,
        camera_id: str,
        risk: dict[str, Any],
        track: TrackState | None = None,
        zone_name: str | None = None,
        helmet_state: dict[str, Any] | None = None,
        bbox: DetectionBox | None = None,
    ) -> dict[str, Any]:
        event_bbox = bbox or (track.bbox if track else None)
        event = {
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

        with self.output_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")

        return event
