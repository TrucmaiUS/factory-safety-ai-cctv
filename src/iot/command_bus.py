import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COMMANDS_PATH = ROOT / "outputs" / "device_commands.jsonl"


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def publish_command(command: dict) -> None:
    _ensure_parent(COMMANDS_PATH)
    with COMMANDS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(command, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def read_recent_commands(limit: int = 20) -> list[dict]:
    if not COMMANDS_PATH.exists():
        return []

    lines = COMMANDS_PATH.read_text(encoding="utf-8").splitlines()
    commands: list[dict] = []
    for line in lines[-limit:]:
        if not line.strip():
            continue
        try:
            commands.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return commands
