param(
    [string]$Prefix = "192.168.8",
    [int]$Start = 2,
    [int]$End = 254,
    [int[]]$Ports = @(80, 554, 10554, 10080, 9502),
    [int]$TimeoutMs = 250
)

function Test-TcpPort {
    param(
        [string]$TargetHost,
        [int]$Port,
        [int]$TimeoutMs = 250
    )

    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect($TargetHost, $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) {
            return $false
        }
        $client.EndConnect($async) | Out-Null
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

$results = @()
for ($i = $Start; $i -le $End; $i++) {
    $ip = "$Prefix.$i"
    $openPorts = @()
    foreach ($port in $Ports) {
        if (Test-TcpPort -TargetHost $ip -Port $port -TimeoutMs $TimeoutMs) {
            $openPorts += $port
        }
    }
    if ($openPorts.Count -gt 0) {
        $results += [PSCustomObject]@{
            IP        = $ip
            OpenPorts = ($openPorts -join ",")
            RtspSub   = "rtsp://admin:YOUR_PASSWORD@${ip}:10554/tcp/av0_1"
            RtspMain  = "rtsp://admin:YOUR_PASSWORD@${ip}:10554/tcp/av0_0"
            Onvif     = "http://${ip}:10080/onvif/device_service"
            Web9502   = "http://${ip}:9502/"
        }
    }
}

if ($results.Count -eq 0) {
    Write-Host "No candidate device was found in subnet $Prefix.0/24"
    exit 4
}

$results | Format-Table -AutoSize

