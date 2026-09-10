param(
    [string]$ComposeFile = "docker-compose.yml",
    [string]$DatabasePath = "/data/reference_agent.db",
    [string]$Volume = "local-production-drill_reference-agent-data",
    [string]$ReportPath = "reports/migrate.json"
)

$ErrorActionPreference = "Stop"
if (-not $DatabasePath.StartsWith("/data/")) { throw "DatabasePath must be inside /data" }
$env:DATABASE_PATH = $DatabasePath
$env:REFERENCE_AGENT_VOLUME = $Volume
$reportDirectory = Split-Path -Parent $ReportPath
if ($reportDirectory) { New-Item -ItemType Directory -Force $reportDirectory | Out-Null }

docker compose -f $ComposeFile run --rm --no-deps --entrypoint python reference-agent -c "from reference_agent.app import create_app; create_app()"
if ($LASTEXITCODE -ne 0) { throw "Database migration failed" }
docker run --rm -v "${Volume}:/data:ro" python:3.12-alpine python -c "import sqlite3,sys; result=sqlite3.connect(sys.argv[1]).execute('PRAGMA integrity_check').fetchone()[0]; sys.exit(0 if result == 'ok' else 1)" $DatabasePath
if ($LASTEXITCODE -ne 0) { throw "Database integrity check failed" }

[ordered]@{ operation = "migrate"; status = "ok"; database_path = $DatabasePath } |
    ConvertTo-Json -Compress | Set-Content -LiteralPath $ReportPath -Encoding utf8
