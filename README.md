# 智慧康养健康监测与预警系统

本项目是一个面向智慧康养场景的 AIoT 健康监测后端，当前重点支持老人手环的静态健康评分、异常预警、结构化解释和后续 Agent 接入。

当前第一版遵循“静态模型 + 规则引擎”的真实数据形态：

- 输入生命体征：心率、血氧、收缩压/舒张压、体温
- 输出能力：健康评分、风险等级、多级预警、异常标签、结构化解释
- 模型方案：轻量级 PyTorch 多任务 MLP
- 升级预留：TCN 时序模型骨架、LangChain 工具、LangGraph 工作流

## 环境规则

本项目必须统一使用 `helth` conda 环境，不要混用裸 `python` 和裸 `pytest`。

标准命令：

```powershell
conda run -n helth python ...
conda run -n helth pytest ...
```

## 项目结构

核心后端相关目录如下：

- `backend/api/`: FastAPI 路由
- `backend/schemas/`: 健康评分、预警、解释的 Pydantic Schema
- `backend/services/`: 健康评分服务、预警服务、解释服务、Agent 工具服务
- `backend/ml/`: 预处理、特征工程、规则引擎、训练、推理
- `backend/models/`: PyTorch 模型定义，包括静态 MLP 和未来 TCN
- `backend/repositories/`: 可切换的持久化仓储接口
- `scripts/train_static_model.py`: 静态模型训练脚本
- `scripts/run_server.py`: Python 启动入口
- `tests/`: 规则、推理、API 基础测试

## 环境安装

建议使用 Python 3.11：

```powershell
conda create -n helth python=3.11 -y
Copy-Item .env.example .env
conda run -n helth python -m pip install -r requirements.txt
```

初始化 `.env` 后，请至少补齐下面两项 Qwen 配置，智能体默认会直接使用它们：

```env
LLM_PROVIDER=qwen
QWEN_API_KEY=your-dashscope-api-key
QWEN_MODEL=qwen-plus
```

### GPU 推荐环境（本机演示建议）

如果你的现场演示机器带 NVIDIA GPU，推荐把 `helth` 环境切到 PyTorch `2.2.2 + cu121`。仓库里的 `requirements.txt` 仍保持通用写法，便于 CPU/GPU 两种环境共存；本机演示环境建议额外执行：

```powershell
conda run -n helth python -m pip uninstall -y torch torchvision torchaudio
conda run -n helth python -m pip install --index-url https://download.pytorch.org/whl/cu121 torch==2.2.2 torchvision==0.17.2 torchaudio==2.2.2
```

安装完成后建议验证：

```powershell
conda run -n helth python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu')"
```

当前训练与推理代码已经支持 `MODEL_DEVICE=auto/cpu/cuda`：
- `auto`：优先使用 CUDA，可用时自动走 GPU
- `cpu`：强制只用 CPU
- `cuda`：强制使用 GPU，不可用时直接报错

如果你第一次运行本项目，还需要先准备 Redis：

```powershell
cd docker
docker compose up -d redis
cd ..
```

## Excel 数据放置

训练数据默认读取：

```text
data/raw/patients_data_with_alerts.xlsx
```

你也可以直接使用外部 Excel 路径，例如你当前的数据文件：

```text
D:/code/health/data/raw/patients_data_with_alerts.xlsx
```

如果不想复制文件，可以在 `.env` 中配置：

```env
STATIC_HEALTH_DATA_PATH=D:/code/health/data/raw/patients_data_with_alerts.xlsx
STATIC_HEALTH_SHEET_NAME=
```

## 数据处理与模型设计

### 1. 预处理

`backend/ml/preprocess.py` 会完成：

- Excel 字段映射到标准字段名
- 类型转换
- 合法范围校验
- 缺失值处理
- 标签兼容编码
- 丢弃样本日志统计

标准字段包括：

- `patient_id`
- `heart_rate`
- `spo2`
- `sbp`
- `dbp`
- `body_temp`
- `fall_detection`
- `predicted_disease`
- `data_accuracy`
- `hr_alert`
- `spo2_alert`
- `bp_alert`
- `temp_alert`

### 2. 特征工程

`backend/ml/feature_engineering.py` 统一生成训练和推理共用特征：

- 基础特征：`heart_rate / spo2 / sbp / dbp / body_temp / fall_detection / data_accuracy`
- 派生特征：`pulse_pressure / map_pressure / hr_spo2_ratio / temp_hr_interaction / bp_level_score / low_spo2_flag / high_hr_flag / fever_flag / hypertension_flag / fall_flag / quality_weight`

