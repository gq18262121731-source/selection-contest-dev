# 手环数据采集问题排查指南

## 问题症状

1. **后端有时收不到手环数据**
2. **手机端健康数据有时显示不出来**

## 问题分析

根据代码分析，可能的原因包括：

### 1. 串口连接问题（最常见）

#### 症状
- 后端日志显示串口连接失败
- 数据采集间歇性中断
- 重启后端才能恢复

#### 可能原因
- USB串口线松动或接触不良
- 串口被其他程序占用
- 串口驱动问题
- 串口配置错误

### 2. 数据采集配置问题

#### 症状
- 后端运行但不采集数据
- 使用模拟数据而不是真实数据

#### 可能原因
- `.env`配置错误
- `SERIAL_ENABLED=false`（未启用串口）
- `DATA_MODE=mock`（使用模拟数据）

### 3. WebSocket连接问题

#### 症状
- 后端收到数据但手机端不显示
- 手机端显示"连接中"或"离线"

#### 可能原因
- WebSocket连接断开
- 网络不稳定
- 手机APP后台被杀死

### 4. MAC地址过滤问题

#### 症状
- 串口有数据但被过滤掉
- 只能收到特定手环的数据

#### 可能原因
- MAC地址配置错误
- MAC地址过滤规则太严格

### 5. 数据包合并超时

#### 症状
- 数据不完整
- 部分指标缺失

#### 可能原因
- `SERIAL_PACKET_MERGE_TIMEOUT_SECONDS`设置太短
- 数据包分片传输

## 诊断步骤

### 步骤1：检查当前配置

查看`.env`文件：
```bash
# 关键配置项
DATA_MODE=mock          # ❌ 应该是 serial
USE_MOCK_DATA=true      # ❌ 应该是 false
SERIAL_ENABLED=false    # ❌ 应该是 true
SERIAL_PORT=COM3        # ✓ 确认是正确的COM口
```

### 步骤2：检查串口连接

#### Windows查看串口
```bash
# 方法1：设备管理器
Win + X → 设备管理器 → 端口(COM和LPT)

# 方法2：PowerShell
Get-WmiObject Win32_SerialPort | Select-Object Name, DeviceID
```

#### 确认串口号
- 查看手环接收器插入的COM口
- 例如：USB-SERIAL CH340 (COM3)

### 步骤3：测试串口通信

运行诊断脚本（需要创建）：
```bash
python scripts/test_serial_connection.py
```

### 步骤4：检查后端日志

查看后端日志中的关键信息：
```bash
# 查看最新日志
tail -f logs/backend-live.out.log

# 或在Windows中
Get-Content logs/backend-live.out.log -Tail 50 -Wait
```

**关键日志信息**：
- ✓ `Serial collector connected on COM3` - 串口连接成功
- ✗ `Serial collector unavailable` - 串口连接失败
- ✓ `Sample ingested` - 数据采集成功
- ⚠ `Dropping serial payload for off-target MAC` - MAC地址被过滤

### 步骤5：检查手机端连接

在手机APP中：
1. 查看设备状态（在线/离线）
2. 查看最后更新时间
3. 尝试下拉刷新

## 解决方案

### 方案1：启用串口数据采集（必须）

修改`.env`文件：
```env
# 修改这些配置
DATA_MODE=serial
USE_MOCK_DATA=false
SERIAL_ENABLED=true
SERIAL_PORT=COM3  # 改为你的实际COM口

# 其他重要配置
SERIAL_BAUDRATE=115200
SERIAL_AUTO_CONFIGURE=true
SERIAL_PACKET_MERGE_TIMEOUT_SECONDS=0.5
```

**重启后端服务**：
```bash
# 停止当前服务（Ctrl+C）
python run.py
```

### 方案2：优化串口配置

#### 2.1 增加数据包合并超时
```env
# 如果数据不完整，增加超时时间
SERIAL_PACKET_MERGE_TIMEOUT_SECONDS=1.0  # 从0.5增加到1.0
```

#### 2.2 调整采集周期
```env
# 如果数据采集太频繁导致丢失
SERIAL_RESPONSE_CYCLE_SECONDS=1.5  # 从1.0增加到1.5
SERIAL_BROADCAST_CYCLE_SECONDS=0.8  # 从0.5增加到0.8
```

#### 2.3 禁用MAC地址过滤（测试用）
```env
# 临时禁用过滤，接收所有手环数据
SERIAL_APPLY_MAC_FILTER=false
SERIAL_APPLY_PACKET_TYPE=false
```

### 方案3：修复串口连接问题

#### 3.1 检查USB连接
- 重新插拔USB接收器
- 更换USB口（使用主板直连的USB口）
- 检查USB线是否损坏

#### 3.2 更新串口驱动
1. 打开设备管理器
2. 找到串口设备（通常是CH340或CP210x）
3. 右键 → 更新驱动程序

#### 3.3 释放被占用的串口
```powershell
# 查找占用串口的进程
Get-Process | Where-Object {$_.Modules.ModuleName -like "*serial*"}

# 或者重启电脑释放所有串口
```

### 方案4：优化WebSocket连接

#### 4.1 增加心跳间隔
修改`backend/config.py`或`.env`：
```env
WS_HEARTBEAT_SECONDS=30  # 默认30秒，可以减少到15秒
```

#### 4.2 手机端保持连接
- 在手机设置中允许APP后台运行
- 关闭省电模式
- 保持APP在前台

