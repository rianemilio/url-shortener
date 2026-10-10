"""Healthcheck do worker para o container: `python -m url_shortener.interface.worker.healthcheck`.

Sai com 0 se o heartbeat foi tocado há pouco e 1 caso contrário (arquivo velho ou ausente).
"""

import sys
import time
from pathlib import Path

from url_shortener.config import get_settings

# Tolera perder dois heartbeats seguidos (ex.: um ping lento) antes de acusar problema.
_MISSED_HEARTBEATS_TOLERATED = 3


def is_heartbeat_fresh(heartbeat_file: Path, interval_seconds: float, now: float) -> bool:
    try:
        age = now - heartbeat_file.stat().st_mtime
    except FileNotFoundError:
        return False
    return age <= interval_seconds * _MISSED_HEARTBEATS_TOLERATED


def main() -> None:
    settings = get_settings()
    fresh = is_heartbeat_fresh(
        Path(settings.worker_heartbeat_file),
        settings.worker_heartbeat_interval_seconds,
        time.time(),
    )
    sys.exit(0 if fresh else 1)


if __name__ == "__main__":
    main()
