param([Parameter(Mandatory=$true)][string]$ImageTag, [string]$ComposeFile = "docker-compose.yml")
$ErrorActionPreference = "Stop"
$env:IMAGE_TAG = $ImageTag
docker compose -f $ComposeFile up -d --no-build --wait
if ($LASTEXITCODE -ne 0) { throw "Rollback compose command failed" }
docker compose -f $ComposeFile ps
if ($LASTEXITCODE -ne 0) { throw "Rollback status check failed" }
Write-Host "Rolled back to image tag $ImageTag; run smoke.ps1 to verify."
