param(
  [string]$BaseUrl = "http://localhost:8000",
  [string]$ReportPath = "reports/smoke.json",
  [string]$BearerTokenFile = ""
)
$ErrorActionPreference = "Stop"
$reportDirectory = Split-Path -Parent $ReportPath
if ($reportDirectory) { New-Item -ItemType Directory -Force $reportDirectory | Out-Null }
$results = @()
$headers = @{}
if ($BearerTokenFile) {
  if (-not (Test-Path -LiteralPath $BearerTokenFile)) { throw "Bearer token file is unavailable" }
  $headers.Authorization = "Bearer $((Get-Content -LiteralPath $BearerTokenFile -Raw).TrimEnd("`r", "`n"))"
}
function Check($Name, $Method, $Uri, $Body) {
  $response = if ($Method -eq "GET") { Invoke-RestMethod -Method Get -Uri $Uri -Headers $headers } else { Invoke-RestMethod -Method Post -Uri $Uri -Headers $headers -ContentType "application/json" -Body ($Body | ConvertTo-Json) }
  if ($Name -eq "health" -and -not ($response.status -eq "ok")) { throw "Health payload did not report status=ok" }
  if ($Name -eq "knowledge" -and ([string]::IsNullOrWhiteSpace($response.answer) -or [string]::IsNullOrWhiteSpace($response.trace_id))) { throw "Knowledge response contract failed" }
  if ($Name -eq "ticket" -and $response.metadata.ticket_status -ne "created") { throw "Ticket workflow failed" }
  if ($Name -eq "access" -and $response.metadata.approval_status -ne "pending") { throw "Approval workflow failed" }
  $script:results += [ordered]@{name=$Name; passed=$true}
}
Check "health" "GET" "$BaseUrl/api/health" $null
Check "knowledge" "POST" "$BaseUrl/api/chat" @{message="如何申请 VPN 权限？"; user_id="U1001"}
Check "ticket" "POST" "$BaseUrl/api/chat" @{message="我的 VPN 无法连接，设备编号是 PC-1001，请帮我创建工单"; user_id="U1001"}
Check "access" "POST" "$BaseUrl/api/chat" @{message="申请安装 VPN，理由是远程办公"; user_id="U1001"}
$payload = [ordered]@{ operation = "smoke"; status = "ok"; checks = $results }
$payload | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 $ReportPath
Write-Host "Smoke passed: $($results.Count) checks"
