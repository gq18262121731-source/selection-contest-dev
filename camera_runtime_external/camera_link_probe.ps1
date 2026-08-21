param(
    [string[]]$CandidateIps = @(
        "192.168.0.10",
        "192.168.0.64",
        "192.168.0.100",
        "192.168.0.126",
        "192.168.1.10",
        "192.168.1.64",
        "192.168.1.100",
        "192.168.1.126",
        "192.168.8.10",
        "192.168.8.64",
        "192.168.8.100",
        "192.168.8.253",
        "169.254.1.10",
        "169.254.10.10",
        "169.254.62.1",
        "169.254.62.97"
    ),
    [int[]]$Ports = @(80, 554, 10554, 10080),
    [int]$TimeoutMs = 700
)

function Test-TcpPort {
    param(
        [string]$TargetHost,
        [int]$Port,
        [int]$TimeoutMs = 700
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

$adapters = Get-NetAdapter
$wiredPatterns = "Realtek|Ethernet|GbE|LAN"
$ethernetAdapter = $adapters | Where-Object {
    $_.InterfaceDescription -match $wiredPatterns -or $_.Name -match "Ethernet|LAN"
} | Select-Object -First 1

Write-Host "=== Adapter Status ==="
$adapters | Format-Table -Auto Name, InterfaceDescription, Status, LinkSpeed, MacAddress

if (-not $ethernetAdapter) {
    Write-Host ""
    Write-Host "No likely wired adapter was found."
    exit 2
}

$ethernet = Get-NetIPConfiguration | Where-Object { $_.InterfaceIndex -eq $ethernetAdapter.ifIndex }

Write-Host ""
Write-Host "=== Wired Adapter Details ==="
if ($ethernet) {
    $ethernet | Format-List InterfaceAlias, InterfaceDescription, IPv4Address, IPv4DefaultGateway, DNSServer
}

if ($ethernetAdapter.Status -ne "Up") {
    Write-Host ""
    Write-Host "Conclusion: the wired adapter has no physical link, so the PC cannot see the camera over Ethernet yet."
    Write-Host "Check these first:"
    Write-Host "1. The camera has a dedicated 12V 2A power supply connected."
    Write-Host "2. The network cable is inserted firmly on both sides."
    Write-Host "3. The camera LAN port LEDs are on or blinking."
    Write-Host "4. If the device needs PoE, a PoE switch or injector is being used."
    exit 3
}

Write-Host ""
Write-Host "=== Candidate IP Scan ==="
$results = @()
foreach ($ip in $CandidateIps | Select-Object -Unique) {
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
        }
    }
}

if ($results.Count -eq 0) {
    Write-Host "No open ports were found on the common candidate addresses."
    Write-Host "Suggestions:"
    Write-Host "1. Connect the camera to a router LAN port and run the vendor search tool again."
    Write-Host "2. Factory reset the camera and retry."
    Write-Host "3. Set a manual static IP on the PC and retry on the matching subnet."
    exit 4
}

$results | Format-Table -Auto IP, OpenPorts, RtspSub

Write-Host ""
Write-Host "=== Likely Endpoints ==="
$results | Select-Object IP, OpenPorts, RtspSub, RtspMain, Onvif | Format-List
