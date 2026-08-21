import os
import socket
import psutil

def get_best_local_ip():
    """
    Looks for a plausible non-loopback, non-VM IPv4 address
    assigned to physical/wi-fi adapters.
    """
    best_ip = None
    for interface, snics in psutil.net_if_addrs().items():
        # Skip common VPN / proxy / VM virtual interfaces
        if any(x in interface.lower() for x in ['vethernet', 'loopback', 'flclash', 'wsl', 'hyper-v']):
            continue

        for snic in snics:
            if snic.family == socket.AF_INET:
                ip = snic.address
                # Skip link-local and localhost
                if ip.startswith("169.254.") or ip.startswith("127."):
                    continue
                # If we found a classic home LAN prefix, prefer it immediately
                if ip.startswith("192.168.") or ip.startswith("10.") or ip.startswith("172."):
                    return ip
                # Fallback to the first valid one we find
                if best_ip is None:
                    best_ip = ip

    return best_ip or "127.0.0.1"

if __name__ == "__main__":
    local_ip = get_best_local_ip()
    print("\n" + "="*60)
    print("🚀 AIoT Health Monitoring System - Backend Launcher")
    print("="*60)
    print(f"\n📡 Mobile App should connect to Server IP:")
    print(f"👉   http://{local_ip}:8000   👈")
    print("\nPlease enter this IP in the mobile app's Server Settings (accessible via the Gear icon on the Login screen).")
    print("\n" + "="*60 + "\n")

    # Start Uvicorn listening on all interfaces with hot-reload enabled
    # We must bind to 0.0.0.0 to accept external requests
    os.system("python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload")
