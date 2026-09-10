param(
    [Parameter(Mandatory=$true)][string]$ImageTag,
    [string]$ImageDigest = "",
    [string]$ComposeFile = "docker-compose.yml",
    [string]$ReportPath = "reports/rollback.json"
)
$ErrorActionPreference = "Stop"
$env:IMAGE_TAG = $ImageTag
if ($ImageDigest) { $env:REFERENCE_AGENT_IMAGE_DIGEST = $ImageDigest }
$reportDirectory = Split-Path -Parent $ReportPath
if ($reportDirectory) { New-Item -ItemType Directory -Force $reportDirectory | Out-Null }
docker compose -f $ComposeFile up -d --no-build --wait
if ($LASTEXITCODE -ne 0) { throw "Rollback compose command failed" }
docker compose -f $ComposeFile ps
if ($LASTEXITCODE -ne 0) { throw "Rollback status check failed" }
[ordered]@{ operation = "rollback"; status = "ok"; image_tag = $ImageTag; image_digest = $ImageDigest } |
    ConvertTo-Json -Compress | Set-Content -LiteralPath $ReportPath -Encoding utf8
Write-Host "Rolled back to image tag $ImageTag; run smoke.ps1 to verify."
