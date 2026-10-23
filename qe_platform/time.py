"""UTC wall clock default; inject a Clock for deterministic application time."""
from datetime import datetime, timezone
from typing import Callable

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
