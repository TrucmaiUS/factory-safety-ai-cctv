from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_command_id() -> str:
    return f"cmd_{uuid4().hex[:12]}"


@dataclass
class DeviceCommand:
    command_id: str
    timestamp: str
    source: str
    camera_id: str
    device_id: str
    risk_score: int
    severity: str
    command: dict[str, str]
    reasons: list[str]
    actions: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DeviceAck:
    timestamp: str
    device_id: str
    command_id: str
    status: str
    message: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DeviceState:
    device_id: str
    camera_id: str
    connection: str
    relay: str
    buzzer: str
    warning_light: str
    last_command_id: str | None
    last_update: str | None

    def to_dict(self) -> dict:
        return asdict(self)


def command_from_event(camera_id: str, device_id: str, event: dict) -> DeviceCommand:
    actions = set(event.get("actions", []))
    return DeviceCommand(
        command_id=new_command_id(),
        timestamp=utc_now(),
        source="ai_risk_pipeline",
        camera_id=camera_id,
        device_id=device_id,
        risk_score=int(event.get("risk_score", 0)),
        severity=str(event.get("severity", "normal")),
        command={
            "relay": "ON" if "relay_on" in actions else "N/A",
            "buzzer": "ON" if "buzzer_on" in actions else "N/A",
            "warning_light": "ON" if "warning_light_on" in actions else "N/A",
        },
        reasons=list(event.get("reasons", [])),
        actions=list(event.get("actions", [])),
    )
