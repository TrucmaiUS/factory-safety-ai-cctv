from pathlib import Path

import cv2
import numpy as np
import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = ROOT / "src" / "configs" / "camera_zones.yaml"


def default_demo_polygon(width: int = 2048, height: int = 1152) -> list[list[int]]:
    return [
        [int(width * 0.58), int(height * 0.35)],
        [int(width * 0.93), int(height * 0.38)],
        [int(width * 0.96), int(height * 0.92)],
        [int(width * 0.62), int(height * 0.92)],
        [int(width * 0.52), int(height * 0.62)],
    ]


class ZoneChecker:
    def __init__(self, config_path: Path | str = DEFAULT_CONFIG_PATH) -> None:
        self.config_path = Path(config_path)
        if not self.config_path.exists():
            raise FileNotFoundError(f"Camera zones config not found: {self.config_path}")

        with self.config_path.open("r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f) or {}

    def get_zone(self, camera_id: str) -> dict:
        camera_config = self.config.get(camera_id, {}) or {}
        danger_zone = camera_config.get("danger_zone", {}) or {}
        points = danger_zone.get("points") or []
        name = danger_zone.get("name") or "demo_default_zone"

        if not points:
            print(f"WARNING: {camera_id} has empty danger_zone.points, using default demo polygon")
            points = default_demo_polygon()

        return {
            "name": name,
            "points": points,
            "zone_type": camera_config.get("zone_type", "polygon"),
        }


def get_zone(camera_id: str) -> dict:
    return ZoneChecker().get_zone(camera_id)


def is_point_inside_zone(point: tuple[float, float], points: list[list[int]]) -> bool:
    if not points:
        return False

    polygon = np.array(points, dtype=np.float32)
    return cv2.pointPolygonTest(polygon, point, False) >= 0


def draw_zone(frame: np.ndarray, points: list[list[int]], label: str) -> np.ndarray:
    if not points:
        h, w = frame.shape[:2]
        print("WARNING: empty zone points, using default demo polygon")
        points = default_demo_polygon(w, h)

    annotated = frame.copy()
    polygon = np.array(points, dtype=np.int32).reshape((-1, 1, 2))

    overlay = annotated.copy()
    cv2.fillPoly(overlay, [polygon], (0, 0, 255))
    cv2.addWeighted(overlay, 0.20, annotated, 0.80, 0, annotated)

    cv2.polylines(annotated, [polygon], isClosed=True, color=(0, 0, 255), thickness=3)
    cv2.putText(
        annotated,
        label,
        tuple(polygon[0][0]),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.85,
        (0, 0, 255),
        2,
        cv2.LINE_AA,
    )
    return annotated
