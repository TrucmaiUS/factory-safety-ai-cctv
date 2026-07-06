from pathlib import Path

import numpy as np
from ultralytics import YOLO

from src.perception.detection_types import DetectionBox


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_PATH = ROOT / "model" / "ppe" / "yolo8s_ppe_best.pt"


def is_helmet(label: str) -> bool:
    normalized = label.lower().replace("_", " ").replace("-", " ")
    return "helmet" in normalized or "hardhat" in normalized or "hard hat" in normalized


def is_head(label: str) -> bool:
    normalized = label.lower().replace("_", " ").replace("-", " ")
    return "head" in normalized and not is_helmet(normalized)


class PPEDetector:
    def __init__(self, model_path: Path | str = DEFAULT_MODEL_PATH, device: str | None = None) -> None:
        self.model_path = Path(model_path)
        if not self.model_path.exists():
            raise FileNotFoundError(f"PPE model not found: {self.model_path}")

        self.model = YOLO(str(self.model_path))
        self.device = device

    def detect(self, frame: np.ndarray, conf: float = 0.25) -> list[DetectionBox]:
        predict_kwargs = {
            "source": frame,
            "conf": conf,
            "verbose": False,
        }
        if self.device:
            predict_kwargs["device"] = self.device

        result = self.model.predict(**predict_kwargs)[0]
        boxes = result.boxes
        if boxes is None:
            return []

        detections: list[DetectionBox] = []
        for box in boxes:
            cls_id = int(box.cls[0])
            label = str(self.model.names.get(cls_id, cls_id))
            if not (is_helmet(label) or is_head(label)):
                continue

            x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
            detections.append(
                DetectionBox(
                    x1=x1,
                    y1=y1,
                    x2=x2,
                    y2=y2,
                    conf=float(box.conf[0]),
                    cls_id=cls_id,
                    label=label,
                    source_model="ppe_yolov8s",
                )
            )

        return detections
