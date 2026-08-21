# Fixed Commands

All commands below must run in conda env `helth`.

Do not replace them with bare `python` or bare `pytest`.

## Backend start

```powershell
conda run -n helth powershell -ExecutionPolicy Bypass -File .\scripts\start_server.ps1
```

## Frontend start

```powershell
conda run -n helth powershell -ExecutionPolicy Bypass -File .\scripts\start_frontend.ps1
```

## Run all tests

```powershell
conda run -n helth pytest
```

## Run smoke test

```powershell
conda run -n helth powershell -ExecutionPolicy Bypass -File .\scripts\run_smoke_tests.ps1 -BuildFrontend
```

## Run backend HTTP smoke check

```powershell
conda run -n helth powershell -ExecutionPolicy Bypass -File .\scripts\smoke_backend_http.ps1
```

## Run a single pytest file

```powershell
conda run -n helth pytest tests\test_chat_api.py
```

## Print the active interpreter explicitly

```powershell
conda run -n helth python -c "import sys; print(sys.executable)"
```

Expected output:

```text
C:\Users\13010\anaconda3\envs\helth\python.exe
```
