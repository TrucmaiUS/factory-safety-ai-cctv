from dataclasses import dataclass
from math import hypot

from src.perception.detection_types import DetectionBox


@dataclass
class TrackState:
    track_id: int
    bbox: DetectionBox
    center: tuple[float, float]
    bottom_center: tuple[float, float]
    first_seen_frame: int
    last_seen_frame: int
    inside_zone_start_time: float | None = None
    total_inside_seconds: float = 0.0
    was_inside_zone: bool = False
    no_helmet_start_time: float | None = None
    total_no_helmet_seconds: float = 0.0
    was_no_helmet: bool = False
    missed_frames: int = 0


class CentroidTracker:
    def __init__(
        self,
        max_distance: float = 90.0,
        max_missed_frames: int = 20,
        min_iou: float = 0.05,
    ) -> None:
        self.max_distance = max_distance
        self.max_missed_frames = max_missed_frames
        self.min_iou = min_iou
        self.next_track_id = 1
        self.tracks: dict[int, TrackState] = {}

    def update(self, detections: list[DetectionBox], frame_index: int) -> list[TrackState]:
        if not detections:
            self._mark_all_missed()
            return list(self.tracks.values())

        unmatched_track_ids = set(self.tracks.keys())
        unmatched_detection_indices = set(range(len(detections)))
        matches: list[tuple[float, int, int]] = []

        for track_id, track in self.tracks.items():
            for det_idx, detection in enumerate(detections):
                distance = self._distance(track.bottom_center, detection.bottom_center)
                iou = self._iou(track.bbox, detection)
                if distance <= self.max_distance or iou >= self.min_iou:
                    score = distance - (iou * self.max_distance)
                    matches.append((score, track_id, det_idx))

        for _, track_id, det_idx in sorted(matches, key=lambda item: item[0]):
            if track_id not in unmatched_track_ids or det_idx not in unmatched_detection_indices:
                continue
            self._update_track(track_id, detections[det_idx], frame_index)
            unmatched_track_ids.remove(track_id)
            unmatched_detection_indices.remove(det_idx)

        for track_id in unmatched_track_ids:
            self.tracks[track_id].missed_frames += 1

        self._remove_stale_tracks()

        for det_idx in unmatched_detection_indices:
            self._create_track(detections[det_idx], frame_index)

        return list(self.tracks.values())

    def update_zone_state(self, track: TrackState, is_inside_zone: bool, timestamp_seconds: float) -> None:
        if is_inside_zone:
            if not track.was_inside_zone:
                track.inside_zone_start_time = timestamp_seconds
                track.was_inside_zone = True
            elif track.inside_zone_start_time is not None:
                track.total_inside_seconds = timestamp_seconds - track.inside_zone_start_time
            return

        track.was_inside_zone = False
        track.inside_zone_start_time = None
        track.total_inside_seconds = 0.0

    def update_no_helmet_state(self, track: TrackState, no_helmet: bool, timestamp_seconds: float) -> None:
        if no_helmet:
            if not track.was_no_helmet:
                track.no_helmet_start_time = timestamp_seconds
                track.was_no_helmet = True
            elif track.no_helmet_start_time is not None:
                track.total_no_helmet_seconds = timestamp_seconds - track.no_helmet_start_time
            return

        track.was_no_helmet = False
        track.no_helmet_start_time = None
        track.total_no_helmet_seconds = 0.0

    def _create_track(self, detection: DetectionBox, frame_index: int) -> None:
        track = TrackState(
            track_id=self.next_track_id,
            bbox=detection,
            center=detection.center,
            bottom_center=detection.bottom_center,
            first_seen_frame=frame_index,
            last_seen_frame=frame_index,
        )
        self.tracks[self.next_track_id] = track
        self.next_track_id += 1

    def _update_track(self, track_id: int, detection: DetectionBox, frame_index: int) -> None:
        track = self.tracks[track_id]
        track.bbox = detection
        track.center = detection.center
        track.bottom_center = detection.bottom_center
        track.last_seen_frame = frame_index
        track.missed_frames = 0

    def _mark_all_missed(self) -> None:
        for track in self.tracks.values():
            track.missed_frames += 1
        self._remove_stale_tracks()

    def _remove_stale_tracks(self) -> None:
        stale_ids = [
            track_id
            for track_id, track in self.tracks.items()
            if track.missed_frames > self.max_missed_frames
        ]
        for track_id in stale_ids:
            del self.tracks[track_id]

    @staticmethod
    def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
        return hypot(a[0] - b[0], a[1] - b[1])

    @staticmethod
    def _iou(a: DetectionBox, b: DetectionBox) -> float:
        x1 = max(a.x1, b.x1)
        y1 = max(a.y1, b.y1)
        x2 = min(a.x2, b.x2)
        y2 = min(a.y2, b.y2)
        inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        if inter <= 0:
            return 0.0
        union = a.area + b.area - inter
        return inter / union if union > 0 else 0.0
