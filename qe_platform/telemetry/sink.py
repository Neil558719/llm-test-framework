from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from .models import TelemetryTrace


class TelemetrySink:
    hash_key: str = ""
    enabled: bool = True

    def emit(self, event: TelemetryTrace) -> None:
        raise NotImplementedError


class NoopTelemetrySink(TelemetrySink):
    enabled = False

    def emit(self, event: TelemetryTrace) -> None:
        return None


class HttpTelemetrySink(TelemetrySink):
    def __init__(
        self,
        endpoint: str,
        ingest_token: str,
        hash_key: str,
        *,
        retention_days: int = 30,
        timeout: float = 2.0,
    ) -> None:
        self.endpoint = endpoint
        self.ingest_token = ingest_token
        self.hash_key = hash_key
        self.retention_days = retention_days
        self.timeout = timeout

    def emit(self, event: TelemetryTrace) -> None:
        try:
            payload = json.dumps(event.as_dict(), ensure_ascii=False).encode("utf-8")
            request = urllib.request.Request(
                self.endpoint,
                data=payload,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "X-QE-Telemetry-Token": self.ingest_token,
                },
            )
            with urllib.request.urlopen(request, timeout=self.timeout):
                return None
        except Exception:
            return None


def telemetry_sink_from_environment(values: dict[str, Any] | None = None) -> TelemetrySink:
    env = os.environ if values is None else values
    endpoint = str(env.get("QE_TELEMETRY_ENDPOINT", "")).strip()
    ingest_token = str(env.get("QE_TELEMETRY_INGEST_TOKEN", "")).strip()
    hash_key = str(env.get("QE_TELEMETRY_HASH_KEY", "")).strip()
    if not endpoint or not ingest_token or not hash_key:
        return NoopTelemetrySink()
    try:
        retention_days = int(str(env.get("QE_TELEMETRY_RETENTION_DAYS", "30")).strip() or "30")
    except ValueError:
        retention_days = 30
    if retention_days <= 0:
        retention_days = 30
    return HttpTelemetrySink(endpoint, ingest_token, hash_key, retention_days=retention_days)
