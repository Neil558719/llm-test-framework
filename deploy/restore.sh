#!/usr/bin/env sh
set -eu
if [ "$#" -ne 1 ] || [ ! -f "$1" ]; then echo "usage: deploy/restore.sh BACKUP_DB" >&2; exit 2; fi
backup="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
backup_dir="$(dirname "$backup")"
backup_name="$(basename "$backup")"
volume="${REFERENCE_AGENT_VOLUME:-local-production-drill_reference-agent-data}"
stopped=0
restart_service() { if [ "$stopped" -eq 1 ]; then docker compose up -d --wait; fi; }
trap restart_service EXIT INT TERM
docker compose stop reference-agent
stopped=1
docker run --rm -v "$volume:/data" -v "$backup_dir:/backup:ro" alpine:3.20 sh -c "cp '/backup/$backup_name' /data/reference_agent.db && chown 10001:10001 /data/reference_agent.db"
docker run --rm -v "$volume:/data:ro" python:3.12-alpine python -c "import sqlite3,sys; result=sqlite3.connect('/data/reference_agent.db').execute('PRAGMA integrity_check').fetchone()[0]; sys.exit(0 if result == 'ok' else 1)"
restart_service
stopped=0
trap - EXIT INT TERM
