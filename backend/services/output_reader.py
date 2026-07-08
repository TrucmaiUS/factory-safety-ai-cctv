import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from src.utils.atomic_io import write_json_atomic


ROOT = Path(__file__).resolve().parents[2]
OUTPUTS = ROOT / "outputs"
LIVE_DIR = OUTPUTS / "live"
DEMO_VIDEO_DIR = OUTPUTS / "demo_videos"
CONTROL_DIR = OUTPUTS / "control"
ALERT_HISTORY_PATH = OUTPUTS / "alert_history.jsonl"
DEVICE_STATUS_PATH = OUTPUTS / "device_status.json"
DEVICE_COMMANDS_PATH = OUTPUTS / "device_commands.jsonl"
SERIAL_LOG_PATH = OUTPUTS / "serial_monitor.log"
VIDEO_SOURCES_PATH = ROOT / "src" / "configs" / "video_sources.yaml"
CAMERAS = ("camera_1", "camera_2", "camera_3")
CAMERA_NAMES = {"camera_1": "Camera 1", "camera_2": "Camera 2", "camera_3": "Camera 3"}
CAMERA_ROLES = {
    "camera_1": "Danger Zone + Helmet",
    "camera_2": "Danger Zone Only",
    "camera_3": "Helmet Compliance",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default: Any = None, retries: int = 5) -> Any:
    if not path.exists():
        return default
    for attempt in range(retries):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            if attempt == retries - 1:
                return default
            time.sleep(0.03 * (attempt + 1))
    return default


def write_json(path: Path, payload: Any) -> None:
    write_json_atomic(path, payload)


def load_video_sources() -> dict[str, dict]:
    if not VIDEO_SOURCES_PATH.exists():
        return {}
    with VIDEO_SOURCES_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def add_freshness(event: dict | None, ttl_seconds: float = 30.0) -> dict | None:
    if not event:
        return None
    event = dict(event)
    ts = parse_timestamp(event.get("timestamp"))
    if not ts:
        event["is_fresh"] = False
        event["age_seconds"] = None
        return event
    age = (datetime.now(timezone.utc) - ts.astimezone(timezone.utc)).total_seconds()
    event["age_seconds"] = round(max(0.0, age), 2)
    event["is_fresh"] = age <= ttl_seconds
    return event


def latest_event_path(camera_id: str) -> Path:
    return LIVE_DIR / f"{camera_id}_latest_event.json"


def latest_frame_path(camera_id: str) -> Path:
    return LIVE_DIR / f"{camera_id}_latest.jpg"


def person_status_path(camera_id: str) -> Path:
    return LIVE_DIR / f"{camera_id}_person_status.json"


def video_path(camera_id: str) -> Path:
    return DEMO_VIDEO_DIR / f"{camera_id}_output.mp4"


def read_latest_event(camera_id: str, ttl_seconds: float = 30.0) -> dict | None:
    return add_freshness(read_json(latest_event_path(camera_id), None), ttl_seconds)


def read_latest_events(ttl_seconds: float = 30.0) -> dict[str, dict | None]:
    return {camera_id: read_latest_event(camera_id, ttl_seconds) for camera_id in CAMERAS}


def read_person_status(camera_id: str) -> dict:
    return read_json(person_status_path(camera_id), {"camera_id": camera_id, "persons": []}) or {
        "camera_id": camera_id,
        "persons": [],
    }


def read_recent_events(limit: int = 100, camera_id: str | None = None, severity: str | None = None) -> list[dict]:
    if not ALERT_HISTORY_PATH.exists():
        return []
    events: list[dict] = []
    try:
        lines = ALERT_HISTORY_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    for line in lines:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if camera_id and event.get("camera_id") != camera_id:
            continue
        if severity and event.get("severity") != severity:
            continue
        events.append(event)
    return list(reversed(events[-limit:]))


def read_device_status() -> dict:
    return read_json(DEVICE_STATUS_PATH, {})


def read_device_commands(limit: int = 50) -> list[dict]:
    if not DEVICE_COMMANDS_PATH.exists():
        return []
    commands = []
    try:
        lines = DEVICE_COMMANDS_PATH.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
    except OSError:
        return []
    for line in lines:
        if not line.strip():
            continue
        try:
            commands.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(commands))


def read_serial_tail(tail: int = 100, camera_id: str | None = None) -> list[str]:
    if not SERIAL_LOG_PATH.exists():
        return []
    try:
        lines = SERIAL_LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()[-tail:]
    except OSError:
        return []
    if camera_id:
        lines = [line for line in lines if camera_id in line or camera_id.replace("_", " ") in line.lower()]
    return lines
