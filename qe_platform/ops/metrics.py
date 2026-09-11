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


# Process-local totals also cover CLI operations and startup migrations.
PROCESS_METRICS = MetricsRegistry()


def measured(operation: str):
    from functools import wraps
    from time import perf_counter
    def decorate(function):
        @wraps(function)
        def wrapped(*args, **kwargs):
            start = perf_counter()
            PROCESS_METRICS.increment(operation + "_total")
            try:
                return function(*args, **kwargs)
            except Exception:
                PROCESS_METRICS.increment(operation + "_failures_total")
                raise
            finally:
                PROCESS_METRICS.observe_latency(operation + "_latency_ms", (perf_counter() - start) * 1000)
        return wrapped
    return decorate


def install_http_metrics(app, service: str) -> None:
    from time import perf_counter
    import sqlite3
    from fastapi.responses import JSONResponse
    @app.middleware("http")
    async def observe(request, call_next):
        start = perf_counter()
        app.state.metrics.increment(service + "_requests_total")
        try:
            try:
                response = await call_next(request)
            except sqlite3.Error:
                PROCESS_METRICS.increment("database_failures_total")
                response = JSONResponse({"detail": "database unavailable"}, status_code=503)
            if response.status_code in (401, 403):
                app.state.metrics.increment("auth_failures_total")
            if response.status_code >= 500:
                app.state.metrics.increment(service + "_failures_total")
            return response
        finally:
            app.state.metrics.observe_latency(service + "_request_latency_ms", (perf_counter() - start) * 1000)
