#!/usr/bin/env python3
"""
串口目标诊断工具 - 检查为什么收不到数据包
"""
import requests
import json


API_BASE = "http://localhost:8000"


def check_system_info():
    """检查系统信息"""
    try:
        response = requests.get(f"{API_BASE}/system/info", timeout=2)
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None


def check_devices():
    """检查设备列表"""
    try:
        response = requests.get(f"{API_BASE}/api/v1/devices", timeout=2)
        if response.status_code == 200:
            return response.json()
        return []
    except:
        return []


def check_realtime_data(mac):
    """检查实时数据"""
    try:
        response = requests.get(f"{API_BASE}/api/v1/health/realtime/{mac}", timeout=2)
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None


def main():
    print("="*70)
    print("串口数据采集诊断")
    print("="*70)
    
    # 1. 检查后端状态
    print("\n[1/4] 检查后端服务...")
    system_info = check_system_info()
    
    if not system_info:
        print("  ✗ 后端服务未运行")
        print("    请启动后端: python run.py")
        return 1
    
    print("  ✓ 后端服务正常")
    
    # 显示关键配置
    data_mode = system_info.get('data_mode', 'N/A')
    serial_enabled = system_info.get('serial_enabled', False)
    active_target_mac = system_info.get('active_serial_target_mac')
    active_target_name = system_info.get('active_serial_target_name')
    
    print(f"\n  系统配置：")
    print(f"    数据模式: {data_mode}")
    print(f"    串口启用: {serial_enabled}")
    print(f"    当前目标MAC: {active_target_mac or '未设置'}")
    print(f"    当前目标名称: {active_target_name or '未设置'}")
    
    # 检查配置问题
    issues = []
    if data_mode != 'serial':
        issues.append(f"数据模式是 '{data_mode}'，应该是 'serial'")
    if not serial_enabled:
        issues.append("串口未启用")
    if not active_target_mac:
        issues.append("未设置串口采集目标（这是主要问题！）")
    
    if issues:
        print(f"\n  ⚠ 发现问题：")
        for issue in issues:
            print(f"    - {issue}")
    
    # 2. 检查设备列表
    print("\n[2/4] 检查设备列表...")
    devices = check_devices()
    
    if not devices:
        print("  ⚠ 未找到任何设备")
        return 0
    
    print(f"  ✓ 找到 {len(devices)} 个设备")
    
    # 找出串口设备
    serial_devices = [
        d for d in devices 
        if d.get('ingest_mode') == 'SERIAL'
    ]
    
    bound_serial_devices = [
        d for d in serial_devices
        if d.get('bind_status') == 'BOUND'
    ]
    
    print(f"\n  串口设备: {len(serial_devices)} 个")
    print(f"  已绑定串口设备: {len(bound_serial_devices)} 个")
    
    if not serial_devices:
        print("\n  ⚠ 没有串口设备")
        return 0
    
    # 显示设备详情
    print(f"\n  设备详情：")
    for device in serial_devices:
        mac = device.get('mac_address', 'N/A')
        name = device.get('device_name', 'N/A')
        status = device.get('status', 'N/A')
        bind_status = device.get('bind_status', 'N/A')
        user_id = device.get('user_id')
        
        is_target = mac == active_target_mac
        marker = " ← 当前目标" if is_target else ""
        
        print(f"\n    {name} [{mac}]{marker}")
        print(f"      状态: {status}")
        print(f"      绑定: {bind_status}")
        print(f"      用户: {user_id or '未绑定'}")
        
        # 检查实时数据
        data = check_realtime_data(mac)
        if data:
            print(f"      ✓ 有数据: HR={data.get('heart_rate')}, Temp={data.get('temperature')}")
        else:
            print(f"      ✗ 无数据")
    
    # 3. 诊断问题
    print("\n[3/4] 问题诊断...")
    
    if not active_target_mac:
        print("  ✗ 主要问题：未设置串口采集目标")
        print("\n  原因分析：")
        print("    系统使用单目标串口采集模式")
        print("    需要明确指定采集哪个手环的数据")
        print("    绑定设备后应该自动设置，但可能失败了")
        
        if bound_serial_devices:
            print(f"\n  建议：手动设置采集目标")
            print(f"    设备: {bound_serial_devices[0].get('device_name')}")
            print(f"    MAC: {bound_serial_devices[0].get('mac_address')}")
    elif active_target_mac not in [d.get('mac_address') for d in bound_serial_devices]:
        print(f"  ⚠ 当前目标 {active_target_mac} 未绑定或不存在")
    else:
        print("  ✓ 串口目标配置正确")
        print("\n  如果仍然收不到数据，可能是：")
        print("    1. 手环未开机或未佩戴")
        print("    2. 手环与接收器距离太远")
        print("    3. USB接收器连接问题")
        print("    4. 串口通信问题")
    
    # 4. 解决方案
    print("\n[4/4] 解决方案...")
    
    if not active_target_mac and bound_serial_devices:
        target_device = bound_serial_devices[0]
        target_mac = target_device.get('mac_address')
        target_name = target_device.get('device_name')
        
        print(f"\n  需要设置串口采集目标：")
        print(f"\n  方法1：通过API设置（推荐）")
        print(f"    curl -X POST {API_BASE}/api/v1/devices/serial/switch \\")
        print(f"      -H 'Content-Type: application/json' \\")
        print(f"      -d '{{'\"mac_address\"': '\"{target_mac}\"'}}'")
        
        print(f"\n  方法2：在手机APP中")
        print(f"    1. 进入设备详情页")
        print(f"    2. 点击\"设为当前采集目标\"或类似按钮")
        
        print(f"\n  方法3：重新绑定设备")
        print(f"    1. 解绑设备")
        print(f"    2. 重新绑定")
        print(f"    3. 绑定时会自动设置为目标")
    
    elif not serial_enabled or data_mode != 'serial':
        print("\n  需要修改.env配置：")
        print("    DATA_MODE=serial")
        print("    SERIAL_ENABLED=true")
        print("\n  然后重启后端: python run.py")
    
    else:
        print("\n  配置正确，检查硬件：")
        print("    1. 确认手环已开机并佩戴")
        print("    2. 确认手环与接收器距离<5米")
        print("    3. 检查USB接收器连接")
        print("    4. 查看后端日志确认串口通信")
    
    print()
    return 0


if __name__ == "__main__":
    import sys
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n操作已取消")
        sys.exit(1)
