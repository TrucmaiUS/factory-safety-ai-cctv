from fastapi import APIRouter, Query

from backend.services.output_reader import CAMERAS, read_latest_events, read_recent_events


router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("/recent")
def recent_events(
    limit: int = Query(default=100, ge=1, le=1000),
    camera_id: str | None = None,
    severity: str | None = None,
) -> list[dict]:
    return read_recent_events(limit=limit, camera_id=camera_id, severity=severity)


@router.get("/latest")
def latest_events(ttl_seconds: float = Query(default=30.0, ge=1.0, le=3600.0)) -> dict:
    latest = read_latest_events(ttl_seconds=ttl_seconds)
    return {camera_id: latest.get(camera_id) for camera_id in CAMERAS}
