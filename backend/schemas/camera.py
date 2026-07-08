from pydantic import BaseModel


class CameraInfo(BaseModel):
    camera_id: str
    name: str
    role: str
    status: str
    source: str
    latest_frame_url: str


class CameraStatus(BaseModel):
    camera_id: str
    status: str
    pid: int | None = None
    last_update: str | None = None
    latest_event: dict | None = None
