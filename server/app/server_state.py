"""Runtime notices an admin can change without restarting (stage 10): the maintenance
message and the server-wide announcement shown by /server/info and the login screen.
They live in RAM; MAINTENANCE_MESSAGE in .env is the value after a restart."""
from __future__ import annotations

import time

from .config import settings

started_at = time.time()
maintenance_message: str = settings.maintenance_message
announcement: str = ""


def uptime_seconds() -> int:
    return int(time.time() - started_at)


def reset() -> None:
    """Tests: back to the values from the environment."""
    global maintenance_message, announcement
    maintenance_message, announcement = settings.maintenance_message, ""
