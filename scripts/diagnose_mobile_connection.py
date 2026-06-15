#!/usr/bin/env python3
"""
手机连接诊断工具
"""
import socket
import urllib.request
import urllib.error
import psutil


def get_local_ip():
    """获取本机局域网IP"""
    for interface, snics in psutil.net_if_addrs().items():
        if any(x in interface.lower() for x in ["vethernet", "loopback", "flclash", "wsl", "hyper-v"]):
            continue
        
        for snic in snics:
            if snic.family == socket.AF_INET:
                ip = snic.address
                if ip.startswith("169.254.") or ip.startswith("127."):
                    continue
                if ip.startswith("192.168.") or ip.startswith("10.") or ip.startswith("172."):
                    return ip
    return None


def check_port_listening(port=8000):
    """检查端口是否在监听"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            result = sock.connect_ex(("127.0.0.1", port))
            return result == 0
    except:
        return False


def check_backend_health(port=8000):
    """检查后端健康状态"""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=2) as response:
            if response.status == 200:
                data = response.read().decode('utf-8')
                return True, data
            return False, f"状态码: {response.status}"
    except urllib.error.URLError as e:
        return False, f"连接错误: {e.reason}"
    except Exception as e:
        return False, f"错误: {str(e)}"


def check_firewall_rule(port=8000):
    """检查防火墙规则（Windows）"""
    try:
        import subprocess
        result = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule", "name=all"],
            capture_output=True,
            text=True,
            timeout=5
        )
        output = result.stdout.lower()
        # 简单检查是否有包含8000端口的规则
        return str(port) in output
    except:
        return None


def main():
    print("="*70)
    print("手机连接诊断工具")
    print("="*70)
    
    # 1. 检查本机IP
    print("\n[1/5] 检查本机IP地址...")
    local_ip = get_local_ip()
    if local_ip:
        print(f"  ✓ 本机IP: {local_ip}")
        print(f"  → 手机应该连接到: http://{local_ip}:8000")
    else:
        print("  ✗ 未找到有效的局域网IP")
        print("  → 请确认电脑已连接到WiFi或有线网络")
    
    # 2. 检查端口监听
    print("\n[2/5] 检查端口8000是否在监听...")
    if check_port_listening():
        print("  ✓ 端口8000正在监听")
    else:
        print("  ✗ 端口8000未监听")
        print("  → 请启动后端服务: python run.py")
        return
    
    # 3. 检查后端健康
    print("\n[3/5] 检查后端健康状态...")
    healthy, message = check_backend_health()
    if healthy:
        print(f"  ✓ 后端正常运行")
        print(f"  响应: {message}")
    else:
        print(f"  ✗ 后端健康检查失败")
        print(f"  原因: {message}")
        return
    
    # 4. 检查防火墙
    print("\n[4/5] 检查防火墙配置...")
    has_rule = check_firewall_rule()
    if has_rule is None:
        print("  ⚠ 无法检查防火墙规则（需要管理员权限）")
    elif has_rule:
        print("  ✓ 找到端口8000的防火墙规则")
    else:
        print("  ⚠ 未找到端口8000的防火墙规则")
        print("  → 这可能导致手机无法连接")
    
    # 5. 提供手机测试URL
    print("\n[5/5] 手机测试步骤...")
    if local_ip:
        test_url = f"http://{local_ip}:8000/healthz"
        print(f"  1. 确保手机和电脑连接同一WiFi")
        print(f"  2. 在手机浏览器中访问:")
        print(f"     {test_url}")
        print(f"  3. 如果能看到 {{'status':'ok'}}，说明网络正常")
        print(f"  4. 在APP中配置服务器:")
        print(f"     主机: {local_ip}")
        print(f"     端口: 8000")
        print(f"     协议: http")
    
    # 总结
    print("\n" + "="*70)
    print("诊断总结")
    print("="*70)
    
    if local_ip and healthy:
        print("\n✓ 后端服务正常运行")
        print(f"✓ 服务器地址: http://{local_ip}:8000")
        
        if has_rule is False:
            print("\n⚠ 警告：未找到防火墙规则")
            print("\n建议操作：")
            print("1. 以管理员身份运行PowerShell")
            print("2. 执行以下命令添加防火墙规则：")
            print(f"   New-NetFirewallRule -DisplayName \"AIoT Health Backend\" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow")
            print("\n或者临时关闭防火墙测试：")
            print("1. 打开Windows安全中心")
            print("2. 防火墙和网络保护")
            print("3. 关闭当前网络的防火墙")
        else:
            print("\n✓ 配置正常，手机应该可以连接")
            print("\n如果手机仍无法连接，请检查：")
            print("1. 手机和电脑是否连接同一WiFi")
            print("2. 在手机浏览器测试上述URL")
            print("3. 检查APP中的服务器配置")
    else:
        print("\n✗ 发现问题，请按照上述提示解决")
    
    print("\n详细排查指南: docs/MOBILE_CONNECTION_TROUBLESHOOTING.md")
    print()


if __name__ == "__main__":
    main()
