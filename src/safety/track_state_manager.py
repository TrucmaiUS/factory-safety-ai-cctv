from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Any


PPE_HELMET = "helmet"
PPE_NO_HELMET = "no_helmet"
PPE_UNKNOWN = "unknown"


@dataclass
class StableTrackDecision:
    track_id: int
    stable_ppe: str
    stable_inside_zone: bool
    risk_score: float
    status: str
    violation_active: bool
    violation_duration_seconds: float
    ppe_votes: dict[str, int]
    zone_votes: dict[str, int]
    raw_ppe: str
    raw_inside_zone: bool

    @property
    def no_helmet(self) -> bool:
        return self.stable_ppe == PPE_NO_HELMET


@dataclass
class _TrackMemory:
    ppe_buffer: deque[str] = field(default_factory=deque)
    zone_buffer: deque[bool] = field(default_factory=deque)
    stable_ppe: str = PPE_UNKNOWN
    stable_inside_zone: bool = False
    risk_score: float = 0.0
    violation_started_at: float | None = None
    violation_alerted: bool = False
    last_seen_frame: int = 0


class TrackStateManager:
    def __init__(
        self,
        window_size: int = 12,
        no_helmet_confirm_frames: int = 6,
        no_helmet_clear_frames: int = 8,
        zone_confirm_frames: int = 5,
        zone_clear_frames: int = 8,
        risk_alpha: float = 0.85,
        alert_duration_seconds: float = 1.5,
        stale_after_frames: int = 60,
        warning_min_score: int = 25,
        violation_min_score: int = 50,
        stable_violation_min_score: int = 80,
        combined_violation_score: int = 100,
    ) -> None:
        self.window_size = window_size
        self.no_helmet_confirm_frames = no_helmet_confirm_frames
        self.no_helmet_clear_frames = no_helmet_clear_frames
        self.zone_confirm_frames = zone_confirm_frames
        self.zone_clear_frames = zone_clear_frames
        self.risk_alpha = risk_alpha
        self.alert_duration_seconds = alert_duration_seconds
        self.stale_after_frames = stale_after_frames
        self.warning_min_score = warning_min_score
        self.violation_min_score = violation_min_score
        self.stable_violation_min_score = stable_violation_min_score
        self.combined_violation_score = combined_violation_score
        self._tracks: dict[int, _TrackMemory] = {}

    def update(
        self,
        track_id: int,
        raw_ppe: str,
        raw_inside_zone: bool,
        current_frame_risk: int,
        timestamp_seconds: float,
        frame_index: int,
    ) -> StableTrackDecision:
        memory = self._tracks.setdefault(track_id, _TrackMemory())
        memory.last_seen_frame = frame_index

        self._append(memory.ppe_buffer, raw_ppe)
        self._append(memory.zone_buffer, raw_inside_zone)
        memory.stable_ppe = self._stable_ppe(memory)
        memory.stable_inside_zone = self._stable_zone(memory)
        target_risk = self._target_risk(memory, current_frame_risk)
        memory.risk_score = (
            self.risk_alpha * memory.risk_score
            + (1.0 - self.risk_alpha) * float(target_risk)
        )
        if self._is_stable_violation(memory):
            memory.risk_score = max(memory.risk_score, float(target_risk))

        violation_active = self._is_violation(memory)
        if violation_active:
            if memory.violation_started_at is None:
                memory.violation_started_at = timestamp_seconds
            violation_duration = timestamp_seconds - memory.violation_started_at
        else:
            memory.violation_started_at = None
            memory.violation_alerted = False
            violation_duration = 0.0

        return StableTrackDecision(
            track_id=track_id,
            stable_ppe=memory.stable_ppe,
            stable_inside_zone=memory.stable_inside_zone,
            risk_score=memory.risk_score,
            status=self._status(memory.risk_score, violation_active),
            violation_active=violation_active,
            violation_duration_seconds=max(0.0, violation_duration),
            ppe_votes=dict(Counter(memory.ppe_buffer)),
            zone_votes={
                "inside": sum(1 for value in memory.zone_buffer if value),
                "outside": sum(1 for value in memory.zone_buffer if not value),
            },
            raw_ppe=raw_ppe,
            raw_inside_zone=raw_inside_zone,
        )

    def should_emit_violation(self, track_id: int, decision: StableTrackDecision) -> bool:
        memory = self._tracks.get(track_id)
        if not memory:
            return False
        if not decision.violation_active:
            return False
        if decision.violation_duration_seconds < self.alert_duration_seconds:
            return False
        if memory.violation_alerted:
            return False
        memory.violation_alerted = True
        return True

    def cleanup(self, frame_index: int) -> None:
        stale_ids = [
            track_id
            for track_id, memory in self._tracks.items()
            if frame_index - memory.last_seen_frame > self.stale_after_frames
        ]
        for track_id in stale_ids:
            del self._tracks[track_id]

    def _append(self, buffer: deque, value: Any) -> None:
        buffer.append(value)
        while len(buffer) > self.window_size:
            buffer.popleft()

    def _stable_ppe(self, memory: _TrackMemory) -> str:
        counts = Counter(memory.ppe_buffer)
        if memory.stable_ppe == PPE_NO_HELMET:
            if counts[PPE_HELMET] >= self.no_helmet_clear_frames:
                return PPE_HELMET
            return PPE_NO_HELMET
        if counts[PPE_NO_HELMET] >= self.no_helmet_confirm_frames:
            return PPE_NO_HELMET
        if counts[PPE_HELMET] >= self.no_helmet_confirm_frames:
            return PPE_HELMET
        return memory.stable_ppe if memory.stable_ppe != PPE_UNKNOWN else PPE_UNKNOWN

    def _stable_zone(self, memory: _TrackMemory) -> bool:
        inside_count = sum(1 for value in memory.zone_buffer if value)
        outside_count = len(memory.zone_buffer) - inside_count
        if memory.stable_inside_zone:
            if outside_count >= self.zone_clear_frames:
                return False
            return True
        if inside_count >= self.zone_confirm_frames:
            return True
        return False

    @staticmethod
    def _is_violation(memory: _TrackMemory) -> bool:
        return TrackStateManager._is_stable_violation(memory)

    @staticmethod
    def _is_stable_violation(memory: _TrackMemory) -> bool:
        if memory.stable_inside_zone:
            return True
        return memory.stable_ppe == PPE_NO_HELMET

    def _target_risk(self, memory: _TrackMemory, current_frame_risk: int) -> int:
        target = int(current_frame_risk)
        if memory.stable_inside_zone:
            target = max(target, self.stable_violation_min_score)
        if memory.stable_ppe == PPE_NO_HELMET:
            target = max(target, self.stable_violation_min_score)
        if memory.stable_inside_zone and memory.stable_ppe == PPE_NO_HELMET:
            target = self.combined_violation_score
        return target

    def _status(self, risk_score: float, violation_active: bool) -> str:
        if violation_active and risk_score >= float(self.violation_min_score):
            return "VIOLATION"
        if risk_score >= float(self.warning_min_score):
            return "WARNING"
        return "SAFE"
