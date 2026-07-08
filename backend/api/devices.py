from fastapi import APIRouter, Query

from backend.services.output_reader import read_device_commands, read_device_status
from src.iot.command_bus import COMMANDS_PATH
from src.iot.device_simulator import ESP32RelaySimulator


router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.get("/status")
def device_status() -> dict:
    simulator = ESP32RelaySimulator()
    return simulator.state or read_device_status()


@router.get("/commands")
def device_commands(limit: int = Query(default=50, ge=1, le=500)) -> list[dict]:
    return read_device_commands(limit)


@router.post("/reset")
def reset_devices() -> dict:
    simulator = ESP32RelaySimulator()
    for camera_id in ("camera_1", "camera_2", "camera_3"):
        simulator.reset_camera(camera_id)
    if not COMMANDS_PATH.exists():
        COMMANDS_PATH.parent.mkdir(parents=True, exist_ok=True)
        COMMANDS_PATH.touch()
    return simulator.state
