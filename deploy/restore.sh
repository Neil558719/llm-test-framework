#!/usr/bin/env sh
set -eu

if [ "$#" -ne 1 ] || [ ! -f "$1" ]; then echo "usage: deploy/restore.sh BACKUP_DB" >&2; exit 2; fi
# Docker Compose consumes this ordered list on every operation, including restart.
export COMPOSE_PATH_SEPARATOR="${COMPOSE_PATH_SEPARATOR:-:}"
export COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml${COMPOSE_PATH_SEPARATOR}docker-compose.production.yml}"
database_path="${DATABASE_PATH:-/data/reference_agent.db}"
volume="${REFERENCE_AGENT_VOLUME:-local-production-drill_reference-agent-data}"
report="${REPORT_PATH:-reports/restore.json}"
pull_policy="${COMPOSE_PULL_POLICY:-always}"
case "$database_path" in /data/*) ;; *) echo "DATABASE_PATH must be inside /data" >&2; exit 2;; esac
case "$pull_policy" in always|missing|never) ;; *) echo "COMPOSE_PULL_POLICY must be always, missing, or never" >&2; exit 2;; esac
export DATABASE_PATH="$database_path"
export REFERENCE_AGENT_VOLUME="$volume"

backup="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
backup_dir="$(dirname "$backup")"
backup_name="$(basename "$backup")"
manifest_name="$backup_name.manifest.json"
test -f "$backup_dir/$manifest_name"
mkdir -p "$(dirname "$report")"
stopped=0
restart_service() {
  if [ "$stopped" -eq 1 ]; then
    docker compose up -d --pull "$pull_policy" --wait
  fi
}
trap restart_service EXIT INT TERM
docker compose stop reference-agent
stopped=1

docker compose run --pull "$pull_policy" --rm --no-deps -v "$backup_dir:/backup:ro" --entrypoint python reference-agent -c '
import sqlite3
import sys
from pathlib import Path
from qe_platform.ops import restore_database
from reference_agent.storage import _MIGRATIONS

backup, target = map(Path, sys.argv[1:])
if target.exists():
    connection = sqlite3.connect(str(target))
    try:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        connection.close()
    for suffix in ("-wal", "-shm"):
        Path(str(target) + suffix).unlink(missing_ok=True)
expected = {"reference_agent": max(migration.version for migration in _MIGRATIONS)}
restore_database(backup, target, expected)
' "/backup/$backup_name" "$database_path"

docker run --rm -v "$volume:/data:ro" python:3.12-alpine python -c "import sqlite3,sys; result=sqlite3.connect(sys.argv[1]).execute('PRAGMA integrity_check').fetchone()[0]; sys.exit(0 if result == 'ok' else 1)" "$database_path"
restart_service
stopped=0
trap - EXIT INT TERM

python - "$report" "$backup" "$database_path" <<'PY'
import json
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(
    json.dumps({"operation": "restore", "status": "ok", "backup_path": sys.argv[2], "database_path": sys.argv[3]}, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY
