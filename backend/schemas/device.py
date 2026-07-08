from pydantic import BaseModel


class DeviceStatus(BaseModel):
    device_id: str
    camera_id: str
    connection: str
    relay: str
    buzzer: str
    warning_light: str
    last_command_id: str | None = None
    last_update: str | None = None
