#!/usr/bin/env python3
"""
手环数据采集诊断工具
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import Settings


def check_serial_ports():
    """检查可用的串口"""
    try:
        from serial.tools import list_ports
        ports = list(list_ports.comports())
        return ports
    except ImportError:
        return None


def check_config():
    """检查配置"""
    settings = Settings()
    
    issues = []
    warnings = []
    
    # 检查数据模式
    if settings.data_mode != "serial":
        issues.append(f"DATA_MODE={settings.data_mode}，应该是 'serial'")
    
    # 检查串口启用
    if not settings.serial_enabled:
        issues.append("SERIAL_ENABLED=false，应该是 true")
    
    # 检查模拟数据
    if settings.use_mock_data:
        warnings.append("USE_MOCK_DATA=true，建议设为 false")
    
    # 检查串口配置
    if not settings.serial_port:
        issues.append("SERIAL_PORT 未配置")
    
    # 检查MAC过滤
    if settings.serial_apply_mac_filter:
        warnings.append(f"MAC过滤已启用: {settings.serial_mac_filter}")
    
    return issues, warnings, settings


def main():
    print("="*70)
    print("手环数据采集诊断工具")
    print("="*70)
    
    # 1. 检查配置
    print("\n[1/3] 检查配置...")
    issues, warnings, settings = check_config()
    
    if issues:
        print("  ✗ 发现配置问题：")
        for issue in issues:
            print(f"    - {issue}")
    else:
        print("  ✓ 配置正确")
    
    if warnings:
        print("  ⚠ 警告：")
        for warning in warnings:
            print(f"    - {warning}")
    
    print(f"\n  当前配置：")
    print(f"    DATA_MODE: {settings.data_mode}")
    print(f"    SERIAL_ENABLED: {settings.serial_enabled}")
    print(f"    SERIAL_PORT: {settings.serial_port}")
    print(f"    SERIAL_BAUDRATE: {settings.serial_baudrate}")
    print(f"    USE_MOCK_DATA: {settings.use_mock_data}")
    
    # 2. 检查串口
    print("\n[2/3] 检查串口...")
    ports = check_serial_ports()
    
    if ports is None:
        print("  ✗ pyserial 未安装")
        print("    安装: pip install pyserial")
    elif not ports:
        print("  ✗ 未找到任何串口设备")
        print("    请检查：")
        print("    1. USB接收器是否插入")
        print("    2. 驱动是否安装（CH340或CP210x）")
    else:
        print(f"  ✓ 找到 {len(ports)} 个串口：")
        for port in ports:
            marker = "  ← 配置的端口" if str(port.device).upper() == settings.serial_port.upper() else ""
            print(f"    - {port.device}: {port.description}{marker}")
        
        # 检查配置的端口是否存在
        if settings.serial_port:
            port_exists = any(
                str(port.device).upper() == settings.serial_port.upper()
                for port in ports
            )
            if not port_exists:
                print(f"\n  ⚠ 警告：配置的端口 {settings.serial_port} 不存在")
    
    # 3. 检查后端连接
    print("\n[3/3] 检查后端服务...")
    try:
        import requests
        response = requests.get("http://localhost:8000/healthz", timeout=2)
        if response.status_code == 200:
            print("  ✓ 后端服务正常运行")
            
            # 检查设备
            try:
                devices_response = requests.get("http://localhost:8000/api/v1/devices", timeout=2)
                if devices_response.status_code == 200:
                    devices = devices_response.json()
                    print(f"  ✓ 找到 {len(devices)} 个设备")
                    
                    for device in devices[:5]:  # 只显示前5个
                        mac = device.get('mac_address', 'N/A')
                        status = device.get('status', 'N/A')
                        mode = device.get('ingest_mode', 'N/A')
                        print(f"    - {mac}: {status} ({mode})")
            except:
                pass
        else:
            print(f"  ✗ 后端响应异常: {response.status_code}")
    except requests.exceptions.ConnectionError:
        print("  ✗ 无法连接到后端服务")
        print("    请启动后端: python run.py")
    except Exception as e:
        print(f"  ✗ 检查失败: {e}")
    
    # 总结
    print("\n" + "="*70)
    print("诊断总结")
    print("="*70)
    
    if issues:
        print("\n❌ 发现问题，需要修复：")
        print("\n修改 .env 文件：")
        if "DATA_MODE" in str(issues):
            print("  DATA_MODE=serial")
        if "SERIAL_ENABLED" in str(issues):
            print("  SERIAL_ENABLED=true")
        if "USE_MOCK_DATA" in str(warnings):
            print("  USE_MOCK_DATA=false")
        if "SERIAL_PORT" in str(issues) and ports:
            print(f"  SERIAL_PORT={ports[0].device}")
        
        print("\n然后重启后端服务：")
        print("  python run.py")
    else:
        print("\n✓ 配置正确")
        
        if ports is None:
            print("\n⚠ 需要安装 pyserial：")
            print("  pip install pyserial")
        elif not ports:
            print("\n⚠ 未找到串口设备，请检查：")
            print("  1. USB接收器是否插入")
            print("  2. 驱动是否安装")
            print("  3. 在设备管理器中查看端口")
        else:
            print("\n✓ 串口设备正常")
            print("\n如果仍然收不到数据，请检查：")
            print("  1. 手环是否开机并佩戴")
            print("  2. 手环与接收器距离是否太远")
            print("  3. 查看后端日志: logs/backend-live.out.log")
    
    print("\n详细排查指南: docs/WRISTBAND_DATA_TROUBLESHOOTING.md")
    print()


if __name__ == "__main__":
    main()