### 3. 静态模型

`backend/models/static_health_model.py` 使用轻量级 MLP 多头结构：

- Backbone: `Linear -> ReLU -> Dropout -> Linear -> ReLU`
- Heads:
  - `hr_alert_head`
  - `spo2_alert_head`
  - `bp_alert_head`
  - `temp_alert_head`
  - `risk_score_head`

### 4. 规则引擎

`backend/ml/rule_engine.py` 实现：

- 心率评分
- 血氧评分
- 血压评分
- 体温评分
- 综合规则分
- 风险等级判定
- 硬阈值升级
- 异常标签输出
- 推荐动作编码

## 训练命令

使用默认配置训练：

```powershell
conda run -n helth python .\scripts\train_static_model.py
```

指定 Excel 路径训练：

```powershell
conda run -n helth python .\scripts\train_static_model.py --data "data/raw/patients_data_with_alerts.xlsx"
```

训练完成后会生成：

- `data/artifacts/static_health/static_health_model.pt`
- `data/artifacts/static_health/feature_scaler.joblib`
- `data/artifacts/static_health/feature_columns.json`
- `data/artifacts/static_health/label_mapping.json`
- `data/artifacts/static_health/training_config.json`
- `data/artifacts/static_health/metrics.json`
- `data/processed/static_health_training_cleaned.csv`

## 启动服务

推荐使用项目脚本：

```powershell
conda run -n helth powershell -ExecutionPolicy Bypass -File .\scripts\start_server.ps1
```

当前脚本默认监听 `0.0.0.0:8000`，便于同一局域网内的手机或平板直接访问。

或使用 Python 启动入口：

```powershell
conda run -n helth python .\scripts\run_server.py
```

如果还要启动前端：

```powershell
conda run -n helth powershell -ExecutionPolicy Bypass -File .\scripts\start_frontend.ps1
```

服务健康检查：

```powershell
curl http://127.0.0.1:8000/healthz
```

如果当前要做“独立视觉服务接入主系统”的联调，请优先阅读：

- [主系统视频桥接对接说明](docs/main-system-video-bridge-integration.md)

### 局域网真机接入

如果后续要让 Android 真机在同一局域网访问后端，按下面步骤即可：

1. 在服务端电脑上执行 `ipconfig`，记下当前 Wi-Fi / 以太网网卡的局域网 IP。
2. 使用默认脚本启动后端，确认它监听的是 `0.0.0.0:8000`。
3. 在 Windows 防火墙中放行 `8000` 端口。
4. 让手机和服务端电脑连接到同一个路由器或 Wi-Fi。
5. 在家庭端 App 的“服务器设置”里填入 `http://<服务器IP>:8000`，再执行一次“测试连接”。

## 核心接口

### 1. 实时健康评分

接口：

```text
POST /api/v1/health/score
```

请求示例：

```json
{
  "elderly_id": "E10001",
  "device_id": "BAND_001",
  "timestamp": "2026-03-23T21:30:00+08:00",
  "heart_rate": 118,
  "spo2": 91,
  "sbp": 148,
  "dbp": 95,
  "body_temp": 37.6,
  "fall_detection": false,
  "data_accuracy": 94
}
```

当前线上评分链路已经加入“稳定化 + 去抖 + 事件聚合”：
- `stabilized_vitals`：最近窗口稳定值，默认 45 秒 / 最近 5 点
- `active_events`：已确认的持续异常事件，而不是单个抖动点
- `score_adjustment_reason`：说明本次评分是否触发了缓降或紧急直通

因此，现场高频采样时不会因为 `89/90` 血氧、`100/101` 心率、`37.2/37.3` 体温这类边界抖动就立刻重复告警或大幅掉分；但对严重低血氧、极端心率、高热、跌倒等情况仍会立即升级。

响应示例：

