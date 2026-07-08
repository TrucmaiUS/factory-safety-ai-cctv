import json
import os
from pathlib import Path

from src.iot.command_schema import DeviceAck, DeviceState, utc_now
from src.iot.serial_logger import serial_log


ROOT = Path(__file__).resolve().parents[2]
DEVICE_STATUS_PATH = ROOT / "outputs" / "device_status.json"

DEVICE_IDS = {
    "camera_1": "ESP32_SIM_CAM1",
    "camera_2": "ESP32_SIM_CAM2",
    "camera_3": "UI_ONLY_CAM3",
}


def default_state() -> dict[str, dict]:
    return {
        "camera_1": DeviceState(
            device_id="ESP32_SIM_CAM1",
            camera_id="camera_1",
            connection="SIMULATED",
            relay="OFF",
            buzzer="OFF",
            warning_light="OFF",
            last_command_id=None,
            last_update=None,
        ).to_dict(),
        "camera_2": DeviceState(
            device_id="ESP32_SIM_CAM2",
            camera_id="camera_2",
            connection="SIMULATED",
            relay="OFF",
            buzzer="OFF",
            warning_light="OFF",
            last_command_id=None,
            last_update=None,
        ).to_dict(),
        "camera_3": DeviceState(
            device_id="UI_ONLY_CAM3",
            camera_id="camera_3",
            connection="SIMULATED",
            relay="N/A",
            buzzer="N/A",
            warning_light="N/A",
            last_command_id=None,
            last_update=None,
        ).to_dict(),
    }


class ESP32RelaySimulator:
    def __init__(self, status_path: Path | str = DEVICE_STATUS_PATH) -> None:
        self.status_path = Path(status_path)
        self.state = self.load_state()

    def load_state(self) -> dict[str, dict]:
        if not self.status_path.exists():
            state = default_state()
            self.state = state
            self.save_state()
            return state

        try:
            loaded = json.loads(self.status_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            loaded = {}

        state = default_state()
        for camera_id, camera_state in loaded.items():
            if camera_id in state and isinstance(camera_state, dict):
                state[camera_id].update(camera_state)
        return state

    def save_state(self) -> None:
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.status_path.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, self.status_path)

    def reset_camera(self, camera_id: str) -> None:
        self.state[camera_id] = default_state()[camera_id]
        self.state[camera_id]["last_update"] = utc_now()
        self.save_state()
        serial_log(f"[SYSTEM] {camera_id} reset to IDLE device state.")

    def handle_command(self, command: dict) -> dict:
        camera_id = command.get("camera_id")
        command_id = command.get("command_id")
        device_id = command.get("device_id", DEVICE_IDS.get(camera_id, "UNKNOWN_DEVICE"))

        if camera_id not in self.state:
            ack = DeviceAck(
                timestamp=utc_now(),
                device_id=device_id,
                command_id=command_id,
                status="ERROR",
                message=f"Unknown camera: {camera_id}",
            ).to_dict()
            serial_log(f"[{device_id}] ERROR command {command_id}: unknown camera")
            return ack

        device_command = command.get("command", {})
        camera_state = self.state[camera_id]
        for key in ("relay", "buzzer", "warning_light"):
            value = device_command.get(key, "N/A")
            if value in {"ON", "OFF"} and camera_state.get(key) != "N/A":
                camera_state[key] = value

        camera_state["last_command_id"] = command_id
        camera_state["last_update"] = utc_now()
        self.save_state()

        ack = DeviceAck(
            timestamp=utc_now(),
            device_id=device_id,
            command_id=command_id,
            status="ACK",
            message="Command applied",
        ).to_dict()

        serial_log(f"[{device_id}] ACK command {command_id}")
        serial_log(
            "[DEVICE] "
            f"RELAY {camera_state['relay']} | "
            f"BUZZER {camera_state['buzzer']} | "
            f"WARNING LIGHT {camera_state['warning_light']}"
        )
        return ack