### 方案5：配置MAC地址（单手环模式）

如果只使用一个手环，配置其MAC地址：
```env
# 配置手环MAC地址
SERIAL_MAC_FILTER=535708000000  # 改为你的手环MAC
SERIAL_APPLY_MAC_FILTER=true

# 或者使用fallback MAC
SERIAL_FALLBACK_DEVICE_MAC=53:57:08:00:00:00
```

**如何获取手环MAC地址**：
1. 临时禁用MAC过滤
2. 查看后端日志
3. 找到类似 `53:57:08:XX:XX:XX` 的MAC地址

### 方案6：使用双串口模式（高级）

如果有多个手环或需要更稳定的采集：
```env
SERIAL_DUAL_COLLECTOR_ENABLED=true
SERIAL_BROADCAST_PORT=COM4  # 广播端口
SERIAL_RESPONSE_PORT=COM3   # 响应端口
```

## 监控和调试

### 实时监控数据采集

创建监控脚本`scripts/monitor_data_collection.py`：
```python
import requests
import time

API_BASE = "http://localhost:8000/api/v1"

while True:
    try:
        # 获取所有设备
        devices = requests.get(f"{API_BASE}/devices").json()
        
        for device in devices:
            mac = device['mac_address']
            status = device['status']
            
            # 获取实时数据
            response = requests.get(f"{API_BASE}/health/realtime/{mac}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"✓ {mac} [{status}]: HR={data.get('heart_rate')}, "
                      f"Temp={data.get('temperature')}, "
                      f"SpO2={data.get('blood_oxygen')}")
            elif response.status_code == 204:
                print(f"⚠ {mac} [{status}]: 无数据")
            else:
                print(f"✗ {mac} [{status}]: 错误 {response.status_code}")
        
        print("-" * 60)
        time.sleep(5)
    except Exception as e:
        print(f"错误: {e}")
        time.sleep(5)
```

运行监控：
```bash
python scripts/monitor_data_collection.py
```

### 查看详细日志

启用调试日志：
```env
# 在.env中添加
LOG_LEVEL=DEBUG
```

或在代码中临时启用：
```python
# backend/main.py
import logging
logging.basicConfig(level=logging.DEBUG)
```

## 常见错误和解决方法

### 错误1：`Serial collector unavailable on COM3`

**原因**：串口不存在或被占用

**解决**：
1. 检查COM口号是否正确
2. 检查USB接收器是否插好
3. 重启电脑释放串口

### 错误2：`No compatible collector serial port was detected`

**原因**：未找到串口设备

**解决**：
1. 安装串口驱动（CH340或CP210x）
2. 检查USB接收器是否正常
3. 尝试更换USB口

### 错误3：`Dropping serial payload for off-target MAC`

**原因**：MAC地址不匹配

**解决**：
1. 禁用MAC过滤：`SERIAL_APPLY_MAC_FILTER=false`
2. 或配置正确的MAC地址

### 错误4：手机端显示"设备离线"

**原因**：
- 后端未收到数据超过一定时间
- WebSocket连接断开

**解决**：
1. 检查后端是否正常采集数据
2. 检查手机网络连接
3. 重启APP重新连接

### 错误5：数据不完整（缺少某些指标）

**原因**：数据包合并超时太短

**解决**：
```env
SERIAL_PACKET_MERGE_TIMEOUT_SECONDS=1.0  # 增加超时
```

## 最佳实践

### 1. 稳定的串口连接
- 使用主板直连的USB口（不要用USB Hub）
- 使用质量好的USB线
- 固定USB口，不要频繁更换

### 2. 合理的配置
```env
# 推荐配置
DATA_MODE=serial
SERIAL_ENABLED=true
SERIAL_AUTO_CONFIGURE=true
SERIAL_PACKET_MERGE_TIMEOUT_SECONDS=0.8
SERIAL_RESPONSE_CYCLE_SECONDS=1.0
SERIAL_APPLY_MAC_FILTER=false  # 开发阶段禁用
```

### 3. 监控和告警
- 定期检查后端日志
- 监控数据采集频率
- 设置数据缺失告警

### 4. 手机端优化
- 保持APP在前台
- 关闭省电模式
- 使用稳定的WiFi连接

## 快速诊断清单

- [ ] `.env`中`SERIAL_ENABLED=true`
- [ ] `.env`中`DATA_MODE=serial`
- [ ] 串口号配置正确（COM3等）
- [ ] USB接收器已插入
- [ ] 设备管理器中能看到串口
- [ ] 后端日志显示串口连接成功
- [ ] 后端日志显示数据采集成功
- [ ] 手机和电脑在同一WiFi
- [ ] 手机APP显示设备在线
- [ ] 手机APP能看到实时数据

## 总结

**最常见的3个问题**：
1. 🔧 **配置错误**（60%）- 未启用串口或使用模拟数据
2. 🔌 **串口连接**（30%）- USB松动或驱动问题
3. 📡 **网络问题**（10%）- WebSocket断开或手机网络不稳定

**解决顺序**：
1. 先检查配置（`.env`文件）
2. 再检查串口连接（设备管理器）
3. 最后检查网络（手机WiFi）

**快速修复**：
```bash
# 1. 修改.env
DATA_MODE=serial
SERIAL_ENABLED=true
SERIAL_APPLY_MAC_FILTER=false

# 2. 重启后端
python run.py

# 3. 查看日志确认
tail -f logs/backend-live.out.log
```
