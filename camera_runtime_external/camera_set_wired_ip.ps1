param(
    [ValidateSet("dhcp", "192.168.1.10", "192.168.8.10", "169.254.62.10")]
    [string]$Mode = "dhcp",
    [string]$PrefixLength = "24"
)

$adapters = Get-NetAdapter
$wiredPatterns = "Realtek|Ethernet|GbE|LAN"
$ethernetAdapter = $adapters | Where-Object {
    $_.InterfaceDescription -match $wiredPatterns -or $_.Name -match "Ethernet|LAN"
} | Select-Object -First 1

if (-not $ethernetAdapter) {
    Write-Host "No likely wired adapter was found."
    exit 2
}

$alias = $ethernetAdapter.Name
Write-Host "Using wired adapter:" $alias

if ($Mode -eq "dhcp") {
    Get-NetIPAddress -InterfaceAlias $alias -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue
    Set-NetIPInterface -InterfaceAlias $alias -Dhcp Enabled
    Set-DnsClientServerAddress -InterfaceAlias $alias -ResetServerAddresses
    Write-Host "Switched to DHCP."
    exit 0
}

$existing = Get-NetIPAddress -InterfaceAlias $alias -AddressFamily IPv4 -ErrorAction SilentlyContinue
if ($existing) {
    $existing | Remove-NetIPAddress -Confirm:$false -ErrorAction SilentlyContinue
}

New-NetIPAddress -InterfaceAlias $alias -IPAddress $Mode -PrefixLength $PrefixLength | Out-Null
Set-DnsClientServerAddress -InterfaceAlias $alias -ServerAddresses @()
Write-Host "Set static IP to" $Mode

