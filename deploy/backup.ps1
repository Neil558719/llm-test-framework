param([string]$Volume = "local-production-drill_reference-agent-data", [string]$OutputDirectory = "deploy/backups")
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force $OutputDirectory | Out-Null
$target = Join-Path $OutputDirectory ("reference_agent_{0:yyyyMMdd_HHmmss}.db" -f (Get-Date))
docker run --rm -v "${Volume}:/data:ro" -v "${PWD}\${OutputDirectory}:/backup" alpine:3.20 cp /data/reference_agent.db "/backup/$(Split-Path $target -Leaf)"
Write-Host "Backup written to $target"
