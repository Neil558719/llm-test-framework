param([Parameter(Mandatory=$true)][string]$ImageTag, [string]$ComposeFile = "docker-compose.yml")
$ErrorActionPreference = "Stop"
$env:IMAGE_TAG = $ImageTag
docker compose -f $ComposeFile up -d --no-build --wait
docker compose -f $ComposeFile ps
Write-Host "Rolled back to image tag $ImageTag; run smoke.ps1 to verify."
