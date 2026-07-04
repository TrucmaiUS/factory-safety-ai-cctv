"""Convert Pascal VOC XML annotations to YOLO txt labels.

Final Phase 2 label map:
0: person
1: helmet
2: head
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path


DEFAULT_CLASS_ALIASES = {
    "helmet": 1,
    "hardhat": 1,
    "hard_hat": 1,
    "hat": 1,
    "safety_helmet": 1,
    "safety helmet": 1,
    "person": 0,
    "worker": 0,
    "people": 0,
    "head": 2,
    "no_helmet": 2,
    "no-hardhat": 2,
    "no_hardhat": 2,
    "bare_head": 2,
}

IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".bmp", ".webp"]


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def normalize_class_name(name: str) -> str:
    return name.strip().lower().replace("-", "_")


def load_class_map(path: Path | None) -> dict[str, int]:
    if path is None:
        return DEFAULT_CLASS_ALIASES
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read class map JSON {path}: {exc}") from exc
    result: dict[str, int] = {}
    for key, value in data.items():
        if value not in (0, 1, 2):
            raise ValueError(f"Invalid target class id for {key}: {value}")
        result[normalize_class_name(key)] = int(value)
    return result


def find_image(images_dir: Path, stem: str) -> Path | None:
    for ext in IMAGE_EXTENSIONS:
        candidate = images_dir / f"{stem}{ext}"
        if candidate.exists():
            return candidate
    return None


def voc_box_to_yolo(
    xmin: float, ymin: float, xmax: float, ymax: float, width: float, height: float
) -> tuple[float, float, float, float]:
    x_center = ((xmin + xmax) / 2.0) / width
    y_center = ((ymin + ymax) / 2.0) / height
    box_width = (xmax - xmin) / width
    box_height = (ymax - ymin) / height
    return x_center, y_center, box_width, box_height


def convert_file(xml_path: Path, output_labels_dir: Path, class_map: dict[str, int]) -> tuple[int, int]:
    try:
        root = ET.parse(xml_path).getroot()
    except ET.ParseError as exc:
        logging.warning("Skipping invalid XML %s: %s", xml_path, exc)
        return 0, 1

    width_text = root.findtext("size/width")
    height_text = root.findtext("size/height")
    if not width_text or not height_text:
        logging.warning("Skipping XML without size: %s", xml_path)
        return 0, 1

    width = float(width_text)
    height = float(height_text)
    if width <= 0 or height <= 0:
        logging.warning("Skipping XML with invalid size: %s", xml_path)
        return 0, 1

    lines: list[str] = []
    ignored = 0
    for obj in root.findall("object"):
        raw_name = obj.findtext("name") or ""
        class_id = class_map.get(normalize_class_name(raw_name))
        if class_id is None:
            ignored += 1
            continue

        box = obj.find("bndbox")
        if box is None:
            ignored += 1
            continue
        try:
            xmin = float(box.findtext("xmin", "0"))
            ymin = float(box.findtext("ymin", "0"))
            xmax = float(box.findtext("xmax", "0"))
            ymax = float(box.findtext("ymax", "0"))
        except ValueError:
            ignored += 1
            continue

        xmin = max(0.0, min(xmin, width))
        xmax = max(0.0, min(xmax, width))
        ymin = max(0.0, min(ymin, height))
        ymax = max(0.0, min(ymax, height))
        if xmax <= xmin or ymax <= ymin:
            ignored += 1
            continue

        yolo_box = voc_box_to_yolo(xmin, ymin, xmax, ymax, width, height)
        lines.append(f"{class_id} " + " ".join(f"{value:.6f}" for value in yolo_box))

    output_labels_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_labels_dir / f"{xml_path.stem}.txt"
    output_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return len(lines), ignored


def convert_dataset(input_dir: Path, output_dir: Path, images_dir: Path, class_map_path: Path | None) -> int:
    if not input_dir.exists():
        logging.error("Input annotation directory does not exist: %s", input_dir)
        return 2
    if not images_dir.exists():
        logging.error("Images directory does not exist: %s", images_dir)
        return 2

    try:
        class_map = load_class_map(class_map_path)
    except ValueError as exc:
        logging.error("%s", exc)
        return 2

    output_images_dir = output_dir / "images"
    output_labels_dir = output_dir / "labels"
    output_images_dir.mkdir(parents=True, exist_ok=True)
    output_labels_dir.mkdir(parents=True, exist_ok=True)

    xml_files = sorted(input_dir.rglob("*.xml"))
    if not xml_files:
        logging.warning("No VOC XML files found under %s", input_dir)
        return 0

    converted = 0
    ignored = 0
    missing_images = 0
    for xml_path in xml_files:
        label_count, ignored_count = convert_file(xml_path, output_labels_dir, class_map)
        converted += label_count
        ignored += ignored_count
        image_path = find_image(images_dir, xml_path.stem)
        if image_path is None:
            missing_images += 1
            logging.warning("No matching image found for %s", xml_path.name)
            continue
        shutil.copy2(image_path, output_images_dir / image_path.name)

    logging.info("XML files processed: %d", len(xml_files))
    logging.info("YOLO labels written to: %s", output_labels_dir)
    logging.info("Images copied to: %s", output_images_dir)
    logging.info("Converted boxes: %d", converted)
    logging.info("Ignored objects/classes: %d", ignored)
    logging.info("Missing matching images: %d", missing_images)
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert Pascal VOC XML annotations to YOLO labels.")
    parser.add_argument("--input-dir", required=True, type=Path, help="Directory containing VOC XML files.")
    parser.add_argument("--output-dir", required=True, type=Path, help="Output directory for images/labels.")
    parser.add_argument("--images-dir", required=True, type=Path, help="Directory containing source images.")
    parser.add_argument("--class-map", type=Path, default=None, help="Optional JSON class alias map.")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    configure_logging(args.verbose)
    return convert_dataset(args.input_dir, args.output_dir, args.images_dir, args.class_map)


if __name__ == "__main__":
    raise SystemExit(main())
