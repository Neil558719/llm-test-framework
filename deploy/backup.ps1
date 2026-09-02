param([string]$Volume = "local-production-drill_reference-agent-data", [string]$OutputDirectory = "deploy/backups")
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force $OutputDirectory | Out-Null
$target = Join-Path $OutputDirectory ("reference_agent_{0:yyyyMMdd_HHmmss}.db" -f (Get-Date))
docker compose stop reference-agent
if ($LASTEXITCODE -ne 0) { throw "Unable to stop service before backup" }
docker run --rm -v "${Volume}:/data:ro" -v "${PWD}\${OutputDirectory}:/backup" alpine:3.20 cp /data/reference_agent.db "/backup/$(Split-Path $target -Leaf)"
if ($LASTEXITCODE -ne 0) { throw "Database backup failed" }
docker compose start reference-agent
if ($LASTEXITCODE -ne 0) { throw "Unable to restart service after backup" }
if (-not (Test-Path $target)) { throw "Backup file was not created" }
Write-Host "Backup written to $target"
