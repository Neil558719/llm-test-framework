param(
  [string]$ComposeFile = "docker-compose.yml",
  [string]$DatabasePath = "/data/reference_agent.db",
  [string]$Volume = "local-production-drill_reference-agent-data",
  [string]$OutputDirectory = "deploy/backups",
  [string]$ReportPath = "reports/backup.json"
)

$ErrorActionPreference = "Stop"
if (-not $DatabasePath.StartsWith("/data/")) { throw "DatabasePath must be inside /data" }
$env:DATABASE_PATH = $DatabasePath
$env:REFERENCE_AGENT_VOLUME = $Volume
New-Item -ItemType Directory -Force $OutputDirectory | Out-Null
$resolvedOutput = (Resolve-Path -LiteralPath $OutputDirectory).Path
$reportDirectory = Split-Path -Parent $ReportPath
if ($reportDirectory) { New-Item -ItemType Directory -Force $reportDirectory | Out-Null }
$targetName = "reference_agent_{0:yyyyMMdd_HHmmss_fff}.db" -f (Get-Date).ToUniversalTime()
$target = Join-Path $resolvedOutput $targetName
$operationError = $null
try {
  docker compose -f $ComposeFile run --rm --no-deps -v "${resolvedOutput}:/backup" --entrypoint python reference-agent -c "import sys; from pathlib import Path; from qe_platform.ops import backup_database; backup_database(Path(sys.argv[1]), Path(sys.argv[2]))" $DatabasePath "/backup/$targetName"
  if ($LASTEXITCODE -ne 0) { throw "Database backup failed" }
  if (-not (Test-Path -LiteralPath $target) -or -not (Test-Path -LiteralPath "$target.manifest.json")) { throw "Backup files were not created" }
  docker run --rm -v "${resolvedOutput}:/backup:ro" python:3.12-alpine python -c "import sqlite3,sys; result=sqlite3.connect('/backup/$targetName').execute('PRAGMA integrity_check').fetchone()[0]; sys.exit(0 if result == 'ok' else 1)"
  if ($LASTEXITCODE -ne 0) { throw "Backup integrity check failed" }
} catch {
  $operationError = $_
} finally {
  # Recheck readiness even though online backup does not stop the service.
  docker compose -f $ComposeFile up -d --wait
  if ($LASTEXITCODE -ne 0 -and $null -eq $operationError) { $operationError = [Exception]::new("Service did not become healthy after backup") }
}
if ($null -ne $operationError) { throw $operationError }

$sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $target).Hash.ToLowerInvariant()
[ordered]@{ operation = "backup"; status = "ok"; backup_path = $target; sha256 = $sha256 } |
  ConvertTo-Json -Compress | Set-Content -LiteralPath $ReportPath -Encoding utf8
Write-Host "Backup written to $target"
