import os
import subprocess
import sys
from pathlib import Path

import psutil

from backend.services.output_reader import (
    CAMERAS,
    CONTROL_DIR,
    current_decision_path,
    latest_event_path,
    latest_frame_path,
    load_video_sources,
    read_latest_event,
    utc_now,
    write_json,
    read_json,
)
from src.configs.runtime_settings import dashboard_worker_settings
from src.iot.device_simulator import ESP32RelaySimulator


ROOT = Path(__file__).resolve().parents[2]
STATUS_PATH = CONTROL_DIR / "camera_process_status.json"
ACTIVE_CAMERA_PATH = CONTROL_DIR / "active_camera.json"
WORKER_LOG_DIR = ROOT / "outputs" / "worker_logs"


def default_statuses() -> dict[str, dict]:
    return {
        camera_id: {"status": "IDLE", "pid": None, "last_update": None}
        for camera_id in CAMERAS
    }


def is_pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        proc = psutil.Process(pid)
        return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
    except psutil.Error:
        return False


def _read_statuses() -> dict[str, dict]:
    statuses = default_statuses()
    loaded = read_json(STATUS_PATH, {})
    if isinstance(loaded, dict):
        for camera_id in CAMERAS:
            if isinstance(loaded.get(camera_id), dict):
                statuses[camera_id].update(loaded[camera_id])
    return statuses


def _write_statuses(statuses: dict[str, dict]) -> None:
    write_json(STATUS_PATH, statuses)


def reconcile_statuses() -> None:
    statuses = _read_statuses()
    changed = False
    for camera_id, status in statuses.items():
        if status.get("status") == "ACTIVE" and not is_pid_alive(status.get("pid")):
            statuses[camera_id] = {"status": "IDLE", "pid": None, "last_update": utc_now()}
            changed = True
    if changed or not STATUS_PATH.exists():
        _write_statuses(statuses)


def get_all_camera_statuses() -> dict[str, dict]:
    reconcile_statuses()
    return _read_statuses()


def get_camera_status(camera_id: str) -> dict:
    if camera_id not in CAMERAS:
        raise ValueError(f"Unsupported camera: {camera_id}")
    statuses = get_all_camera_statuses()
    status = dict(statuses[camera_id])
    status["camera_id"] = camera_id
    status["latest_event"] = read_latest_event(camera_id)
    status["latest_frame_exists"] = latest_frame_path(camera_id).exists()
    return status


def _terminate_pid(pid: int | None) -> None:
    if not is_pid_alive(pid):
        return
    proc = psutil.Process(pid)
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except psutil.TimeoutExpired:
        proc.kill()


def _write_active_camera(camera_id: str | None) -> None:
    write_json(ACTIVE_CAMERA_PATH, {"active_camera": camera_id, "last_update": utc_now()})


def _clear_camera_live_outputs(camera_id: str) -> None:
    latest_event_path(camera_id).unlink(missing_ok=True)
    current_decision_path(camera_id).unlink(missing_ok=True)
    latest_frame_path(camera_id).unlink(missing_ok=True)


def stop_camera(camera_id: str) -> dict:
    if camera_id not in CAMERAS:
        raise ValueError(f"Unsupported camera: {camera_id}")
    statuses = get_all_camera_statuses()
    _terminate_pid(statuses[camera_id].get("pid"))
    statuses[camera_id] = {"status": "IDLE", "pid": None, "last_update": utc_now()}
    _write_statuses(statuses)
    _clear_camera_live_outputs(camera_id)
    if not any(status.get("status") == "ACTIVE" for status in statuses.values()):
        _write_active_camera(None)
    if camera_id in {"camera_1", "camera_2"}:
        ESP32RelaySimulator().reset_camera(camera_id)
    return get_camera_status(camera_id)


def _stop_other_cameras(camera_id: str, statuses: dict[str, dict]) -> None:
    for other_id, status in statuses.items():
        if other_id == camera_id:
            continue
        if status.get("status") == "ACTIVE":
            _terminate_pid(status.get("pid"))
            statuses[other_id] = {"status": "IDLE", "pid": None, "last_update": utc_now()}
            _clear_camera_live_outputs(other_id)
            if other_id in {"camera_1", "camera_2"}:
                ESP32RelaySimulator().reset_camera(other_id)


def _append_worker_options(command: list[str], options: dict) -> None:
    flag_map = {
        "start_sec": "--start-sec",
        "end_sec": "--end-sec",
        "snapshot_every": "--snapshot-every",
        "event_cooldown_sec": "--event-cooldown-sec",
        "live_frame_width": "--live-frame-width",
        "inference_every": "--inference-every",
        "person_conf": "--person-conf",
        "ppe_conf": "--ppe-conf",
        "smoothing_window": "--smoothing-window",
        "no_helmet_confirm_frames": "--no-helmet-confirm-frames",
        "risk_alpha": "--risk-alpha",
        "alert_duration_sec": "--alert-duration-sec",
    }
    for key, flag in flag_map.items():
        value = options.get(key)
        if value is not None:
            command.extend([flag, str(value)])

    if options.get("save_video"):
        command.append("--save-video")
    if options.get("realtime_logs"):
        command.append("--realtime-logs")
    if options.get("loop_video"):
        command.append("--loop-video")


def start_camera(camera_id: str, max_frames: int | None = None) -> dict:
    if camera_id not in CAMERAS:
        raise ValueError(f"Unsupported camera: {camera_id}")
    if camera_id not in load_video_sources():
        raise ValueError(f"Camera missing in video_sources.yaml: {camera_id}")

    statuses = get_all_camera_statuses()
    current = statuses[camera_id]
    if current.get("status") == "ACTIVE" and is_pid_alive(current.get("pid")):
        return get_camera_status(camera_id)

    _stop_other_cameras(camera_id, statuses)
    options = dashboard_worker_settings()
    effective_max_frames = options.get("max_frames") if max_frames is None else max_frames

    command = [
        sys.executable,
        "-u",
        "-m",
        "src.demo.run_cctv_demo",
        "--camera",
        camera_id,
    ]
    _append_worker_options(command, options)
    if effective_max_frames and effective_max_frames > 0:
        command.extend(["--max-frames", str(effective_max_frames)])

    WORKER_LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = (WORKER_LOG_DIR / f"{camera_id}_worker.log").open("a", encoding="utf-8")
    process = subprocess.Popen(
        command,
        cwd=str(ROOT),
        stdout=log_file,
        stderr=log_file,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    log_file.close()
    statuses[camera_id] = {"status": "ACTIVE", "pid": process.pid, "last_update": utc_now()}
    _write_statuses(statuses)
    _write_active_camera(camera_id)
    return get_camera_status(camera_id)


def restart_camera(camera_id: str, max_frames: int | None = None) -> dict:
    stop_camera(camera_id)
    return start_camera(camera_id, max_frames=max_frames)


def activate_camera(camera_id: str, max_frames: int | None = None) -> dict:
    if camera_id not in CAMERAS:
        raise ValueError(f"Unsupported camera: {camera_id}")
    statuses = get_all_camera_statuses()
    _stop_other_cameras(camera_id, statuses)
    _terminate_pid(statuses[camera_id].get("pid"))
    statuses[camera_id] = {"status": "IDLE", "pid": None, "last_update": utc_now()}
    _write_statuses(statuses)
    _clear_camera_live_outputs(camera_id)
    _write_active_camera(camera_id)
    return start_camera(camera_id, max_frames=max_frames)
