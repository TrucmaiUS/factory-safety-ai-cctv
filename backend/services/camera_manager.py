from backend.services.output_reader import CAMERA_NAMES, CAMERA_ROLES, CAMERAS, load_video_sources, read_latest_event
from backend.services.process_manager import get_all_camera_statuses


def list_camera_infos() -> list[dict]:
    statuses = get_all_camera_statuses()
    sources = load_video_sources()
    return [
        {
            "camera_id": camera_id,
            "name": CAMERA_NAMES[camera_id],
            "role": CAMERA_ROLES[camera_id],
            "status": statuses[camera_id]["status"],
            "pid": statuses[camera_id].get("pid"),
            "source": sources.get(camera_id, {}).get("source"),
            "latest_event": read_latest_event(camera_id),
            "latest_frame_url": f"/api/cameras/{camera_id}/frame",
        }
        for camera_id in CAMERAS
    ]
