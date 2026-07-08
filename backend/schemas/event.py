from pydantic import BaseModel


class EventRecord(BaseModel):
    timestamp: str | None = None
    camera_id: str | None = None
    track_id: int | None = None
    risk_score: int | None = None
    severity: str | None = None
    reasons: list[str] | None = None
    actions: list[str] | None = None
    is_fresh: bool | None = None
    age_seconds: float | None = None
