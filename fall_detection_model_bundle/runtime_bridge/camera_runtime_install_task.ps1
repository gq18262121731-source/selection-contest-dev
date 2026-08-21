param(
    [string]$TaskName = "CameraRuntime8090",
    [string]$Config = "camera_live_config.json",
    [ValidateSet("av0_1", "av0_0")]
    [string]$Stream = "av0_1",
    [int]$ListenPort = 8090,
    [switch]$AtStartup
)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$startScript = Join-Path $root "camera_runtime_start.ps1"
if (-not (Test-Path $startScript)) {
    Write-Host "camera_runtime_start.ps1 was not found."
    exit 2
}

$psArgs = "-ExecutionPolicy Bypass -File `"$startScript`" -Config `"$Config`" -Stream $Stream -ListenPort $ListenPort"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $psArgs

if ($AtStartup) {
    $trigger = New-ScheduledTaskTrigger -AtStartup
} else {
    $trigger = New-ScheduledTaskTrigger -AtLogOn
}

$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null

Write-Host "Scheduled task installed."
Write-Host ("TaskName: " + $TaskName)
Write-Host ("Mode: " + ($(if ($AtStartup) { "AtStartup" } else { "AtLogOn" })))

