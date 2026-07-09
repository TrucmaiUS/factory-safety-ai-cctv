from typing import Any

from src.iot.command_bus import publish_command
from src.iot.command_schema import command_from_event
from src.iot.device_simulator import DEVICE_IDS, ESP32RelaySimulator
from src.iot.serial_logger import serial_log
from src.safety.history_logger import HistoryLogger
from src.safety.simple_tracker import TrackState


class ActionEngine:
    def __init__(
        self,
        history_logger: HistoryLogger | None = None,
        simulator: ESP32RelaySimulator | None = None,
        realtime_logs: bool = False,
    ) -> None:
        self.history_logger = history_logger or HistoryLogger()
        self.simulator = simulator or ESP32RelaySimulator()
        self.realtime_logs = realtime_logs

    def handle_event(
        self,
        camera_id: str,
        risk: dict[str, Any],
        track: TrackState | None = None,
        zone_name: str | None = None,
        zone_points: list[list[int]] | None = None,
        helmet_state: dict[str, Any] | None = None,
        bbox: Any | None = None,
        snapshot_frame: Any | None = None,
    ) -> dict[str, Any]:
        actions = set(risk.get("actions", []))
        result = {
            "saved_history": False,
            "device_command_sent": False,
            "ack": None,
            "device_state": None,
        }

        event = None
        snapshot_path = self.history_logger.save_snapshot(
            camera_id=camera_id,
            frame=snapshot_frame,
            track_id=track.track_id if track else None,
            risk=risk,
            track=track,
            helmet_state=helmet_state,
            bbox=bbox,
            zone_points=zone_points,
            zone_name=zone_name,
        ) if "save_history" in actions else None

        if "save_history" in actions:
            event = self.history_logger.log_event(
                camera_id=camera_id,
                risk=risk,
                track=track,
                zone_name=zone_name,
                helmet_state=helmet_state,
                bbox=bbox,
                snapshot_path=snapshot_path,
            )
            result["saved_history"] = True

        if "ui_warning" in actions:
            latest_event = event or self.history_logger.build_event(
                camera_id=camera_id,
                risk=risk,
                track=track,
                zone_name=zone_name,
                helmet_state=helmet_state,
                bbox=bbox,
                snapshot_path=snapshot_path,
            )
            self.history_logger.write_latest_event(camera_id, latest_event)

        reasons = ", ".join(risk.get("reasons", [])) or "none"
        if self.realtime_logs:
            serial_log(
                f"[AI] {camera_id} | Risk {risk.get('risk_score', 0)}/100 "
                f"{str(risk.get('severity', 'normal')).upper()} | {reasons}"
            )

        needs_device_command = bool(actions & {"relay_on", "buzzer_on", "warning_light_on"})
        if needs_device_command:
            device_id = DEVICE_IDS.get(camera_id, f"ESP32_SIM_{camera_id.upper()}")
            command = command_from_event(camera_id, device_id, risk).to_dict()
            publish_command(command)
            result["device_command_sent"] = True

            cmd = command["command"]
            serial_log(
                f"[CMD] {camera_id} -> {device_id}: "
                f"RELAY={cmd['relay']}, BUZZER={cmd['buzzer']}, LIGHT={cmd['warning_light']}"
            )
            ack = self.simulator.handle_command(command)
            result["ack"] = ack
            result["device_state"] = self.simulator.state.get(camera_id)
        elif camera_id == "camera_3" and "ui_warning" in actions:
            serial_log("[UI] Camera 3 helmet-only warning; no relay command required.")

        return result
