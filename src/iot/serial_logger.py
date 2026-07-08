import os
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERIAL_LOG_PATH = ROOT / "outputs" / "serial_monitor.log"


def serial_log(message: str) -> None:
    SERIAL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    with SERIAL_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(f"{timestamp} {message}\n")
        f.flush()
        os.fsync(f.fileno())


def read_serial_log(tail: int = 100) -> list[str]:
    if not SERIAL_LOG_PATH.exists():
        return []
    return SERIAL_LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()[-tail:]
