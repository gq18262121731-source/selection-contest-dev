# Mobile Connection Troubleshooting

## The only backend address the mobile app should use

For real Android phones on the same Wi-Fi as the development PC:

- Backend port: `8000`
- Example origin: `http://192.168.8.252:8000`

Do **not** use:

- `10.0.2.2` on a real phone
- `127.0.0.1`
- `localhost`
- frontend ports such as `5173`, `5182`
- tool ports such as `7860`, `7861`, `8090`

## Fast checklist

1. Open `http://<PC-LAN-IP>:8000/healthz` in the phone browser.
2. If that works, enter the same IP and port into the mobile app server settings.
3. If it does not work, check:
   - the phone and PC are on the same Wi-Fi
   - Windows firewall allows TCP `8000`
   - the backend is listening on `0.0.0.0:8000`

## Typical mistakes

### Wrong subnet

- PC is `192.168.8.xxx`
- phone app is configured to `192.168.2.xxx`

This will time out even if the backend is healthy.

### Wrong port

The mobile app must use backend `8000`.
It cannot log in through:

- `5173`
- `5182`
- `7860`
- `7861`
- `8090`

### Emulator-only host on a real phone

`10.0.2.2` only works for Android emulators.

## Backend verification

On the PC:

```powershell
Invoke-WebRequest http://127.0.0.1:8000/healthz
```

Expected:

```json
{"status":"ok","app":"AIoT Elder Care Monitoring System"}
```

## Windows firewall rule

If the phone browser cannot open `http://<PC-LAN-IP>:8000/healthz`, allow inbound TCP 8000:

```powershell
New-NetFirewallRule -DisplayName "AIoT Health Backend" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
```

## Current project note

This project now prints a suggested mobile backend address when `scripts/start_server.ps1` starts successfully.
