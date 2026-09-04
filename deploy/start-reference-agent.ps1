param(
    [string]$ComposeFile = "docker-compose.yml",
    [int]$WaitTimeout = 120,
    [int]$Port = 0,
    [switch]$WatchOnly
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$composeCandidate = if ([IO.Path]::IsPathRooted($ComposeFile)) { $ComposeFile } else { Join-Path $projectRoot $ComposeFile }
$composePath = (Resolve-Path $composeCandidate).Path
$sha256 = [Security.Cryptography.SHA256]::Create()
try {
    $hashBytes = $sha256.ComputeHash([Text.Encoding]::UTF8.GetBytes($composePath))
} finally {
    $sha256.Dispose()
}
$pathHash = ([BitConverter]::ToString($hashBytes) -replace "-", "").Substring(0, 12)
$watchErrorLog = Join-Path ([IO.Path]::GetTempPath()) ("llmtest-reference-agent-watch-{0}-error.log" -f $pathHash)

function Invoke-ReferenceAgentRefresh {
    docker compose -f $composePath up -d --force-recreate --no-build --wait --wait-timeout $WaitTimeout
    if ($LASTEXITCODE -ne 0) { throw "Reference Agent refresh failed" }
}

if ($WatchOnly) {
    $envPath = Join-Path $projectRoot ".env"
    $watcher = New-Object System.IO.FileSystemWatcher($projectRoot, ".env")
    $watcher.NotifyFilter = [IO.NotifyFilters]::LastWrite -bor [IO.NotifyFilters]::Size -bor [IO.NotifyFilters]::FileName
    $lastWrite = if (Test-Path $envPath) { (Get-Item $envPath).LastWriteTimeUtc } else { [DateTime]::MinValue }
    while ($true) {
        $watcher.WaitForChanged([IO.WatcherChangeTypes]::All, 1000) | Out-Null
        $currentWrite = if (Test-Path $envPath) { (Get-Item $envPath).LastWriteTimeUtc } else { [DateTime]::MinValue }
        if ($currentWrite -ne $lastWrite) {
            Start-Sleep -Milliseconds 500
            try {
                Invoke-ReferenceAgentRefresh
            } catch {
                try {
                    Add-Content -LiteralPath $watchErrorLog -Value ("{0}: {1}" -f (Get-Date -Format o), $_.Exception.Message) -ErrorAction Stop
                } catch {
                    # Logging must never terminate the long-running watcher.
                }
            }
            $lastWrite = $currentWrite
        }
    }
}

docker compose -f $composePath up -d --build --wait --wait-timeout $WaitTimeout
if ($LASTEXITCODE -ne 0) { throw "Reference Agent failed to start" }

$pidFile = Join-Path ([IO.Path]::GetTempPath()) ("llmtest-reference-agent-watch-{0}.pid" -f $pathHash)
$watcherProcess = $null
if (Test-Path $pidFile) {
    $storedPid = 0
    if ([int]::TryParse((Get-Content $pidFile -Raw).Trim(), [ref]$storedPid)) {
        $candidate = Get-CimInstance Win32_Process -Filter ("ProcessId = {0}" -f $storedPid) -ErrorAction SilentlyContinue
        if ($candidate -and $candidate.CommandLine -like "*start-reference-agent.ps1*" -and $candidate.CommandLine -like "*-WatchOnly*" -and $candidate.CommandLine -like "*$composePath*") {
            $watcherProcess = $candidate
        } else {
            Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
        }
    }
}
if (-not $watcherProcess) {
    $outputLog = Join-Path ([IO.Path]::GetTempPath()) ("llmtest-reference-agent-watch-{0}.log" -f $pathHash)
    $errorLog = Join-Path ([IO.Path]::GetTempPath()) ("llmtest-reference-agent-watch-{0}-process-error.log" -f $pathHash)
    $scriptPath = Join-Path $projectRoot "deploy\start-reference-agent.ps1"
    $watchArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$scriptPath`"", "-ComposeFile", "`"$composePath`"", "-WaitTimeout", $WaitTimeout, "-WatchOnly")
    $watcherProcess = Start-Process -FilePath "powershell.exe" -ArgumentList $watchArgs -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput $outputLog -RedirectStandardError $errorLog -PassThru
    Set-Content -LiteralPath $pidFile -Value $watcherProcess.Id -Encoding ascii
    Start-Sleep -Milliseconds 500
    if ($watcherProcess.HasExited) { throw "Reference Agent .env watcher failed to start" }
}

$effectivePort = $Port
if ($effectivePort -le 0) {
    $published = docker compose -f $composePath port reference-agent 8000
    if ($LASTEXITCODE -ne 0 -or -not $published) { throw "Unable to determine Reference Agent published port" }
    $endpoint = ($published | Select-Object -First 1).Trim()
    $effectivePort = [int](($endpoint -split ":")[-1])
}
$health = Invoke-RestMethod -Method Get -Uri ("http://localhost:{0}/api/health" -f $effectivePort)
if ($health.status -ne "ok") { throw "Reference Agent health check failed" }

Write-Host "Reference Agent is running with .env auto-refresh enabled."
Write-Host "Edit .env; the watcher will recreate the service and re-inject model settings."
