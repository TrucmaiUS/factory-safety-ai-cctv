from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from backend.api import cameras, devices, events, logs
from backend.services.output_reader import (
    ALERT_HISTORY_PATH,
    CONTROL_DIR,
    DEVICE_COMMANDS_PATH,
    DEVICE_STATUS_PATH,
    DEMO_VIDEO_DIR,
    LIVE_DIR,
    SERIAL_LOG_PATH,
    write_json,
)
from backend.services.process_manager import default_statuses, stop_camera
from backend.services.websocket_manager import live_updates
from src.iot.device_simulator import ESP32RelaySimulator


app = FastAPI(title="Factory Safety AI Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(cameras.router)
app.include_router(events.router)
app.include_router(devices.router)
app.include_router(logs.router)


@app.on_event("startup")
def startup() -> None:
    clear_runtime_state(clear_history=True, clear_live_frames=True)


@app.on_event("shutdown")
def shutdown() -> None:
    clear_runtime_state(clear_history=True, clear_live_frames=True)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "factory-safety-ai-backend"}


@app.websocket("/ws/live")
async def websocket_live(websocket: WebSocket) -> None:
    await live_updates(websocket)


def _clear_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("", encoding="utf-8")


def clear_runtime_state(
    clear_history: bool = True,
    clear_live_frames: bool = True,
    clear_demo_videos: bool = False,
) -> None:
    for camera_id in ("camera_1", "camera_2", "camera_3"):
        try:
            stop_camera(camera_id)
        except ValueError:
            pass

    for path in LIVE_DIR.glob("*_latest_event.json"):
        path.unlink(missing_ok=True)
    for path in LIVE_DIR.glob("*_person_status.json"):
        path.unlink(missing_ok=True)
    if clear_live_frames:
        for path in LIVE_DIR.glob("*_latest.jpg"):
            path.unlink(missing_ok=True)
        for path in LIVE_DIR.glob("*_latest.tmp.jpg"):
            path.unlink(missing_ok=True)
        for path in LIVE_DIR.glob("*_latest.jpg.*.tmp.jpg"):
            path.unlink(missing_ok=True)
    for path in LIVE_DIR.glob("*.json.*.json.tmp"):
        path.unlink(missing_ok=True)
    if clear_demo_videos:
        for path in DEMO_VIDEO_DIR.glob("*_output.mp4"):
            path.unlink(missing_ok=True)

    (CONTROL_DIR / "active_camera.json").unlink(missing_ok=True)
    write_json(CONTROL_DIR / "camera_process_status.json", default_statuses())
    DEVICE_STATUS_PATH.unlink(missing_ok=True)
    ESP32RelaySimulator()
    _clear_file(DEVICE_COMMANDS_PATH)
    _clear_file(SERIAL_LOG_PATH)
    if clear_history:
        _clear_file(ALERT_HISTORY_PATH)


@app.post("/api/system/reset-realtime-state")
def reset_realtime_state(clear_history: bool = True) -> dict:
    clear_runtime_state(clear_history=clear_history, clear_live_frames=True)
    return {"status": "ok", "clear_history": clear_history}
