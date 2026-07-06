def trigger(camera_id: str, event: dict) -> None:
    severity = event.get("severity")
    reasons = set(event.get("reasons", []))
    if severity not in {"high", "critical"} or "inside_danger_zone" not in reasons:
        return

    actions = set(event.get("actions", []))
    device_messages = []
    if "relay_on" in actions:
        device_messages.append("RELAY ON")
    if "buzzer_on" in actions:
        device_messages.append("BUZZER ON")
    if "warning_light_on" in actions:
        device_messages.append("WARNING LIGHT ON")

    if device_messages:
        print(f"[DEVICE SIM] {camera_id} | {' | '.join(device_messages)}")
