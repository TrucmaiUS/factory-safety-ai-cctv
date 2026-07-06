from pathlib import Path

import cv2
from ultralytics import YOLO


ROOT = Path(__file__).resolve().parents[1]

PERSON_MODEL_PATH = ROOT / "model" / "person" / "yolov8s.pt"
PPE_MODEL_PATH = ROOT / "model" / "ppe" / "yolo8s_ppe_best.pt"

VIDEOS = {
    "camera_1": ROOT / "video_source" / "camera_1" / "cam1.mp4",
    "camera_2": ROOT / "video_source" / "camera_2" / "cam2.mp4",
    "camera_3": ROOT / "video_source" / "camera_3" / "cam3.mp4",
}

OUT_DIR = ROOT / "outputs" / "smoke_tests"
OUT_DIR.mkdir(parents=True, exist_ok=True)

MAX_FRAMES_PER_VIDEO = 10
PERSON_CONF = 0.35
PPE_CONF = 0.25


def require_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Missing required file: {path}")


def evenly_spaced_indices(total_frames: int, max_frames: int) -> list[int]:
    if total_frames <= 0:
        return list(range(max_frames))

    sample_count = min(max_frames, total_frames)
    if sample_count == 1:
        return [0]

    return sorted(
        {
            round(i * (total_frames - 1) / (sample_count - 1))
            for i in range(sample_count)
        }
    )


def class_name(names: dict | list, class_id: int) -> str:
    if isinstance(names, dict):
        return str(names.get(class_id, class_id))
    if 0 <= class_id < len(names):
        return str(names[class_id])
    return str(class_id)


def is_helmet_label(label: str) -> bool:
    normalized = label.lower().replace("_", " ").replace("-", " ")
    return "helmet" in normalized or "hardhat" in normalized or "hard hat" in normalized


def is_head_label(label: str) -> bool:
    normalized = label.lower().replace("_", " ").replace("-", " ")
    return "head" in normalized and not is_helmet_label(normalized)


def draw_result_boxes(frame, result, names, color, prefix: str) -> None:
    boxes = result.boxes
    if boxes is None:
        return

    for box in boxes:
        x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
        cls_id = int(box.cls[0])
        conf = float(box.conf[0])
        label = f"{prefix}:{class_name(names, cls_id)} {conf:.2f}"

        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(
            frame,
            label,
            (x1, max(y1 - 6, 16)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            2,
            cv2.LINE_AA,
        )


def count_ppe(result, names) -> tuple[int, int]:
    helmet_count = 0
    head_count = 0

    boxes = result.boxes
    if boxes is None:
        return helmet_count, head_count

    for box in boxes:
        label = class_name(names, int(box.cls[0]))
        if is_helmet_label(label):
            helmet_count += 1
        if is_head_label(label):
            head_count += 1

    return helmet_count, head_count


def read_frame(cap: cv2.VideoCapture, index: int):
    cap.set(cv2.CAP_PROP_POS_FRAMES, index)
    ok, frame = cap.read()
    if ok:
        return frame
    return None


def run_video(camera_id: str, video_path: Path, person_model: YOLO, ppe_model: YOLO) -> None:
    require_file(video_path)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_indices = evenly_spaced_indices(total_frames, MAX_FRAMES_PER_VIDEO)

    print(f"\n[{camera_id}] {video_path}")
    print(f"  total_frames={total_frames}, sampled_frames={len(frame_indices)}")

    totals = {"person": 0, "helmet": 0, "head": 0}

    for frame_index in frame_indices:
        frame = read_frame(cap, frame_index)
        if frame is None:
            print(f"  WARNING: cannot read frame {frame_index}, skipped")
            continue

        person_result = person_model.predict(
            source=frame,
            classes=[0],
            conf=PERSON_CONF,
            device="cpu",
            verbose=False,
        )[0]
        ppe_result = ppe_model.predict(
            source=frame,
            conf=PPE_CONF,
            device="cpu",
            verbose=False,
        )[0]

        person_count = 0 if person_result.boxes is None else len(person_result.boxes)
        helmet_count, head_count = count_ppe(ppe_result, ppe_model.names)

        totals["person"] += person_count
        totals["helmet"] += helmet_count
        totals["head"] += head_count

        annotated = frame.copy()
        draw_result_boxes(annotated, person_result, person_model.names, (0, 180, 255), "person")
        draw_result_boxes(annotated, ppe_result, ppe_model.names, (70, 220, 70), "ppe")

        out_path = OUT_DIR / f"{camera_id}_frame_{frame_index:06d}.jpg"
        cv2.imwrite(str(out_path), annotated)

        print(
            f"  frame={frame_index:06d}: "
            f"person={person_count}, helmet={helmet_count}, head={head_count} -> {out_path.name}"
        )

    cap.release()

    print(
        f"  summary: person={totals['person']}, "
        f"helmet={totals['helmet']}, head={totals['head']}"
    )


def main() -> None:
    require_file(PERSON_MODEL_PATH)
    require_file(PPE_MODEL_PATH)

    print("Loading models on CPU...")
    person_model = YOLO(str(PERSON_MODEL_PATH))
    ppe_model = YOLO(str(PPE_MODEL_PATH))

    print(f"Person classes: {person_model.names}")
    print(f"PPE classes: {ppe_model.names}")

    for camera_id, video_path in VIDEOS.items():
        run_video(camera_id, video_path, person_model, ppe_model)

    print(f"\nAnnotated images saved to: {OUT_DIR}")


if __name__ == "__main__":
    main()
