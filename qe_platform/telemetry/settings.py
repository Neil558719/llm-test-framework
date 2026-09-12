from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from qe_platform.production.secrets import SecretSource


@dataclass(frozen=True)
class TelemetrySettings:
    database: str
    hash_key: str
    ingest_token: str
    retention_days: int = 30

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> "TelemetrySettings":
        values = os.environ if environ is None else environ
        secrets = SecretSource.from_environment(values)
        database = values.get("QE_TELEMETRY_DATABASE", "telemetry.db")
        hash_key = secrets.get("QE_TELEMETRY_HASH_KEY")
        ingest_token = secrets.get("QE_TELEMETRY_INGEST_TOKEN")
        retention_text = values.get("QE_TELEMETRY_RETENTION_DAYS", "30")
        if not isinstance(database, str) or not database:
            raise ValueError("QE_TELEMETRY_DATABASE must be nonempty")
        if not isinstance(hash_key, str) or not hash_key:
            raise ValueError("QE_TELEMETRY_HASH_KEY must be nonempty")
        if not isinstance(ingest_token, str) or not ingest_token:
            raise ValueError("QE_TELEMETRY_INGEST_TOKEN must be nonempty")
        try:
            retention_days = int(retention_text)
        except (TypeError, ValueError) as exc:
            raise ValueError("QE_TELEMETRY_RETENTION_DAYS must be a positive integer") from exc
        if str(retention_text).strip() != str(retention_days) or retention_days <= 0:
            raise ValueError("QE_TELEMETRY_RETENTION_DAYS must be a positive integer")
        return cls(database, hash_key, ingest_token, retention_days)
