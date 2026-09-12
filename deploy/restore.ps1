param(
    [Parameter(Mandatory=$true)][string]$BackupPath,
    [Alias("ComposeFile")][string[]]$ComposeFiles = @("docker-compose.yml", "docker-compose.production.yml"),
    [string]$DatabasePath = "/data/reference_agent.db",
    [string]$Volume = "local-production-drill_reference-agent-data",
    [ValidateSet("always", "missing", "never")][string]$PullPolicy = "always",
    [string]$ReportPath = "reports/restore.json"
)
$ErrorActionPreference = "Stop"
$composeArgs = @()
foreach ($file in $ComposeFiles) {
    if ([string]::IsNullOrWhiteSpace($file)) { throw "Compose file list must not contain empty paths" }
    $composeArgs += @("-f", $file)
}
if ($composeArgs.Count -eq 0) { throw "Compose file list must not be empty" }
if (-not $DatabasePath.StartsWith("/data/")) { throw "DatabasePath must be inside /data" }
$env:DATABASE_PATH = $DatabasePath
$env:REFERENCE_AGENT_VOLUME = $Volume
$backup = (Resolve-Path -LiteralPath $BackupPath).Path
if (-not (Test-Path -LiteralPath "$backup.manifest.json")) { throw "Backup manifest is missing" }
$backupDirectory = Split-Path -Parent $backup
$backupName = Split-Path -Leaf $backup
$reportDirectory = Split-Path -Parent $ReportPath
if ($reportDirectory) { New-Item -ItemType Directory -Force $reportDirectory | Out-Null }
docker compose @composeArgs stop reference-agent
if ($LASTEXITCODE -ne 0) { throw "Service stop failed" }
$restoreCode = @"
import sqlite3, sys
from pathlib import Path
from qe_platform.ops import restore_database
from reference_agent.storage import _MIGRATIONS
backup, target = map(Path, sys.argv[1:])
if target.exists():
    connection = sqlite3.connect(str(target))
    try:
        connection.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    finally:
        connection.close()
    for suffix in ('-wal', '-shm'):
        Path(str(target) + suffix).unlink(missing_ok=True)
restore_database(backup, target, {'reference_agent': max(item.version for item in _MIGRATIONS)})
"@
docker compose @composeArgs run --pull $PullPolicy --rm --no-deps -v "${backupDirectory}:/backup:ro" --entrypoint python reference-agent -c $restoreCode "/backup/$backupName" $DatabasePath
if ($LASTEXITCODE -ne 0) { throw "Restore failed; service remains stopped for inspection" }
docker compose @composeArgs up -d --pull $PullPolicy --wait
if ($LASTEXITCODE -ne 0) { throw "Restored service readiness failed" }
[ordered]@{ operation = "restore"; status = "ok"; database_path = $DatabasePath } |
    ConvertTo-Json -Compress | Set-Content -LiteralPath $ReportPath -Encoding utf8
