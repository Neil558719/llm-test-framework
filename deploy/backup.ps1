param([string]$Volume = "local-production-drill_reference-agent-data", [string]$OutputDirectory = "deploy/backups")
$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force $OutputDirectory | Out-Null
$resolvedOutput = (Resolve-Path -LiteralPath $OutputDirectory).Path
$targetName = "reference_agent_{0:yyyyMMdd_HHmmss_fff}.db" -f (Get-Date).ToUniversalTime()
$target = Join-Path $resolvedOutput $targetName
$operationError = $null
$serviceStopped = $false
try {
  docker compose stop reference-agent
  if ($LASTEXITCODE -ne 0) { throw "Unable to stop service before backup" }
  $serviceStopped = $true
  docker run --rm -v "${Volume}:/data:ro" -v "${resolvedOutput}:/backup" alpine:3.20 cp /data/reference_agent.db "/backup/$targetName"
  if ($LASTEXITCODE -ne 0) { throw "Database backup failed" }
  if (-not (Test-Path -LiteralPath $target)) { throw "Backup file was not created" }
  docker run --rm -v "${resolvedOutput}:/backup:ro" python:3.12-alpine python -c "import sqlite3,sys; result=sqlite3.connect('/backup/$targetName').execute('PRAGMA integrity_check').fetchone()[0]; sys.exit(0 if result == 'ok' else 1)"
  if ($LASTEXITCODE -ne 0) { throw "Backup integrity check failed" }
} catch {
  $operationError = $_
} finally {
  if ($serviceStopped) {
    docker compose up -d --wait
    if ($LASTEXITCODE -ne 0 -and $null -eq $operationError) { $operationError = [Exception]::new("Service did not become healthy after backup") }
  }
}
if ($null -ne $operationError) { throw $operationError }
Write-Host "Backup written to $target"
