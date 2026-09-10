"""Small bounded metrics registry that never accepts request labels or payloads."""

from __future__ import annotations

import math
import re
from collections import defaultdict
from threading import RLock
from typing import Any


_METRIC_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class MetricsRegistry:
    """Collect counters and latency totals using a fixed, label-free name."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._counters: dict[str, int] = defaultdict(int)
        self._latencies: dict[str, list[float]] = defaultdict(lambda: [0, 0.0])

    @staticmethod
    def _name(name: str) -> str:
        if not isinstance(name, str) or not _METRIC_NAME.fullmatch(name):
            raise ValueError("metric name is invalid")
        return name

    def increment(self, name: str, amount: int = 1) -> None:
        name = self._name(name)
        if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
            raise ValueError("metric amount is invalid")
        with self._lock:
            self._counters[name] += amount

    def observe_latency(self, name: str, milliseconds: float) -> None:
        name = self._name(name)
        if isinstance(milliseconds, bool) or not isinstance(milliseconds, (int, float)) or not math.isfinite(milliseconds) or milliseconds < 0:
            raise ValueError("latency observation is invalid")
        with self._lock:
            self._latencies[name][0] += 1
            self._latencies[name][1] += float(milliseconds)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "counters": dict(sorted(self._counters.items())),
                "latencies": {
                    name: {"count": int(values[0]), "sum_ms": values[1]}
                    for name, values in sorted(self._latencies.items())
                },
            }
