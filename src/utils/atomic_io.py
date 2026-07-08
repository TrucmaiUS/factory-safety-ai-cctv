import json
import os
import time
from pathlib import Path
from typing import Any
from uuid import uuid4


def unique_tmp_path(path: Path, suffix: str = ".tmp") -> Path:
    return path.with_name(f"{path.name}.{os.getpid()}.{uuid4().hex}{suffix}")


def replace_with_retry(tmp_path: Path, final_path: Path, retries: int = 12, delay_seconds: float = 0.05) -> bool:
    final_path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(retries):
        try:
            os.replace(tmp_path, final_path)
            return True
        except PermissionError:
            if attempt == retries - 1:
                break
            time.sleep(delay_seconds * (attempt + 1))
        except FileNotFoundError:
            return False
    try:
        tmp_path.unlink(missing_ok=True)
    except OSError:
        pass
    return False


def write_json_atomic(path: Path, payload: Any, retries: int = 12) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = unique_tmp_path(path, ".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
        f.flush()
        os.fsync(f.fileno())
    return replace_with_retry(tmp_path, path, retries=retries)
