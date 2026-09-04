param([string]$ComposeFile = "docker-compose.yml")
$ErrorActionPreference = "Stop"

# Docker injects .env values only when the container is created. Force a
# recreate so changed model settings cannot remain stale in the running app.
docker compose -f $ComposeFile up -d --build --force-recreate --wait
if ($LASTEXITCODE -ne 0) { throw "Reference Agent recreate failed" }

$config = Invoke-RestMethod -Method Get -Uri "http://localhost:8000/api/model-profiles"
$config.current | ConvertTo-Json -Depth 5
Write-Host "Reference Agent model configuration refreshed."
