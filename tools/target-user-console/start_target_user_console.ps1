$port = 9200
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = "C:\Users\YANG\.conda\envs\AI\python.exe"

$existing = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue | Where-Object { $_.State -eq "Listen" } | Select-Object -First 1
if ($existing) {
  Write-Host "target-user-console is already listening on http://127.0.0.1:$port/"
  Start-Process "http://127.0.0.1:$port/"
  exit 0
}

if (-not (Test-Path $python)) {
  throw "Python not found: $python"
}

$out = Join-Path $root "target-user-console.out.log"
$err = Join-Path $root "target-user-console.err.log"

$proc = Start-Process `
  -FilePath $python `
  -ArgumentList @("-m", "http.server", "$port", "--bind", "127.0.0.1") `
  -WorkingDirectory $root `
  -RedirectStandardOutput $out `
  -RedirectStandardError $err `
  -WindowStyle Hidden `
  -PassThru

Start-Sleep -Seconds 2
Start-Process "http://127.0.0.1:$port/"
Write-Host "target-user-console started at http://127.0.0.1:$port/ (PID: $($proc.Id))"
