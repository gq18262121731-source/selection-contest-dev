#!/usr/bin/env python3
"""
摄像头性能监控脚本
实时监控摄像头的性能指标，包括帧率、延迟、缓存命中率等
"""

import asyncio
import time
from datetime import datetime

import requests


async def monitor_camera_performance(interval: float = 2.0, duration: int = 60):
    """
    监控摄像头性能
    
    Args:
        interval: 监控间隔（秒）
        duration: 监控时长（秒），0表示持续监控
    """
    base_url = "http://localhost:8000"
    start_time = time.time()
    
    print("=" * 80)
    print("摄像头性能监控")
    print("=" * 80)
    print(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"监控间隔: {interval}秒")
    print(f"监控时长: {'持续' if duration == 0 else f'{duration}秒'}")
    print("=" * 80)
    print()
    
    iteration = 0
    try:
        while True:
            iteration += 1
            elapsed = time.time() - start_time
            
            # 检查是否超过监控时长
            if duration > 0 and elapsed > duration:
                break
            
            try:
                # 获取摄像头状态
                response = requests.get(f"{base_url}/api/v1/camera/stream/status", timeout=5)
                if response.status_code == 200:
                    status = response.json()
                    
                    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 监控迭代 #{iteration}")
                    print("-" * 80)
                    
                    # 基本信息
                    print(f"运行状态: {'运行中' if status.get('running') else '已停止'}")
                    print(f"客户端数: {status.get('clients', 0)} (WebSocket: {status.get('websocket_clients', 0)}, MJPEG: {status.get('mjpeg_clients', 0)})")
                    print(f"保持预热: {'是' if status.get('keep_warm') else '否'}")
                    
                    # 性能指标
                    print(f"\n性能指标:")
                    print(f"  目标帧率: {status.get('target_fps', 0)} FPS")
                    print(f"  实际帧率: {status.get('source_fps', 0)} FPS")
                    print(f"  广播帧率: {status.get('broadcast_fps', 0)} FPS")
                    print(f"  总帧数: {status.get('frames_total', 0)}")
                    print(f"  广播总数: {status.get('broadcast_total', 0)}")
                    
                    # 缓存性能
                    cache_hit_rate = status.get('cache_hit_rate', 0)
                    cache_hits = status.get('cache_hits', 0)
                    cache_misses = status.get('cache_misses', 0)
                    cache_size = status.get('cache_size', 0)
                    
                    print(f"\n缓存性能:")
                    print(f"  缓存命中率: {cache_hit_rate}%")
                    print(f"  缓存命中: {cache_hits}")
                    print(f"  缓存未命中: {cache_misses}")
                    print(f"  缓存大小: {cache_size}")
                    
                    # 帧信息
                    latest_frame_size = status.get('latest_frame_size', 0)
                    print(f"\n帧信息:")
                    print(f"  最新帧大小: {latest_frame_size / 1024:.2f} KB")
                    print(f"  活动URL: {status.get('active_url', 'N/A')}")
                    print(f"  配置文件: {status.get('profile', 'N/A')}")
                    print(f"  JPEG质量: {status.get('jpeg_quality', 0)}")
                    print(f"  流宽度: {status.get('stream_width', 0)}")
                    
                    # 错误信息
                    last_error = status.get('last_error')
                    if last_error:
                        print(f"\n最后错误: {last_error}")
                    
                    # 性能评估
                    print(f"\n性能评估:")
                    source_fps = status.get('source_fps', 0)
                    target_fps = status.get('target_fps', 0)
                    if source_fps >= target_fps * 0.9:
                        print(f"  ✅ 帧率正常 ({source_fps}/{target_fps} FPS)")
                    elif source_fps >= target_fps * 0.7:
                        print(f"  ⚠️  帧率偏低 ({source_fps}/{target_fps} FPS)")
                    else:
                        print(f"  ❌ 帧率过低 ({source_fps}/{target_fps} FPS)")
                    
                    if cache_hit_rate >= 50:
                        print(f"  ✅ 缓存效果好 ({cache_hit_rate}%)")
                    elif cache_hit_rate >= 30:
                        print(f"  ⚠️  缓存效果一般 ({cache_hit_rate}%)")
                    else:
                        print(f"  ℹ️  缓存效果待提升 ({cache_hit_rate}%)")
                    
                else:
                    print(f"❌ 获取状态失败: HTTP {response.status_code}")
                    
            except requests.exceptions.RequestException as e:
                print(f"❌ 请求失败: {e}")
            except Exception as e:
                print(f"❌ 错误: {e}")
            
            # 等待下一次监控
            await asyncio.sleep(interval)
            
    except KeyboardInterrupt:
        print("\n\n监控已停止")
    
    print("\n" + "=" * 80)
    print(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"总监控时长: {time.time() - start_time:.1f}秒")
    print("=" * 80)


async def test_camera_snapshot():
    """测试摄像头快照性能"""
    base_url = "http://localhost:8000"
    
    print("\n" + "=" * 80)
    print("摄像头快照性能测试")
    print("=" * 80)
    
    # 测试10次快照
    times = []
    for i in range(10):
        start = time.time()
        try:
            response = requests.get(f"{base_url}/api/v1/camera/snapshot", timeout=10)
            elapsed = time.time() - start
            times.append(elapsed)
            
            if response.status_code == 200:
                size = len(response.content)
                print(f"快照 #{i+1}: {elapsed*1000:.0f}ms, {size/1024:.1f}KB")
            else:
                print(f"快照 #{i+1}: 失败 (HTTP {response.status_code})")
        except Exception as e:
            print(f"快照 #{i+1}: 错误 - {e}")
        
        await asyncio.sleep(0.5)
    
    if times:
        avg_time = sum(times) / len(times)
        min_time = min(times)
        max_time = max(times)
        
        print("\n性能统计:")
        print(f"  平均延迟: {avg_time*1000:.0f}ms")
        print(f"  最小延迟: {min_time*1000:.0f}ms")
        print(f"  最大延迟: {max_time*1000:.0f}ms")
        print(f"  理论最大FPS: {1/avg_time:.1f}")
    
    print("=" * 80)


async def main():
    """主函数"""
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        # 测试模式
        await test_camera_snapshot()
    else:
        # 监控模式
        interval = 2.0
        duration = 0  # 持续监控
        
        if len(sys.argv) > 1:
            try:
                interval = float(sys.argv[1])
            except ValueError:
                print(f"无效的间隔时间: {sys.argv[1]}")
                return
        
        if len(sys.argv) > 2:
            try:
                duration = int(sys.argv[2])
            except ValueError:
                print(f"无效的监控时长: {sys.argv[2]}")
                return
        
        await monitor_camera_performance(interval, duration)


if __name__ == "__main__":
    asyncio.run(main())
