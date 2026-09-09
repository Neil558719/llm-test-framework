from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Sequence

from qe_platform.storage import create_telemetry_repository, prune_expired
from qe_platform.telemetry.settings import TelemetrySettings


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args:
        print("Configuration error: telemetry-prune does not accept command-line arguments", file=sys.stderr)
        return 2
    try:
        settings = TelemetrySettings.from_environment()
        repository = create_telemetry_repository(
            settings.database,
            retention_days=settings.retention_days,
            hash_key=settings.hash_key,
        )
    except (ValueError, NotImplementedError) as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    try:
        deleted = prune_expired(repository, now=datetime.now(timezone.utc))
    except Exception as exc:
        print(f"Prune error: {exc}", file=sys.stderr)
        return 1
    finally:
        close = getattr(locals().get("repository", None), "close", None)
        if close is not None:
            close()
    noun = "trace" if deleted == 1 else "traces"
    print(f"Deleted {deleted} expired telemetry {noun}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
