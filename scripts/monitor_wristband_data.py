#!/usr/bin/env python3
"""
手环数据实时监控工具
"""
import requests
import time
from datetime import datetime


API_BASE = "http://localhost:8000/api/v1"


def get_devices():
    """获取所有设备"""
    try:
        response = requests.get(f"{API_BASE}/devices", timeout=2)
        if response.status_code == 200:
            return response.json()
        return []
    except:
        return []


def get_realtime_data(mac):
    """获取实时数据"""
    try:
        response = requests.get(f"{API_BASE}/health/realtime/{mac}", timeout=2)
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None


def format_value(value, unit=""):
    """格式化数值"""
    if value is None:
        return "N/A"
    return f"{value}{unit}"


def main():
    print("="*80)
    print("手环数据实时监控")
    print("="*80)
    print("按 Ctrl+C 停止监控\n")
    
    last_data = {}
    no_data_count = {}
    
    try:
        while True:
            devices = get_devices()
            
            if not devices:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠ 未找到设备或后端未运行")
                time.sleep(5)
                continue
            
            print(f"\n{'='*80}")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 监控 {len(devices)} 个设备")
            print(f"{'='*80}")
            
            for device in devices:
                mac = device.get('mac_address', 'N/A')
                status = device.get('status', 'N/A')
                mode = device.get('ingest_mode', 'N/A')
                name = device.get('name', mac)
                
                # 获取实时数据
                data = get_realtime_data(mac)
                
                if data:
                    # 提取数据
                    hr = data.get('heart_rate')
                    temp = data.get('temperature')
                    spo2 = data.get('blood_oxygen')
                    bp = data.get('blood_pressure')
                    steps = data.get('steps')
                    timestamp = data.get('timestamp', '')
                    
                    # 检查数据是否更新
                    data_key = f"{hr}_{temp}_{spo2}"
                    is_new = last_data.get(mac) != data_key
                    last_data[mac] = data_key
                    no_data_count[mac] = 0
                    
                    # 显示数据
                    status_icon = "✓" if is_new else "→"
                    print(f"\n{status_icon} {name} [{mac}]")
                    print(f"  状态: {status} | 模式: {mode}")
                    print(f"  心率: {format_value(hr, ' bpm')} | "
                          f"体温: {format_value(temp, '°C')} | "
                          f"血氧: {format_value(spo2, '%')}")
                    if bp:
                        print(f"  血压: {bp}")
                    if steps is not None:
                        print(f"  步数: {steps}")
                    if timestamp:
                        print(f"  时间: {timestamp[:19]}")
                    
                    if not is_new:
                        print(f"  ⚠ 数据未更新")
                else:
                    # 无数据
                    no_data_count[mac] = no_data_count.get(mac, 0) + 1
                    count = no_data_count[mac]
                    
                    print(f"\n✗ {name} [{mac}]")
                    print(f"  状态: {status} | 模式: {mode}")
                    print(f"  ⚠ 无数据 (已持续 {count * 5} 秒)")
                    
                    if count >= 6:  # 30秒无数据
                        print(f"  ⚠ 警告：超过30秒未收到数据")
                        print(f"  建议检查：")
                        print(f"    1. 手环是否开机")
                        print(f"    2. 手环是否佩戴")
                        print(f"    3. 串口连接是否正常")
            
            print(f"\n{'='*80}")
            print("等待5秒后刷新...")
            time.sleep(5)
            
    except KeyboardInterrupt:
        print("\n\n监控已停止")
    except Exception as e:
        print(f"\n错误: {e}")


if __name__ == "__main__":
    main()
