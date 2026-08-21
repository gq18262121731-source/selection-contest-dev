# Camera Runtime Notes

## Goal

Expose the camera as a small local runtime that is easy to integrate into a project backend.

## Current verified RTSP source

```text
Sub stream:
rtsp://admin:admin@192.168.8.248:554/tcp/av0_1

Main stream:
rtsp://admin:admin@192.168.8.248:554/tcp/av0_0
```

## Local runtime entry

Start the local viewer service:

```powershell
powershell -ExecutionPolicy Bypass -File D:\Program\camear_new\camera_runtime_start.ps1
```

Start the main stream instead of the sub stream:

```powershell
powershell -ExecutionPolicy Bypass -File D:\Program\camear_new\camera_runtime_start.ps1 -Stream av0_0
```

Stop the runtime:

```powershell
powershell -ExecutionPolicy Bypass -File D:\Program\camear_new\camera_runtime_stop.ps1
```

Show runtime status:

```powershell
powershell -ExecutionPolicy Bypass -File D:\Program\camear_new\camera_runtime_status.ps1
```

## Config file

Default config:

`D:\Program\camear_new\camera_live_config.json`

Fields:

```json
{
  "camera": {
    "host": "192.168.8.248",
    "username": "admin",
    "password": "admin",
    "rtsp_port": 554,
    "transport": "tcp",
    "stream": "av0_1"
  },
  "viewer": {
    "listen_host": "127.0.0.1",
    "listen_port": 8090,
    "jpeg_quality": 80,
    "frame_interval_seconds": 0.08,
    "log_dir": "runtime_logs",
    "auth_enabled": false,
    "auth_username": "camera",
    "auth_password": "camera"
  }
}
```

## Optional authentication

Authentication is disabled by default for local development.

To enable Basic Auth:

```json
"auth_enabled": true,
"auth_username": "camera",
"auth_password": "camera"
```

Restart the runtime after changing the config.

When auth is enabled:

```text
username: camera
password: camera
```

PowerShell example:

```powershell
$pair = "camera:camera"
$token = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($pair))
$headers = @{ Authorization = "Basic $token" }
Invoke-WebRequest -Uri "http://127.0.0.1:8090/api/v1/camera/health" -Headers $headers
```

## Runtime endpoints

Browser viewer:

```text
http://127.0.0.1:8090/viewer
```

Health:

```text
http://127.0.0.1:8090/health
```

Standard health API:

```text
http://127.0.0.1:8090/api/v1/camera/health
```

Snapshot:

```text
http://127.0.0.1:8090/snapshot.jpg
```

Standard snapshot API:

```text
http://127.0.0.1:8090/api/v1/camera/snapshot
```

MJPEG stream:

```text
http://127.0.0.1:8090/stream.mjpg
```

Standard MJPEG API:

```text
http://127.0.0.1:8090/api/v1/camera/stream.mjpg
```

Switch stream to main:

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:8090/api/v1/camera/stream/switch?stream=av0_0" -Method Post
```

Switch stream back to sub:

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:8090/api/v1/camera/stream/switch?stream=av0_1" -Method Post
```

Logs:

```text
D:\Program\camear_new\runtime_logs\camera_runtime.log
```

## Suggested next integration path

1. Keep RTSP as the source-of-truth input.
2. Use the local runtime for browser preview and debugging.
3. Move the `camera_runtime` package into your real backend service later.
4. Add authentication and process supervision before production use.

## Serviceization helpers

Install the current-user scheduled task:

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
