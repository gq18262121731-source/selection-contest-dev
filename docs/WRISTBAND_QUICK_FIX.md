# 手环数据问题快速修复

## 问题：手环数据收不到或手机端显示不出来

### 快速诊断（1分钟）

运行诊断脚本：
```bash
python scripts/diagnose_wristband_data.py
```

### 快速修复（3分钟）

#### 步骤1：修改配置

编辑 `.env` 文件，修改以下3行：

```env
DATA_MODE=serial          # 改为 serial
SERIAL_ENABLED=true       # 改为 true  
USE_MOCK_DATA=false       # 改为 false
```

#### 步骤2：确认串口号

1. 打开设备管理器（Win + X → 设备管理器）
2. 展开"端口(COM和LPT)"
3. 找到USB串口设备，记下COM号（例如COM3）
4. 在`.env`中确认：
   ```env
   SERIAL_PORT=COM3  # 改为你的COM号
   ```

#### 步骤3：重启后端

```bash
# 停止当前后端（Ctrl+C）
python run.py
```

#### 步骤4：验证

查看后端日志，应该看到：
```
Serial collector connected on COM3
Sample ingested
```

### 如果还是不行

#### 检查1：USB接收器
- 重新插拔USB接收器
- 更换USB口（使用主板直连的USB口）

#### 检查2：手环状态
- 手环是否开机
- 手环是否佩戴在手腕上
- 手环与接收器距离不要太远（<5米）

#### 检查3：驱动
- 安装CH340或CP210x驱动
- 重启电脑

### 实时监控

运行监控脚本查看数据采集情况：
```bash
python scripts/monitor_wristband_data.py
```

应该看到：
```
✓ 手环名称 [53:57:08:XX:XX:XX]
  状态: ONLINE | 模式: SERIAL
  心率: 75 bpm | 体温: 36.5°C | 血氧: 98%
```

### 常见配置错误对照表

| 错误配置 | 正确配置 | 症状 |
|---------|---------|------|
| `DATA_MODE=mock` | `DATA_MODE=serial` | 显示模拟数据 |
| `SERIAL_ENABLED=false` | `SERIAL_ENABLED=true` | 不采集数据 |
| `USE_MOCK_DATA=true` | `USE_MOCK_DATA=false` | 使用假数据 |
| `SERIAL_PORT=COM5` | `SERIAL_PORT=COM3` | 串口错误 |
| `SERIAL_APPLY_MAC_FILTER=true` | `SERIAL_APPLY_MAC_FILTER=false` | 数据被过滤 |

### 完整配置示例

```env
# 数据采集配置
DATA_MODE=serial
USE_MOCK_DATA=false
SERIAL_ENABLED=true

# 串口配置
SERIAL_PORT=COM3
SERIAL_BAUDRATE=115200
SERIAL_AUTO_CONFIGURE=true

# 数据包配置
SERIAL_PACKET_MERGE_TIMEOUT_SECONDS=0.8
SERIAL_RESPONSE_CYCLE_SECONDS=1.0
SERIAL_BROADCAST_CYCLE_SECONDS=0.5

# MAC过滤（开发阶段建议禁用）
SERIAL_APPLY_MAC_FILTER=false
SERIAL_APPLY_PACKET_TYPE=false
```

### 手机端问题

如果后端收到数据但手机端不显示：

1. **检查网络**：手机和电脑在同一WiFi
2. **刷新APP**：下拉刷新或重启APP
3. **检查设备状态**：设备应该显示"在线"
4. **查看最后更新时间**：应该是最近几秒

### 需要帮助？

详细排查指南：`docs/WRISTBAND_DATA_TROUBLESHOOTING.md`
