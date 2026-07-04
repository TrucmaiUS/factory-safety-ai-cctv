"""Validate a YOLO-format dataset for the final 3-class PPE schema."""

from __future__ import annotations

import argparse
import logging
from collections import Counter
from pathlib import Path


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VALID_CLASS_IDS = {0, 1, 2}


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def validate_label_file(label_path: Path, class_counts: Counter[int]) -> list[str]:
    errors: list[str] = []
    try:
        lines = label_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError as exc:
        return [f"could not read {label_path}: {exc}"]

    if not lines:
        logging.warning("Empty label file: %s", label_path)
        return errors

    for line_number, line in enumerate(lines, start=1):
        parts = line.strip().split()
        if len(parts) != 5:
            errors.append(f"{label_path}:{line_number} expected 5 values, got {len(parts)}")
            continue
        try:
            class_id = int(parts[0])
            values = [float(value) for value in parts[1:]]
        except ValueError:
            errors.append(f"{label_path}:{line_number} contains non-numeric values")
            continue

        if class_id not in VALID_CLASS_IDS:
            errors.append(f"{label_path}:{line_number} invalid class id {class_id}")
        x_center, y_center, width, height = values
        if not all(0.0 <= value <= 1.0 for value in values):
            errors.append(f"{label_path}:{line_number} bbox values must be normalized in [0,1]")
        if width <= 0 or height <= 0:
            errors.append(f"{label_path}:{line_number} bbox width/height must be > 0")
        class_counts[class_id] += 1
    return errors


def validate_dataset(dataset_dir: Path) -> int:
    if not dataset_dir.exists():
        logging.error("Dataset directory does not exist: %s", dataset_dir)
        return 2

    class_counts: Counter[int] = Counter()
    critical_errors: list[str] = []
    image_files = sorted(path for path in dataset_dir.rglob("*") if path.suffix.lower() in IMAGE_EXTENSIONS)
    label_files = sorted(path for path in dataset_dir.rglob("*.txt") if "labels" in path.parts)

    if not image_files:
        logging.warning("No images found under %s", dataset_dir)
    if not label_files:
        logging.warning("No YOLO label files found under labels/ in %s", dataset_dir)

    for label_path in label_files:
        critical_errors.extend(validate_label_file(label_path, class_counts))

    label_lookup = {label_path.stem for label_path in label_files}
    images_without_labels = [path for path in image_files if path.stem not in label_lookup]
    for image_path in images_without_labels:
        logging.warning("Image without label file: %s", image_path)

    logging.info("Images: %d", len(image_files))
    logging.info("Label files: %d", len(label_files))
    logging.info("Images without labels: %d", len(images_without_labels))
    logging.info("Class distribution: %s", dict(sorted(class_counts.items())))

    if critical_errors:
        for error in critical_errors[:50]:
            logging.error("%s", error)
        if len(critical_errors) > 50:
            logging.error("... and %d more validation errors", len(critical_errors) - 50)
        return 1
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate YOLO dataset labels.")
    parser.add_argument("--dataset-dir", required=True, type=Path, help="Dataset root containing images/ and labels/.")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging(args.verbose)
    return validate_dataset(args.dataset_dir)


if __name__ == "__main__":
    raise SystemExit(main())
