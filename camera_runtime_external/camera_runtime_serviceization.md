# Camera Serviceization Notes

## Goal

Add a controllable Windows startup path for the local camera runtime without forcing intrusive changes by default.

## Manual service-like control

Start:

```powershell
powershell -ExecutionPolicy Bypass -File D:\Program\camear_new\camera_runtime_start.ps1
```

Stop:

```powershell
powershell -ExecutionPolicy Bypass -File D:\Program\camear_new\camera_runtime_stop.ps1
```

Status:

```powershell
powershell -ExecutionPolicy Bypass -File D:\Program\camear_new\camera_runtime_status.ps1
```

## Scheduled task installation

Install for current-user logon:

```powershell
powershell -ExecutionPolicy Bypass -File D:\Program\camear_new\camera_runtime_install_task.ps1
```

Install at Windows startup:

```powershell
powershell -ExecutionPolicy Bypass -File D:\Program\camear_new\camera_runtime_install_task.ps1 -AtStartup
```

Remove the scheduled task:

```powershell
powershell -ExecutionPolicy Bypass -File D:\Program\camear_new\camera_runtime_uninstall_task.ps1
```

## No-admin fallback: Startup folder

Install a current-user startup launcher:

```powershell
powershell -ExecutionPolicy Bypass -File D:\Program\camear_new\camera_runtime_install_startup.ps1
```

Remove the startup launcher:

```powershell
powershell -ExecutionPolicy Bypass -File D:\Program\camear_new\camera_runtime_uninstall_startup.ps1
```

## Notes

1. The scheduled task path is implemented but not auto-installed by default.
2. This avoids unexpected persistent changes on the machine.
3. If scheduled task installation is blocked by Windows permissions, the Startup folder fallback can still be used.
4. The runtime still uses RTSP as the source-of-truth ingest path.
