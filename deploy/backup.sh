#!/usr/bin/env sh
set -eu
volume="${REFERENCE_AGENT_VOLUME:-local-production-drill_reference-agent-data}"
output_dir="${BACKUP_DIR:-deploy/backups}"
mkdir -p "$output_dir"
output_dir="$(cd "$output_dir" && pwd)"
target="reference_agent_$(date -u +%Y%m%d_%H%M%S)_$$.db"
stopped=0
restart_service() { if [ "$stopped" -eq 1 ]; then docker compose up -d --wait; fi; }
trap restart_service EXIT INT TERM
docker compose stop reference-agent
stopped=1
docker run --rm -v "$volume:/data:ro" -v "$output_dir:/backup" alpine:3.20 cp /data/reference_agent.db "/backup/$target"
docker run --rm -v "$output_dir:/backup:ro" python:3.12-alpine python -c "import sqlite3,sys; result=sqlite3.connect('/backup/$target').execute('PRAGMA integrity_check').fetchone()[0]; sys.exit(0 if result == 'ok' else 1)"
restart_service
stopped=0
trap - EXIT INT TERM
printf '%s\n' "$output_dir/$target"
