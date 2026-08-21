param(
    [string]$TaskName = "CameraRuntime8090"
)

Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "Scheduled task removed (if it existed)."
Write-Host ("TaskName: " + $TaskName)

