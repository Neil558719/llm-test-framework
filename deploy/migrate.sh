#!/usr/bin/env sh
set -eu

compose_file="${COMPOSE_FILE:-docker-compose.yml}"
database_path="${DATABASE_PATH:-/data/reference_agent.db}"
volume="${REFERENCE_AGENT_VOLUME:-local-production-drill_reference-agent-data}"
report="${REPORT_PATH:-reports/migrate.json}"

case "$database_path" in /data/*) ;; *) echo "DATABASE_PATH must be inside /data" >&2; exit 2;; esac
export DATABASE_PATH="$database_path"
export REFERENCE_AGENT_VOLUME="$volume"
mkdir -p "$(dirname "$report")"

docker compose -f "$compose_file" run --rm --no-deps --entrypoint python reference-agent -c 'from reference_agent.app import create_app; create_app()'
docker run --rm -v "$volume:/data:ro" python:3.12-alpine python -c 'import sqlite3,sys; path=sys.argv[1]; result=sqlite3.connect(path).execute("PRAGMA integrity_check").fetchone()[0]; sys.exit(0 if result == "ok" else 1)' "$database_path"

python - "$report" "$database_path" <<'PY'
import json
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(
    json.dumps({"operation": "migrate", "status": "ok", "database_path": sys.argv[2]}, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY
