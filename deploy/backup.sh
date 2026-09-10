#!/usr/bin/env sh
set -eu

compose_file="${COMPOSE_FILE:-docker-compose.yml}"
database_path="${DATABASE_PATH:-/data/reference_agent.db}"
volume="${REFERENCE_AGENT_VOLUME:-local-production-drill_reference-agent-data}"
output_dir="${BACKUP_DIR:-deploy/backups}"
report="${REPORT_PATH:-reports/backup.json}"

case "$database_path" in /data/*) ;; *) echo "DATABASE_PATH must be inside /data" >&2; exit 2;; esac
export DATABASE_PATH="$database_path"
export REFERENCE_AGENT_VOLUME="$volume"
mkdir -p "$output_dir" "$(dirname "$report")"
output_dir="$(cd "$output_dir" && pwd)"
target="reference_agent_$(date -u +%Y%m%d_%H%M%S)_$$.db"
published=0
cleanup() {
  if [ "$published" -eq 0 ]; then
    rm -f "$output_dir/$target" "$output_dir/$target.manifest.json"
  fi
}
trap cleanup EXIT INT TERM

# The helper uses SQLite's online backup API, so a healthy service remains available.
docker compose -f "$compose_file" run --rm --no-deps -v "$output_dir:/backup" --entrypoint python reference-agent -c '
import sys
from pathlib import Path
from qe_platform.ops import backup_database
backup_database(Path(sys.argv[1]), Path(sys.argv[2]))
' "$database_path" "/backup/$target"
test -f "$output_dir/$target"
test -f "$output_dir/$target.manifest.json"
docker run --rm -v "$output_dir:/backup:ro" python:3.12-alpine python -c "import sqlite3,sys; result=sqlite3.connect('/backup/$target').execute('PRAGMA integrity_check').fetchone()[0]; sys.exit(0 if result == 'ok' else 1)"
published=1

python - "$report" "$output_dir/$target" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

backup = Path(sys.argv[2])
payload = {
    "operation": "backup",
    "status": "ok",
    "backup_path": str(backup),
    "sha256": hashlib.sha256(backup.read_bytes()).hexdigest(),
}
Path(sys.argv[1]).write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
PY
trap - EXIT INT TERM
printf '%s\n' "$output_dir/$target"
