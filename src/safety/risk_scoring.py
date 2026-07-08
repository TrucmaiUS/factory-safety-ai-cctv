from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RULES_PATH = ROOT / "src" / "configs" / "risk_rules.yaml"

Severity = str


@lru_cache(maxsize=1)
def load_risk_rules(rules_path: str = str(DEFAULT_RULES_PATH)) -> dict[str, Any]:
    path = Path(rules_path)
    if not path.exists():
        raise FileNotFoundError(f"Risk rules config not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def severity_from_score(score: int, rules: dict[str, Any] | None = None) -> Severity:
    rules = rules or load_risk_rules()
    thresholds = rules.get("severity_thresholds", {})

    for severity in ("normal", "warning", "high", "critical"):
        low, high = thresholds.get(severity, [0, 100])
        if int(low) <= score <= int(high):
            return severity

    return "critical"


def score_limits(rules: dict[str, Any] | None = None) -> dict[str, int]:
    rules = rules or load_risk_rules()
    limits = rules.get("score_limits", {})
    return {
        "min_score": int(limits.get("min_score", 0)),
        "max_score": int(limits.get("max_score", 100)),
    }


def decision_policy(rules: dict[str, Any] | None = None) -> dict[str, int]:
    rules = rules or load_risk_rules()
    policy = rules.get("decision_policy", {})
    return {
        "warning_min_score": int(policy.get("warning_min_score", 25)),
        "violation_min_score": int(policy.get("violation_min_score", 50)),
        "stable_violation_min_score": int(policy.get("stable_violation_min_score", 80)),
        "combined_violation_score": int(policy.get("combined_violation_score", 100)),
        "ppe_visibility_warning_score": int(policy.get("ppe_visibility_warning_score", 30)),
    }


def _camera_weights(camera_id: str, rules: dict[str, Any]) -> dict[str, int]:
    defaults = rules.get("default_weights", {})
    camera_weights = (
        rules.get("camera_rules", {})
        .get(camera_id, {})
        .get("weights", {})
    )
    merged = {**defaults, **camera_weights}
    return {key: int(value) for key, value in merged.items()}


def _weight(weights: dict[str, int], key: str, legacy_key: str | None = None) -> int:
    if key in weights:
        return weights[key]
    if legacy_key and legacy_key in weights:
        return weights[legacy_key]
    return 0


def _actions_for(camera_id: str, severity: Severity, rules: dict[str, Any]) -> list[str]:
    return list(
        rules.get("camera_rules", {})
        .get(camera_id, {})
        .get("actions", {})
        .get(severity, [])
    )


def score_event(
    camera_id: str,
    person_detected: bool = False,
    inside_danger_zone: bool = False,
    no_helmet: bool = False,
    total_inside_seconds: float = 0.0,
    no_helmet_seconds: float = 0.0,
    no_helmet_count: int = 0,
    uncertain: bool = False,
) -> dict[str, Any]:
    rules = load_risk_rules()
    weights = _camera_weights(camera_id, rules)
    dwell = rules.get("dwell_time", {})
    danger_dwell_seconds = float(dwell.get("danger_zone_seconds", 3.0))
    no_helmet_dwell_seconds = float(dwell.get("no_helmet_seconds", 3.0))

    risk_score = 0
    reasons: list[str] = []
    details: dict[str, Any] = {
        "camera_id": camera_id,
        "person_detected": person_detected,
        "inside_danger_zone": inside_danger_zone,
        "no_helmet": no_helmet,
        "total_inside_seconds": round(float(total_inside_seconds), 3),
        "no_helmet_seconds": round(float(no_helmet_seconds), 3),
        "no_helmet_count": int(no_helmet_count),
        "uncertain": uncertain,
    }

    if person_detected:
        risk_score += weights.get("person_detected", 0)
        reasons.append("person_detected")

    if inside_danger_zone:
        risk_score += weights.get("inside_danger_zone", 0)
        reasons.append("inside_danger_zone")

    if inside_danger_zone and total_inside_seconds >= danger_dwell_seconds:
        risk_score += _weight(weights, "stay_time_over_threshold", "stay_time_over_3s")
        reasons.append(f"stayed_in_zone_over_{danger_dwell_seconds:g}s")

    if no_helmet:
        risk_score += weights.get("no_helmet", 0)
        reasons.append("no_helmet")

    if no_helmet and no_helmet_seconds >= no_helmet_dwell_seconds:
        risk_score += _weight(weights, "no_helmet_over_threshold", "no_helmet_over_3s")
        reasons.append(f"no_helmet_over_{no_helmet_dwell_seconds:g}s")

    if no_helmet_count >= 2:
        risk_score += weights.get("multiple_no_helmet_bonus", 0)
        reasons.append("multiple_no_helmet_persons")

    if inside_danger_zone and no_helmet:
        risk_score += weights.get("combined_danger_no_helmet_bonus", 0)
        reasons.append("combined_danger_no_helmet")

    if uncertain:
        risk_score += weights.get("uncertain_detection_penalty", 0)
        reasons.append("uncertain_detection")

    limits = score_limits(rules)
    risk_score = max(limits["min_score"], min(limits["max_score"], risk_score))
    severity = severity_from_score(risk_score, rules)
    actions = _actions_for(camera_id, severity, rules)

    return {
        "risk_score": risk_score,
        "severity": severity,
        "reasons": reasons,
        "actions": actions,
        "details": details,
    }


def score_camera_2(
    person_detected: bool,
    inside_danger_zone: bool,
    total_inside_seconds: float,
) -> dict[str, Any]:
    return score_event(
        "camera_2",
        person_detected=person_detected,
        inside_danger_zone=inside_danger_zone,
        total_inside_seconds=total_inside_seconds,
    )
