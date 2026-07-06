from pathlib import Path

import cv2
import numpy as np
import yaml


ROOT = Path(__file__).resolve().parents[1]

CONFIG_PATH = ROOT / "src" / "configs" / "camera_zones.yaml"
VIDEOS = {
    "camera_1": ROOT / "video_source" / "camera_1" / "cam1.mp4",
    "camera_2": ROOT / "video_source" / "camera_2" / "cam2.mp4",
}

OUT_DIR = ROOT / "outputs" / "zone_preview"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PREFERRED_FRAME_INDEX = 100


def require_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")


def default_polygon(width: int, height: int) -> list[list[int]]:
    return [
        [int(width * 0.58), int(height * 0.35)],
        [int(width * 0.93), int(height * 0.38)],
        [int(width * 0.96), int(height * 0.92)],
        [int(width * 0.62), int(height * 0.92)],
        [int(width * 0.52), int(height * 0.62)],
    ]


def load_config() -> dict:
    require_file(CONFIG_PATH)
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def read_preview_frame(video_path: Path) -> tuple[np.ndarray, int]:
    require_file(video_path)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    target = PREFERRED_FRAME_INDEX if total_frames > PREFERRED_FRAME_INDEX else 0

    cap.set(cv2.CAP_PROP_POS_FRAMES, target)
    ok, frame = cap.read()

    if not ok and target != 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ok, frame = cap.read()
        target = 0

    cap.release()

    if not ok:
        raise RuntimeError(f"Cannot read preview frame from: {video_path}")

    return frame, target


def zone_points(camera_id: str, config: dict, width: int, height: int) -> tuple[list[list[int]], str]:
    camera_config = config.get(camera_id, {}) or {}
    danger_zone = camera_config.get("danger_zone", {}) or {}
    points = danger_zone.get("points") or []
    zone_name = danger_zone.get("name") or "demo_default_zone"

    if not points:
        print(f"WARNING: {camera_id} has empty danger_zone.points, using default demo polygon")
        return default_polygon(width, height), zone_name

    return points, zone_name


def draw_zone(frame: np.ndarray, points: list[list[int]], camera_id: str, zone_name: str) -> np.ndarray:
    annotated = frame.copy()
    polygon = np.array(points, dtype=np.int32).reshape((-1, 1, 2))

    overlay = annotated.copy()
    cv2.fillPoly(overlay, [polygon], (0, 0, 255))
    cv2.addWeighted(overlay, 0.22, annotated, 0.78, 0, annotated)

    cv2.polylines(annotated, [polygon], isClosed=True, color=(0, 0, 255), thickness=4)
    for idx, point in enumerate(points, start=1):
        x, y = int(point[0]), int(point[1])
        cv2.circle(annotated, (x, y), 6, (255, 255, 255), -1)
        cv2.putText(
            annotated,
            str(idx),
            (x + 8, y - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

    cv2.putText(
        annotated,
        f"{camera_id} danger zone: {zone_name}",
        (24, 42),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (0, 0, 255),
        3,
        cv2.LINE_AA,
    )

    return annotated


def main() -> None:
    config = load_config()

    for camera_id, video_path in VIDEOS.items():
        frame, frame_index = read_preview_frame(video_path)
        height, width = frame.shape[:2]
        points, zone_name = zone_points(camera_id, config, width, height)
        annotated = draw_zone(frame, points, camera_id, zone_name)

        out_path = OUT_DIR / f"{camera_id}_zone_frame_{frame_index}.jpg"
        cv2.imwrite(str(out_path), annotated)

        print(
            f"{camera_id}: frame={frame_index}, "
            f"points={len(points)}, saved={out_path}"
        )

    print(f"\nZone preview images saved to: {OUT_DIR}")


if __name__ == "__main__":
    main()
