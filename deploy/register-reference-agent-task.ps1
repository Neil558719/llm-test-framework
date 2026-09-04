param(
    [string]$TaskName = "LLMTest Reference Agent Auto Refresh",
    [int]$DelaySeconds = 30,
    [switch]$Unregister
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$startupScript = Join-Path $projectRoot "deploy\start-reference-agent.ps1"
$currentUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name

function Get-RegisteredTaskOrNull {
    param([string]$Name)

    try {
        return Get-ScheduledTask -TaskName $Name -ErrorAction Stop
    } catch {
        if ($_.FullyQualifiedErrorId -like "CmdletizationQuery_NotFound_TaskName,*") {
            return $null
        }
        throw
    }
}

if ($Unregister) {
    $existingTask = Get-RegisteredTaskOrNull -Name $TaskName
    if ($existingTask) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction Stop
        if (Get-RegisteredTaskOrNull -Name $TaskName) {
            throw ("Scheduled task still exists after removal: {0}" -f $TaskName)
        }
        Write-Host ("Removed scheduled task: {0}" -f $TaskName)
    } else {
        Write-Host ("Scheduled task is not registered: {0}" -f $TaskName)
    }
    exit 0
}

if (-not (Test-Path -LiteralPath $startupScript -PathType Leaf)) {
    throw ("Reference Agent startup script was not found: {0}" -f $startupScript)
}

$powerShell = (Get-Command powershell.exe -ErrorAction Stop).Source
$escapedScript = $startupScript.Replace("'", "''")
$delay = [Math]::Max(0, $DelaySeconds)
$actionCommand = "Start-Sleep -Seconds {0}; & '{1}'" -f $delay, $escapedScript
$action = New-ScheduledTaskAction -Execute $powerShell -Argument ("-NoProfile -ExecutionPolicy Bypass -Command `"& {{ {0} }}`"" -f $actionCommand) -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $currentUser
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RestartCount 5 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)
$principal = New-ScheduledTaskPrincipal `
    -UserId $currentUser `
    -LogonType Interactive `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Starts the local Reference Agent and its .env auto-refresh watcher after user logon." `
    -Force | Out-Null

Write-Host ("Registered scheduled task: {0}" -f $TaskName)
Write-Host ("Trigger: current-user logon with a {0}s startup delay; up to 5 one-minute retries while Docker Desktop starts." -f $delay)
