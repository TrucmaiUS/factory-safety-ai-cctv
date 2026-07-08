from dataclasses import dataclass


SEVERITY_RANK = {
    "normal": 0,
    "warning": 1,
    "high": 2,
    "critical": 3,
}


@dataclass
class _EventMemory:
    active: bool = False
    severity: str = "normal"
    last_emit_time: float = 0.0


class EventStateManager:
    def __init__(self, ongoing_cooldown_seconds: float = 5.0) -> None:
        self.ongoing_cooldown_seconds = ongoing_cooldown_seconds
        self._events: dict[tuple[str, int, str], _EventMemory] = {}

    def update(
        self,
        camera_id: str,
        person_id: int,
        violation_type: str,
        active: bool,
        severity: str,
        timestamp_seconds: float,
    ) -> str | None:
        key = (camera_id, person_id, violation_type)
        memory = self._events.setdefault(key, _EventMemory())

        if active:
            if not memory.active:
                memory.active = True
                memory.severity = severity
                memory.last_emit_time = timestamp_seconds
                return self._started_state(severity)

            if SEVERITY_RANK.get(severity, 0) > SEVERITY_RANK.get(memory.severity, 0):
                memory.severity = severity
                memory.last_emit_time = timestamp_seconds
                return self._started_state(severity)

            if timestamp_seconds - memory.last_emit_time >= self.ongoing_cooldown_seconds:
                memory.last_emit_time = timestamp_seconds
                return self._ongoing_state(memory.severity)

            return None

        if memory.active:
            memory.active = False
            memory.severity = "normal"
            memory.last_emit_time = timestamp_seconds
            return "RESOLVED"

        return None

    @staticmethod
    def _started_state(severity: str) -> str:
        if severity == "critical":
            return "CRITICAL_STARTED"
        return "WARNING_STARTED"

    @staticmethod
    def _ongoing_state(severity: str) -> str:
        if severity == "critical":
            return "CRITICAL_ONGOING"
        return "WARNING_ONGOING"
