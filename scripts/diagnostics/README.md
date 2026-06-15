# Diagnostics Scripts

These scripts are small, terminal-first probes for local development and onsite debugging.

## Conda environment

Use the dedicated lightweight environment:

```powershell
conda activate health-diagnostics
```

Or run without activation:

```powershell
conda run -n health-diagnostics python scripts\diagnostics\probe_backend_health.py
```

Interpreter path for PyCharm:

```text
C:\Users\YANG\.conda\envs\health-diagnostics\python.exe
```

## Most useful camera commands

Camera status and configured source:

```powershell
python scripts\diagnostics\probe_camera_status.py --timeout 30
```

Direct RTSP matrix check:

```powershell
python scripts\diagnostics\probe_rtsp_matrix.py --timeout 2
```

Snapshot check:

```powershell
python scripts\diagnostics\probe_camera_snapshot.py --timeout 15
```

Continuous MJPEG stream watch:

```powershell
python scripts\diagnostics\watch_camera_stream.py --timeout 10
```

If video frames are entering correctly, the terminal prints lines like:

```text
[16:42:03] frame=1 frame_bytes=73421 total_bytes=81222 fps=1.00
[16:42:04] frame=2 frame_bytes=72880 total_bytes=154102 fps=1.00
```

If no frame enters, it prints the HTTP status, timeout, or RTSP error directly.

## Other feature probes

Backend:

```powershell
python scripts\diagnostics\probe_backend_health.py
python scripts\diagnostics\watch_backend_health.py
```

Health scoring:

```powershell
python scripts\diagnostics\probe_health_score.py
```

Device/auth:

```powershell
python scripts\diagnostics\probe_auth_flow.py --timeout 30
python scripts\diagnostics\probe_device_flow.py --timeout 30
```

Realtime WebSocket:

```powershell
python scripts\diagnostics\watch_health_ws.py --device-mac 53:57:08:00:00:01
python scripts\diagnostics\watch_alarm_ws.py
```

Agent and fine-tuning:

```powershell
python scripts\diagnostics\probe_agent.py --timeout 30
python scripts\diagnostics\probe_model_finetune.py --timeout 30
python scripts\diagnostics\watch_chat_stream.py --timeout 30
```

All one-shot checks:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\diagnostics\run_all_diagnostics.ps1 -Timeout 30
```

## Current known observation

On the machine used to create these scripts, the backend is healthy and several business probes pass.
The camera HTTP MJPEG endpoints open, but no JPEG frame is currently received. Raw RTSP probes to
`192.168.8.248`, `192.168.8.253`, and `192.168.8.254` on ports `554` and `10554` time out, so the
next onsite check should confirm the camera's current IP, RTSP port, and whether the camera is powered
and reachable from the Windows WLAN interface.
