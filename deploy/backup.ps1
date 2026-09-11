param(
  [Alias("ComposeFile")][string[]]$ComposeFiles = @("docker-compose.yml", "docker-compose.production.yml"),
  [string]$DatabasePath = "/data/reference_agent.db",
  [string]$Volume = "local-production-drill_reference-agent-data",
  [string]$OutputDirectory = "deploy/backups",
  [ValidateSet("always", "missing", "never")][string]$PullPolicy = "always",
  [string]$ReportPath = "reports/backup.json"
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
New-Item -ItemType Directory -Force $OutputDirectory | Out-Null
$resolvedOutput = (Resolve-Path -LiteralPath $OutputDirectory).Path
$reportDirectory = Split-Path -Parent $ReportPath
if ($reportDirectory) { New-Item -ItemType Directory -Force $reportDirectory | Out-Null }
$targetName = "reference_agent_{0:yyyyMMdd_HHmmss_fff}.db" -f (Get-Date).ToUniversalTime()
$target = Join-Path $resolvedOutput $targetName
docker compose @composeArgs run --pull $PullPolicy --rm --no-deps -v "${resolvedOutput}:/backup" --entrypoint python reference-agent -c "import sys; from pathlib import Path; from qe_platform.ops import backup_database; backup_database(Path(sys.argv[1]), Path(sys.argv[2]))" $DatabasePath "/backup/$targetName"
if ($LASTEXITCODE -ne 0) { throw "Database backup failed" }
if (-not (Test-Path -LiteralPath $target) -or -not (Test-Path -LiteralPath "$target.manifest.json")) { throw "Backup files were not created" }
docker run --rm -v "${resolvedOutput}:/backup:ro" python:3.12-alpine python -c "import sqlite3,sys; result=sqlite3.connect('file:/backup/$targetName?mode=ro&immutable=1', uri=True).execute('PRAGMA integrity_check').fetchone()[0]; sys.exit(0 if result == 'ok' else 1)"
if ($LASTEXITCODE -ne 0) { throw "Backup integrity check failed" }

$sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $target).Hash.ToLowerInvariant()
[ordered]@{ operation = "backup"; status = "ok"; backup_path = $target; sha256 = $sha256 } |
  ConvertTo-Json -Compress | Set-Content -LiteralPath $ReportPath -Encoding utf8
Write-Host "Backup written to $target"
