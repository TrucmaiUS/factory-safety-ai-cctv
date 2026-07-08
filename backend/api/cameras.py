import asyncio

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse

from backend.services.camera_manager import list_camera_infos
from backend.services import process_manager
from backend.services.output_reader import (
    CAMERAS,
    latest_frame_path,
    video_path,
)


router = APIRouter(prefix="/api/cameras", tags=["cameras"])


def _no_cache(response: FileResponse) -> FileResponse:
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


def _placeholder_jpeg(camera_id: str) -> bytes:
    frame = np.zeros((540, 960, 3), dtype=np.uint8)
    cv2.putText(
        frame,
        f"{camera_id} waiting for live frame",
        (90, 270),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (220, 230, 235),
        2,
        cv2.LINE_AA,
    )
    ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 78])
    return encoded.tobytes() if ok else b""


@router.get("")
def list_cameras() -> list[dict]:
    return list_camera_infos()


@router.get("/{camera_id}/status")
def camera_status(camera_id: str) -> dict:
    try:
        return process_manager.get_camera_status(camera_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{camera_id}/start")
def start_camera(camera_id: str, max_frames: int = Query(default=0, ge=0, le=200000)) -> dict:
    try:
        return process_manager.start_camera(camera_id, max_frames=max_frames)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{camera_id}/stop")
def stop_camera(camera_id: str) -> dict:
    try:
        return process_manager.stop_camera(camera_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{camera_id}/restart")
def restart_camera(camera_id: str, max_frames: int = Query(default=0, ge=0, le=200000)) -> dict:
    try:
        return process_manager.restart_camera(camera_id, max_frames=max_frames)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{camera_id}/activate")
def activate_camera(camera_id: str, max_frames: int = Query(default=0, ge=0, le=200000)) -> dict:
    try:
        return process_manager.activate_camera(camera_id, max_frames=max_frames)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{camera_id}/frame")
def latest_frame(camera_id: str) -> FileResponse:
    path = latest_frame_path(camera_id)
    if camera_id not in CAMERAS or not path.exists():
        raise HTTPException(status_code=404, detail="Latest frame not found")
    return _no_cache(FileResponse(path, media_type="image/jpeg"))


@router.get("/{camera_id}/mjpeg")
async def mjpeg_stream(camera_id: str, request: Request) -> StreamingResponse:
    if camera_id not in CAMERAS:
        raise HTTPException(status_code=404, detail=f"Unknown camera: {camera_id}")

    frame_path = latest_frame_path(camera_id)
    placeholder = _placeholder_jpeg(camera_id)

    async def generate():
        last_mtime_ns: int | None = None
        placeholder_sent = False
        while True:
            try:
                if await request.is_disconnected():
                    break

                frame_bytes: bytes | None = None
                if frame_path.exists():
                    stat = frame_path.stat()
                    if stat.st_size > 0 and stat.st_mtime_ns != last_mtime_ns:
                        frame_bytes = frame_path.read_bytes()
                        last_mtime_ns = stat.st_mtime_ns
                elif placeholder and not placeholder_sent:
                    frame_bytes = placeholder
                    placeholder_sent = True

                if frame_bytes:
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        + f"Content-Length: {len(frame_bytes)}\r\n\r\n".encode("utf-8")
                        + frame_bytes
                        + b"\r\n"
                    )
            except asyncio.CancelledError:
                break
            except (ConnectionError, BrokenPipeError):
                break
            except Exception:
                pass

            await asyncio.sleep(0.08)

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@router.get("/{camera_id}/video")
def processed_video(camera_id: str) -> FileResponse:
    path = video_path(camera_id)
    if camera_id not in CAMERAS or not path.exists():
        raise HTTPException(status_code=404, detail="Processed video not found")
    return _no_cache(FileResponse(path, media_type="video/mp4"))
