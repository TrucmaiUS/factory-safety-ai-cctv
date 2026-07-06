from pathlib import Path
import cv2

ROOT = Path(__file__).resolve().parents[1]

JOBS = {
    "camera_1": ROOT / "video_source" / "camera_1" / "cam1.mp4",
    "camera_2": ROOT / "video_source" / "camera_2" / "cam2.mp4",
}

OUT_DIR = ROOT / "outputs" / "zone_samples"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def extract_frame(camera_id: str, video_path: Path, frame_index: int = 100):
    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    target = min(frame_index, max(total - 1, 0))

    cap.set(cv2.CAP_PROP_POS_FRAMES, target)
    ok, frame = cap.read()
    cap.release()

    if not ok:
        raise RuntimeError(f"Cannot read frame {target} from {video_path}")

    out_path = OUT_DIR / f"{camera_id}_frame_{target}.jpg"
    cv2.imwrite(str(out_path), frame)
    print(f"Saved: {out_path}")


def main():
    for camera_id, video_path in JOBS.items():
        extract_frame(camera_id, video_path, frame_index=100)


if __name__ == "__main__":
    main()