"""Inspect local safety/PPE datasets without modifying them.

The script intentionally ignores zip files by default and handles unknown
dataset layouts gracefully. It is meant for Phase 2 dataset triage before any
conversion or merging work.
"""

from __future__ import annotations

import argparse
import logging
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Iterable


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
YOLO_LABEL_EXTENSIONS = {".txt"}
VOC_EXTENSIONS = {".xml"}
COCO_NAMES = {"annotations.json", "instances_train.json", "instances_val.json"}


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def iter_files(root: Path, ignore_zip: bool = True) -> Iterable[Path]:
    if not root.exists():
        return
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        if ignore_zip and path.suffix.lower() == ".zip":
            continue
        yield path


def detect_format(files: list[Path]) -> str:
    suffixes = Counter(path.suffix.lower() for path in files)
    names = {path.name.lower() for path in files}
    has_yolo = suffixes[".txt"] > 0 and any("labels" in path.parts for path in files)
    has_voc = suffixes[".xml"] > 0
    has_coco = any(name in COCO_NAMES for name in names) or any(
        path.suffix.lower() == ".json" and "annotation" in path.name.lower()
        for path in files
    )
    if has_yolo:
        return "YOLO"
    if has_voc:
        return "Pascal VOC"
    if has_coco:
        return "COCO"
    return "unknown"


def looks_like_yolo_label(path: Path) -> bool:
    if path.suffix.lower() != ".txt":
        return False
    if any(part.lower() == "labels" for part in path.parts):
        return True
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return False
    non_empty = [line.strip() for line in lines if line.strip()]
    if not non_empty:
        return False
    for line in non_empty[:5]:
        parts = line.split()
        if len(parts) != 5:
            return False
        try:
            int(parts[0])
            [float(value) for value in parts[1:]]
        except ValueError:
            return False
    return True


def count_voc_classes(xml_files: list[Path]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for xml_path in xml_files:
        try:
            root = ET.parse(xml_path).getroot()
        except ET.ParseError:
            logging.warning("Could not parse XML: %s", xml_path)
            continue
        for obj in root.findall("object"):
            name = obj.findtext("name")
            if name:
                counts[name.strip()] += 1
    return counts


def count_yolo_classes(label_files: list[Path]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for label_path in label_files:
        try:
            lines = label_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError as exc:
            logging.warning("Could not read label file %s: %s", label_path, exc)
            continue
        for line in lines:
            parts = line.strip().split()
            if len(parts) == 5 and parts[0].lstrip("-").isdigit():
                counts[parts[0]] += 1
    return counts


def sample(paths: list[Path], limit: int) -> list[str]:
    return [str(path) for path in sorted(paths)[:limit]]


def inspect_dataset(dataset_dir: Path, sample_limit: int) -> int:
    logging.info("Inspecting dataset: %s", dataset_dir)
    if not dataset_dir.exists():
        logging.error("Dataset directory does not exist: %s", dataset_dir)
        return 2
    if not dataset_dir.is_dir():
        logging.error("Dataset path is not a directory: %s", dataset_dir)
        return 2

    files = list(iter_files(dataset_dir))
    if not files:
        logging.warning("Dataset directory is empty or only contains ignored files.")
        return 0

    image_files = [path for path in files if path.suffix.lower() in IMAGE_EXTENSIONS]
    xml_files = [path for path in files if path.suffix.lower() in VOC_EXTENSIONS]
    txt_files = [path for path in files if path.suffix.lower() in YOLO_LABEL_EXTENSIONS]
    yolo_label_files = [path for path in txt_files if looks_like_yolo_label(path)]
    json_files = [path for path in files if path.suffix.lower() == ".json"]

    likely_format = detect_format(files)
    logging.info("Likely format: %s", likely_format)
    logging.info("Images: %d", len(image_files))
    logging.info("VOC XML annotations: %d", len(xml_files))
    logging.info("YOLO label files: %d", len(yolo_label_files))
    logging.info("Other TXT files: %d", len(txt_files) - len(yolo_label_files))
    logging.info("JSON files: %d", len(json_files))

    if not image_files:
        logging.warning("No image files found.")
    if not xml_files and not txt_files and not json_files:
        logging.warning("No obvious annotation files found.")

    if xml_files:
        logging.info("VOC class counts: %s", dict(count_voc_classes(xml_files)))
    if yolo_label_files and likely_format == "YOLO":
        logging.info("YOLO class-id counts: %s", dict(count_yolo_classes(yolo_label_files)))

    logging.info("Sample image files: %s", sample(image_files, sample_limit))
    logging.info("Sample annotation files: %s", sample(xml_files + yolo_label_files + json_files, sample_limit))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect a local dataset folder.")
    parser.add_argument("--dataset-dir", required=True, type=Path, help="Dataset directory to inspect.")
    parser.add_argument("--sample-limit", type=int, default=5, help="Number of sample files to print.")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging(args.verbose)
    return inspect_dataset(args.dataset_dir, args.sample_limit)


if __name__ == "__main__":
    raise SystemExit(main())
