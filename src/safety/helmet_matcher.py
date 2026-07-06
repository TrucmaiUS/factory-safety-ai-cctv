from typing import Any

from src.perception.detection_types import DetectionBox
from src.perception.ppe_detector import is_head, is_helmet


LOW_CONF_THRESHOLD = 0.35


def _box_center(box: DetectionBox) -> tuple[float, float]:
    return box.center


def _head_region(person: DetectionBox) -> tuple[float, float, float, float]:
    return (
        person.x1,
        person.y1,
        person.x2,
        person.y1 + 0.45 * person.height,
    )


def _contains(region: tuple[float, float, float, float], point: tuple[float, float]) -> bool:
    x1, y1, x2, y2 = region
    return x1 <= point[0] <= x2 and y1 <= point[1] <= y2


def _intersection_area(a: DetectionBox, region: tuple[float, float, float, float]) -> float:
    x1 = max(a.x1, region[0])
    y1 = max(a.y1, region[1])
    x2 = min(a.x2, region[2])
    y2 = min(a.y2, region[3])
    return max(0.0, x2 - x1) * max(0.0, y2 - y1)


def _matches_head_region(ppe_box: DetectionBox, region: tuple[float, float, float, float]) -> bool:
    if _contains(region, _box_center(ppe_box)):
        return True
    if ppe_box.area <= 0:
        return False
    return _intersection_area(ppe_box, region) / ppe_box.area >= 0.25


def _near(a: DetectionBox, b: DetectionBox, max_distance: float) -> bool:
    ax, ay = a.center
    bx, by = b.center
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5 <= max_distance


def match_helmet_to_person(person_bbox: DetectionBox, ppe_detections: list[DetectionBox]) -> dict[str, Any]:
    region = _head_region(person_bbox)
    matched_helmets = [
        det for det in ppe_detections
        if is_helmet(det.label) and _matches_head_region(det, region)
    ]
    matched_heads = [
        det for det in ppe_detections
        if is_head(det.label) and _matches_head_region(det, region)
    ]

    has_helmet = bool(matched_helmets)
    has_head = bool(matched_heads)
    helmet_conf = max((det.conf for det in matched_helmets), default=None)
    head_conf = max((det.conf for det in matched_heads), default=None)

    helmet_near_head = False
    if matched_helmets and matched_heads:
        max_distance = max(35.0, person_bbox.width * 0.20)
        helmet_near_head = any(
            _near(helmet, head, max_distance)
            for helmet in matched_helmets
            for head in matched_heads
        )

    no_helmet = has_head and not has_helmet
    uncertain = False
    if has_helmet and has_head and helmet_near_head:
        uncertain = True
    if helmet_conf is not None and helmet_conf < LOW_CONF_THRESHOLD:
        uncertain = True
    if head_conf is not None and head_conf < LOW_CONF_THRESHOLD:
        uncertain = True

    return {
        "has_helmet": has_helmet,
        "has_head": has_head,
        "no_helmet": no_helmet,
        "helmet_conf": helmet_conf,
        "head_conf": head_conf,
        "matched_ppe": matched_helmets + matched_heads,
        "uncertain": uncertain,
    }


def count_unmatched_heads(ppe_detections: list[DetectionBox]) -> int:
    helmets = [det for det in ppe_detections if is_helmet(det.label)]
    heads = [det for det in ppe_detections if is_head(det.label)]
    unmatched = 0
    for head in heads:
        max_distance = max(35.0, head.width * 2.0)
        if not any(_near(head, helmet, max_distance) for helmet in helmets):
            unmatched += 1
    return unmatched
