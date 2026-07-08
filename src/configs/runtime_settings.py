from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
RUNTIME_SETTINGS_PATH = ROOT / "src" / "configs" / "runtime_settings.yaml"

DEFAULT_RUNTIME_SETTINGS: dict[str, Any] = {
    "pipeline": {
        "max_frames": None,
        "start_sec": 0.0,
        "end_sec": None,
        "save_video": False,
        "realtime_logs": False,
        "loop_video": False,
        "snapshot_every": 3,
        "event_cooldown_sec": 2.0,
        "live_frame_width": 960,
        "inference_every": 2,
        "person_conf": 0.35,
        "ppe_conf": 0.25,
        "smoothing_window": 12,
        "no_helmet_confirm_frames": 6,
        "risk_alpha": 0.85,
        "alert_duration_sec": 1.5,
    },
    "dashboard_worker": {
        "max_frames": 0,
        "save_video": True,
        "realtime_logs": True,
        "loop_video": True,
    },
    "tracking": {
        "no_helmet_clear_extra_frames": 2,
        "no_helmet_clear_min_frames": 8,
        "zone_confirm_min_frames": 3,
        "zone_confirm_max_frames": 5,
        "zone_clear_min_frames": 6,
        "zone_clear_max_frames": 8,
        "stale_after_frames": 60,
        "event_ongoing_cooldown_min_sec": 5.0,
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


@lru_cache(maxsize=1)
def load_runtime_settings() -> dict[str, Any]:
    if not RUNTIME_SETTINGS_PATH.exists():
        return deepcopy(DEFAULT_RUNTIME_SETTINGS)
    with RUNTIME_SETTINGS_PATH.open("r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f) or {}
    if not isinstance(loaded, dict):
        loaded = {}
    return _deep_merge(DEFAULT_RUNTIME_SETTINGS, loaded)


def pipeline_settings() -> dict[str, Any]:
    return dict(load_runtime_settings().get("pipeline", {}))


def dashboard_worker_settings() -> dict[str, Any]:
    settings = load_runtime_settings()
    return {
        **settings.get("pipeline", {}),
        **settings.get("dashboard_worker", {}),
    }


def tracking_settings() -> dict[str, Any]:
    return dict(load_runtime_settings().get("tracking", {}))
