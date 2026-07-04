"""Split a YOLO-format image/label folder into train/val/test subsets."""

from __future__ import annotations

import argparse
import logging
import random
import shutil
from pathlib import Path


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
DEFAULT_OUTPUT_DIR = Path("data/processed/ppe_yolo")


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def parse_split(value: str) -> tuple[float, float, float]:
    try:
        parts = [float(part) for part in value.split(",")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Split must be numeric, e.g. 0.7,0.2,0.1") from exc
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("Split must have three values: train,val,test")
    if any(part < 0 for part in parts):
        raise argparse.ArgumentTypeError("Split values must be non-negative")
    total = sum(parts)
    if abs(total - 1.0) > 1e-6:
        raise argparse.ArgumentTypeError("Split values must sum to 1.0")
    return parts[0], parts[1], parts[2]


def prepare_output_dirs(output_dir: Path, overwrite: bool) -> int:
    subdirs = [
        output_dir / "images" / subset for subset in ("train", "val", "test")
    ] + [
        output_dir / "labels" / subset for subset in ("train", "val", "test")
    ]
    existing_files = [path for subdir in subdirs if subdir.exists() for path in subdir.iterdir() if path.is_file()]
    if existing_files and not overwrite:
        logging.error("Processed output already contains files. Use --overwrite to replace them.")
        return 2
    if overwrite:
        for subdir in subdirs:
            if subdir.exists():
                shutil.rmtree(subdir)
    for subdir in subdirs:
        subdir.mkdir(parents=True, exist_ok=True)
    return 0


def split_items(items: list[Path], split: tuple[float, float, float]) -> dict[str, list[Path]]:
    train_ratio, val_ratio, _test_ratio = split
    train_end = int(len(items) * train_ratio)
    val_end = train_end + int(len(items) * val_ratio)
    return {
        "train": items[:train_end],
        "val": items[train_end:val_end],
        "test": items[val_end:],
    }


def split_dataset(
    images_dir: Path,
    labels_dir: Path,
    output_dir: Path,
    split: tuple[float, float, float],
    seed: int,
    overwrite: bool,
) -> int:
    if not images_dir.exists():
        logging.error("Images directory does not exist: %s", images_dir)
        return 2
    if not labels_dir.exists():
        logging.warning("Labels directory does not exist: %s", labels_dir)

    status = prepare_output_dirs(output_dir, overwrite)
    if status != 0:
        return status

    image_files = sorted(path for path in images_dir.rglob("*") if path.suffix.lower() in IMAGE_EXTENSIONS)
    if not image_files:
        logging.warning("No images found under %s", images_dir)
        return 0

    rng = random.Random(seed)
    rng.shuffle(image_files)
    subsets = split_items(image_files, split)

    missing_labels = 0
    for subset, files in subsets.items():
        for image_path in files:
            shutil.copy2(image_path, output_dir / "images" / subset / image_path.name)
            label_path = labels_dir / f"{image_path.stem}.txt"
            if label_path.exists():
                shutil.copy2(label_path, output_dir / "labels" / subset / label_path.name)
            else:
                missing_labels += 1
                logging.warning("Image has no matching label: %s", image_path)

    logging.info("Images split: train=%d val=%d test=%d", *(len(subsets[key]) for key in ("train", "val", "test")))
    logging.info("Missing labels: %d", missing_labels)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Split YOLO-format images and labels.")
    parser.add_argument("--images-dir", required=True, type=Path, help="Source images directory.")
    parser.add_argument("--labels-dir", required=True, type=Path, help="Source YOLO labels directory.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Processed output directory.")
    parser.add_argument("--split", type=parse_split, default=(0.7, 0.2, 0.1), help="Split ratio train,val,test.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing processed files.")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging(args.verbose)
    return split_dataset(args.images_dir, args.labels_dir, args.output_dir, args.split, args.seed, args.overwrite)


if __name__ == "__main__":
    raise SystemExit(main())