```json
{
  "code": "OK",
  "message": "success",
  "data": {
    "elderly_id": "E10001",
    "device_id": "BAND_001",
    "timestamp": "2026-03-23T13:30:00Z",
    "health_score": 63.2,
    "final_health_score": 63.2,
    "rule_health_score": 71.0,
    "model_health_score": 51.5,
    "risk_level": "warning",
    "risk_score_raw": 0.485,
    "sub_scores": {
      "score_hr": 60.0,
      "score_spo2": 65.0,
      "score_bp": 50.0,
      "score_temp": 60.0
    },
    "alerts": {
      "hr_alert": {"label": "High", "probability": 0.72},
      "spo2_alert": {"label": "Low", "probability": 0.61},
      "bp_alert": {"label": "High", "probability": 0.66},
      "temp_alert": {"label": "Abnormal", "probability": 0.58},
      "hard_threshold_level": "warning"
    },
    "abnormal_tags": ["tachycardia", "hypertension", "fever"],
    "trigger_reasons": ["Heart rate above 130 bpm"],
    "recommendation_code": "RISK_OBSERVE_AND_NOTIFY"
  }
}
```

### 2. 预警检查

接口：

```text
POST /api/v1/health/warning/check
```

请求示例：

```json
{
  "window_data": [
    {
      "timestamp": "2026-03-23T21:00:00+08:00",
      "heart_rate": 86,
      "spo2": 96,
      "sbp": 126,
      "dbp": 84,
      "body_temp": 36.7,
      "fall_detection": false,
      "data_accuracy": 95
    },
    {
      "timestamp": "2026-03-23T21:30:00+08:00",
      "heart_rate": 136,
      "spo2": 88,
      "sbp": 165,
      "dbp": 102,
      "body_temp": 38.1,
      "fall_detection": false,
      "data_accuracy": 94
    }
  ]
}
```

当前版本会对 `window_data` 做真实的窗口聚合判断，并在响应中返回 `window_mode=event_aggregated_window`。
单个轻微越界点只会进入候选状态，满足“最近 3 点至少 2 点异常”或达到最短持续时长后才升级为正式事件。

### 3. 健康解释

接口：

```text
POST /api/v1/agent/health/explain
```

请求示例：

```json
{
  "role": "children",
  "health_result": {
    "elderly_id": "E10001",
    "device_id": "BAND_001",
    "timestamp": "2026-03-23T21:30:00+08:00",
    "health_score": 58.0,
    "final_health_score": 58.0,
    "rule_health_score": 66.0,
    "model_health_score": 46.0,
    "risk_level": "warning",
    "risk_score_raw": 0.54,
    "sub_scores": {
      "score_hr": 80.0,
      "score_spo2": 45.0,
      "score_bp": 50.0,
      "score_temp": 60.0
    },
    "alerts": {
      "hr_alert": {"label": "High", "probability": 0.5},
      "spo2_alert": {"label": "Low", "probability": 0.5},
      "bp_alert": {"label": "High", "probability": 0.5},
      "temp_alert": {"label": "Abnormal", "probability": 0.5},
      "hard_threshold_level": "warning"
    },
    "abnormal_tags": ["low_spo2", "hypertension", "fever"],
    "trigger_reasons": ["SpO2 below 90%"],
    "recommendation_code": "RISK_OBSERVE_AND_NOTIFY"
  }
}
```

## 测试

运行全部测试：

```powershell
conda run -n helth pytest tests/test_rule_engine.py tests/test_inference.py tests/test_health_api.py
```

这些测试覆盖：

- 正常输入
- 低血氧
- 高心率
- 高血压
- 发热
- 跌倒
- 数据越界

## LangChain / LangGraph 接入

当前已经提供本地 Agent 工具服务 `backend/services/agent_tool_service.py`，包括：

- `get_health_score_tool(payload)`
- `check_warning_tool(payload)`
- `explain_health_result_tool(payload)`

并预留：

- `build_langchain_tools()`：返回 LangChain v1 风格工具
- `build_langgraph_workflow()`：返回最小 LangGraph 工作流骨架

当前版本不强制接入真实 LLM API，但工具接口已经能直接被上层 Agent 编排复用。

## 后续如何升级为时序模型

当前数据不是严格连续时间序列，因此第一版先使用静态 MLP。未来如采集到稳定窗口序列数据，可按下面路径升级：

1. 在数据层补齐按设备分组的固定长度序列样本。
2. 将 `backend/models/tcn_health_model.py` 作为正式训练模型接入。
3. 在 `backend/ml/dataset.py` 中新增序列 Dataset。
4. 在 `backend/ml/trainer.py` 中增加 TCN/GRU 训练入口。
5. 在 `backend/ml/inference.py` 中根据模型版本切换静态推理或时序推理。

这条升级路径已经在当前工程结构中预留好了，不需要再推翻第一版静态链路。
