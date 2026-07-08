import asyncio

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from backend.services.output_reader import (
    CAMERAS,
    read_device_status,
    read_latest_events,
    read_person_status,
    read_serial_tail,
    utc_now,
)
from backend.services.process_manager import get_all_camera_statuses


def build_dashboard_payload() -> dict:
    statuses = get_all_camera_statuses()
    latest_events = read_latest_events()
    return {
        "type": "dashboard_update",
        "timestamp": utc_now(),
        "cameras": {
            camera_id: {
                "status": statuses[camera_id]["status"],
                "pid": statuses[camera_id].get("pid"),
                        "latest_event": latest_events.get(camera_id),
                        "person_status": read_person_status(camera_id),
                        "latest_frame_url": f"/api/cameras/{camera_id}/frame?ts={utc_now()}",
            }
            for camera_id in CAMERAS
        },
        "device_status": read_device_status(),
        "serial_tail": read_serial_tail(80),
    }


async def live_updates(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        while True:
            try:
                if (
                    websocket.client_state != WebSocketState.CONNECTED
                    or websocket.application_state != WebSocketState.CONNECTED
                ):
                    break
                await websocket.send_json(build_dashboard_payload())
            except WebSocketDisconnect:
                break
            except RuntimeError:
                break
            except Exception:
                break
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        return
