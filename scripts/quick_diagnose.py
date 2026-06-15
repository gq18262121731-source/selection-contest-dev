#!/usr/bin/env python3
"""
手环数据采集快速诊断工具（独立版本）
"""
import os
from pathlib import Path


def read_env_file():
    """读取.env文件"""
    env_path = Path(__file__).parent.parent / '.env'
    config = {}
    
    if not env_path.exists():
        return None
    
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                config[key.strip()] = value.strip()
    
    return config


def check_serial_ports():
    """检查可用的串口"""
    try:
        from serial.tools import list_ports
        ports = list(list_ports.comports())
        return ports
    except ImportError:
        return None


def main():
    print("="*70)
    print("手环数据采集快速诊断")
    print("="*70)
    
    # 1. 读取配置
    print("\n[1/3] 检查配置文件...")
    config = read_env_file()
    
    if config is None:
        print("  ✗ 未找到.env文件")
        return
    
    # 关键配置项
    data_mode = config.get('DATA_MODE', 'mock')
    serial_enabled = config.get('SERIAL_ENABLED', 'false').lower()
    use_mock_data = config.get('USE_MOCK_DATA', 'true').lower()
    serial_port = config.get('SERIAL_PORT', '')
    serial_baudrate = config.get('SERIAL_BAUDRATE', '115200')
    
    issues = []
    
    # 检查配置
    if data_mode != 'serial':
        issues.append(f"DATA_MODE={data_mode}，应该是 'serial'")
    
    if serial_enabled != 'true':
        issues.append(f"SERIAL_ENABLED={serial_enabled}，应该是 'true'")
    
    if use_mock_data != 'false':
        issues.append(f"USE_MOCK_DATA={use_mock_data}，应该是 'false'")
    
    if not serial_port:
        issues.append("SERIAL_PORT 未配置")
    
    if issues:
        print("  ✗ 发现配置问题：")
        for issue in issues:
            print(f"    - {issue}")
    else:
        print("  ✓ 配置正确")
    
    print(f"\n  当前配置：")
    print(f"    DATA_MODE: {data_mode}")
    print(f"    SERIAL_ENABLED: {serial_enabled}")
    print(f"    USE_MOCK_DATA: {use_mock_data}")
    print(f"    SERIAL_PORT: {serial_port}")
    print(f"    SERIAL_BAUDRATE: {serial_baudrate}")
    
    # 2. 检查串口
    print("\n[2/3] 检查串口设备...")
    ports = check_serial_ports()
    
    if ports is None:
        print("  ⚠ pyserial 未安装")
        print("    安装命令: pip install pyserial")
    elif not ports:
        print("  ✗ 未找到任何串口设备")
        print("    请检查：")
        print("    1. USB接收器是否插入")
        print("    2. 驱动是否安装（CH340或CP210x）")
        print("    3. 在设备管理器中查看")
    else:
        print(f"  ✓ 找到 {len(ports)} 个串口：")
        for port in ports:
            marker = "  ← 配置的端口" if str(port.device).upper() == serial_port.upper() else ""
            print(f"    - {port.device}: {port.description}{marker}")
        
        # 检查配置的端口是否存在
        if serial_port:
            port_exists = any(
                str(port.device).upper() == serial_port.upper()
                for port in ports
            )
            if not port_exists:
                print(f"\n  ⚠ 警告：配置的端口 {serial_port} 不存在")
                print(f"    可用端口: {', '.join(str(p.device) for p in ports)}")
    
    # 3. 检查后端
    print("\n[3/3] 检查后端服务...")
    try:
        import urllib.request
        with urllib.request.urlopen("http://localhost:8000/healthz", timeout=2) as response:
            if response.status == 200:
                print("  ✓ 后端服务正常运行")
            else:
                print(f"  ✗ 后端响应异常: {response.status}")
    except Exception as e:
        print("  ✗ 无法连接到后端服务")
        print("    请启动后端: python run.py")
    
    # 总结
    print("\n" + "="*70)
    print("诊断总结")
    print("="*70)
    
    if issues:
        print("\n❌ 发现配置问题，需要修复：")
        print("\n请修改 .env 文件：")
        print("-" * 70)
        if any("DATA_MODE" in issue for issue in issues):
            print("DATA_MODE=serial")
        if any("SERIAL_ENABLED" in issue for issue in issues):
            print("SERIAL_ENABLED=true")
        if any("USE_MOCK_DATA" in issue for issue in issues):
            print("USE_MOCK_DATA=false")
        if any("SERIAL_PORT" in issue for issue in issues) and ports:
            print(f"SERIAL_PORT={ports[0].device}")
        print("-" * 70)
        
        print("\n修改后重启后端服务：")
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
            print("  3. 在设备管理器中查看端口(COM和LPT)")
        else:
            print("\n✓ 串口设备正常")
            print("\n如果仍然收不到数据，请：")
            print("  1. 确认手环已开机并佩戴")
            print("  2. 确认手环与接收器距离<5米")
            print("  3. 查看后端日志确认数据采集")
            print("  4. 运行监控: python scripts/monitor_wristband_data.py")
    
    print("\n详细指南:")
    print("  - 快速修复: docs/WRISTBAND_QUICK_FIX.md")
    print("  - 完整排查: docs/WRISTBAND_DATA_TROUBLESHOOTING.md")
    print()


if __name__ == "__main__":
    main()
