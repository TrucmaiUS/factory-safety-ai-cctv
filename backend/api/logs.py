from fastapi import APIRouter, Query

from backend.services.output_reader import read_serial_tail


router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("/serial")
def serial_logs(
    tail: int = Query(default=100, ge=1, le=1000),
    camera_id: str | None = None,
) -> dict:
    return {"lines": read_serial_tail(tail=tail, camera_id=camera_id)}
