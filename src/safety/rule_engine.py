from typing import Any

from src.safety.risk_scoring import load_risk_rules, score_event, severity_from_score
from src.safety.track_state_manager import StableTrackDecision


class RuleEngine:
    def score_track(
        self,
        camera_id: str,
        person_detected: bool,
        decision: StableTrackDecision,
        total_inside_seconds: float,
        no_helmet_seconds: float,
        no_helmet_count: int,
        uncertain: bool = False,
    ) -> dict[str, Any]:
        risk = score_event(
            camera_id=camera_id,
            person_detected=person_detected,
            inside_danger_zone=decision.stable_inside_zone,
            no_helmet=decision.no_helmet,
            total_inside_seconds=total_inside_seconds,
            no_helmet_seconds=no_helmet_seconds,
            no_helmet_count=no_helmet_count,
            uncertain=uncertain,
        )
        rule_score = int(risk.get("risk_score", 0))
        smoothed_score = int(round(decision.risk_score))
        display_score = max(smoothed_score, rule_score) if decision.violation_active else smoothed_score
        risk["risk_score"] = display_score
        risk["severity"] = severity_from_score(display_score)
        risk["actions"] = self._actions_for(camera_id, risk["severity"])
        risk["details"] = {
            **risk.get("details", {}),
            "stable_ppe": decision.stable_ppe,
            "stable_inside_zone": decision.stable_inside_zone,
            "decision_status": decision.status,
            "violation_duration_seconds": round(decision.violation_duration_seconds, 3),
            "raw_ppe": decision.raw_ppe,
            "raw_inside_zone": decision.raw_inside_zone,
            "ppe_votes": decision.ppe_votes,
            "zone_votes": decision.zone_votes,
        }
        return risk

    @staticmethod
    def _actions_for(camera_id: str, severity: str) -> list[str]:
        rules = load_risk_rules()
        return list(
            rules.get("camera_rules", {})
            .get(camera_id, {})
            .get("actions", {})
            .get(severity, [])
        )
