# 智慧康养主系统功能与接口说明

> 文档版本：1.1<br>
> 代码基线：`e8ecea4`（2026-07-29）<br>
> 康伴智能体冻结基线：`robot-agent-v1.1-qweather`（`46a46d6`）<br>
> 主系统名称：AIoT Elder Care Monitoring System<br>
> 默认后端端口：`8000`<br>
> 默认 Web 前端端口：`5173`

## 1. 文档目的

本文用于统一说明智慧康养主系统的建设目的、业务边界、用户角色、功能模块、数据流、接口契约、运行方式和当前限制，可用于：

- 项目介绍、比赛演示和答辩准备；
- Web 前端、Flutter 移动端与后端联调；
- T10 手环、摄像头和独立 Vision Service 接入；
- 新成员快速理解代码结构和业务流程；
- 测试、运维和故障排查时确认系统职责。

本文以当前代码、运行时 OpenAPI 描述以及仓库内现有说明为事实来源。接口实现发生变化后，应同步更新本文和 OpenAPI 文档。

## 2. 主系统定位与建设目标

主系统是面向社区养老、居家康养和健康关怀场景的 AIoT 健康监测与预警平台。它将老人、家属、社区工作人员、可穿戴设备、摄像头、健康分析模型、AI 智能体和 Go2 具身执行系统组织在同一业务体系中。

系统重点解决以下问题：

1. **健康数据分散**：统一接收手环、模拟设备、串口采集器和 MQTT 网关的生命体征数据。
2. **异常发现滞后**：结合规则、统计异常检测和健康评分模型识别 SOS、低血氧、心率异常、体温异常、血压风险等事件。
3. **告警触达不统一**：把手环 SOS、生命体征异常和视觉跌倒事件转成统一告警，通过 REST、WebSocket 和移动推送记录提供给业务端。
4. **社区管理缺少全局视角**：提供老人、家属、设备、健康趋势、告警队列、风险排名和关系拓扑。
5. **专业信息难以理解**：使用 AI 智能体、RAG 知识库和报告生成能力，将健康数据转成结构化解释和处置建议。
6. **多设备、多端难联动**：为 Vue 社区端、家庭 Web 端、Flutter 移动端、手环和 Vision Service 提供统一业务接口。
7. **陪伴决策与机器人执行容易耦合**：通过康伴智能体、动作计划、安全守卫和 Robot Gateway 分离用户意图、决策与真实运动。

主系统的核心价值不是替代医疗诊断，而是完成“数据采集—风险识别—告警联动—人工处置—报告总结”的健康关怀闭环。

## 3. 系统边界

### 3.1 主系统包含的能力

- 用户注册、登录、角色会话和访问范围；
- 老人、家属、社区、设备及绑定关系管理；
- 手环健康数据接入、校验、持久化和实时推送；
- 健康评分、规则预警、趋势分析和社区聚合；
- 告警生成、优先级队列、确认、去重和推送记录；
- 社区工作台、家属页面、报告页面和关系拓扑；
- AI 智能体、RAG 检索、设备/社区分析和报告生成；
- 独立康伴智能体，融合健康上下文和天气感知，生成受安全约束且默认不可执行的动作计划；
- Go2 机器人状态、任务、导航、应急和工作台能力，以及受能力状态与安全联锁约束的执行接口；
- 摄像头源管理、快照、视频流代理和音频状态；
- Vision Service 桥接、跌倒事件接收和业务告警提升；
- ASR、TTS 和 Omni 多模态分析接口；
- 模型微调数据、评估门禁和适配器状态查询。

### 3.2 主系统不等于 Vision Service

主系统和独立视觉服务必须按接口特征识别，不能按固定 IP 猜测。

| 系统 | 核心职责 | 典型接口特征 |
|---|---|---|
| 主系统 | 接收健康/视觉结果，管理用户设备，形成业务告警并向多端展示 | `/api/v1/*`、`/ws/alarms`，`/healthz` 返回 `app=AIoT Elder Care Monitoring System` |
| Vision Service | 拉取摄像头视频、执行目标/姿态/跌倒识别、输出结构化视觉结果 | `/status`、`/stream/*`、`/integration/results/{camera_id}/latest` |

一句话概括：Vision Service 负责“看和判”，主系统负责“收、转、关联、告警和展示”。

### 3.3 系统身份确认

主系统身份检查：

```http
GET http://<host>:8000/healthz
```

预期响应：

```json
{
  "status": "ok",
  "app": "AIoT Elder Care Monitoring System"
}
```

联调视觉能力前，应分别确认主系统和 Vision Service 的真实地址，再配置 `VISION_SERVICE_BASE_URL`。局域网 IP 可能在切换 Wi-Fi、热点或网卡后变化。

### 3.4 康伴智能体与 Go2 的安全边界

康伴智能体负责“感知、理解、决策和计划”，Go2 系统负责“能力声明、任务管理和受控执行”。两者通过明确契约连接，不允许 LLM 或前端按钮直接调用机器人运动 SDK。

当前边界如下：

- 康伴智能体已接入真实健康上下文、WeatherProvider、QWeather、Mock 降级、Action Planner 和 Safety Guard；
- 动作计划固定为 `enabled=false`、`execution=not_executed`，不会触发 Go2；
- Go2 工作台可展示状态、任务、导航和应急信息；
- 跟随页面当前只登记本地请求意图，“跟随请求”不代表机器人已接受或执行；
- LocationProvider、真实 GPS、康伴驾驶舱和真实 `follow_elder` 执行尚未纳入当前基线。

## 4. 用户角色与使用场景

| 角色 | 主要目标 | 当前主要入口 | 主要权限 |
|---|---|---|---|
| 社区工作人员 `community` | 管理社区老人、设备和风险事件 | Vue Web 社区端 | 社区总览、成员设备、拓扑、报告、智能体、写操作 |
| 管理员 `admin` | 管理和调试整个主系统 | Vue Web 社区端/调试入口 | 与社区工作人员类似，并保留管理语义 |
| 家属 `family` | 查看关联老人的健康与告警 | Vue 家属页、Flutter 家属端 | 查看授权老人数据，访问报告和关怀功能，可执行受限设备操作 |
| 老人 `elder` | 查看个人状态并绑定自己的设备 | 主要为 Flutter 老人端 | 个人数据、自助绑定/解绑、语音关怀 |
| 演示/调试人员 | 验证数据、告警、摄像头和视觉桥接 | 调试页、诊断脚本、OpenAPI | 依赖当前开发环境配置，不应视为生产角色 |

### 4.1 Web 页面与路由

Vue 前端使用自定义 Hash 路由，并未使用 Vue Router。

| 页面 | Hash | 允许角色 | 用途 |
|---|---|---|---|
| 社区总览 | `#/overview` | `community`、`admin` | 社区指标、老人风险、设备和告警总览 |
| 关系拓扑 | `#/topology` | `community`、`admin` | 老人—家属—设备关系展示 |
| 成员设备 | `#/members` | `community`、`admin` | 用户注册、设备登记、绑定、解绑和履历 |
| 社区报告 | `#/report` | `community`、`admin` | 交接/周期报告和导出 |
| 智能体 | `#/agent` | `community`、`admin` | 社区/老人分析、风险排序、问答和报告 |
| 机器人任务 | `#/robot-tasks` | `community`、`admin` | Go2 任务、时间线、观察结果和安全状态 |
| 机器人状态 | `#/robot-status` | `community`、`admin` | Robot Gateway 状态、能力和诊断信息 |
| 建图巡航 | `#/robot-navigation` | `community`、`admin` | 地图、点位、路线和导航任务管理 |
| 机器狗跟随 | `#/robot-follow` | `community`、`admin` | 第一视角监看和本地跟随请求登记，不代表真实执行 |
| 机器人应急 | `#/robot-emergency` | `community`、`admin` | 跌倒应急任务、对话、升级和返航流程 |
| 家属页面 | `#/family` | `family` | 关联老人健康、趋势、告警和建议 |
| 调试页 | `#/debug` | `community`、`admin` | 系统状态、摄像头、桥接和模拟链路；不在普通导航白名单中 |

当前 Web 端没有完整的老人业务页面，老人使用场景主要由 Flutter 移动端承载。

## 5. 总体架构

```text
                         智慧康养主系统
                                │
          ┌─────────────────────┼─────────────────────┐
          │                     │                     │
          ▼                     ▼                     ▼
   健康数据与告警线        视觉风险感知线          智能体决策线
 T10 / BLE / MQTT       Vision Service       健康智能体 / 康伴智能体
          │                     │                     │
          ▼                     ▼                     ▼
 校验/评分/预警/队列      跌倒识别/视频桥接      RAG / HealthContext
          │                     │              WeatherProvider
          └──────────┬──────────┘                     │
                     ▼                                ▼
              统一健康与风险上下文          Action Planner + Safety Guard
                     │                                │
                     ├───────────────┬────────────────┘
                     ▼               ▼
              Vue / Flutter     受约束 Action Plan
                                      │
                                      ▼
                            Robot Gateway / 能力检查
                                      │
                                      ▼
                              Go2 具身执行系统
```

### 5.1 技术栈

| 层级 | 当前技术 |
|---|---|
| 后端 | Python 3.11、FastAPI、Uvicorn、Pydantic v2 |
| Web 前端 | Vue 3、TypeScript、Vite、ECharts、html2canvas、jsPDF |
| 移动端 | Flutter，多平台工程结构 |
| 本地数据 | SQLite、文件数据、JSON/JSONL、模型 artifacts |
| 预留生产数据栈 | PostgreSQL 15、TimescaleDB、Redis |
| 健康模型 | PyTorch、scikit-learn、规则引擎、动态 Z-Score |
| 视觉 | OpenCV、Ultralytics/YOLO、ONNX Runtime、独立 Vision Service |
| 智能体 | LangChain、LangGraph、ChromaDB、BM25/RAG、Qwen/DashScope、Ollama |
| 环境感知 | WeatherProvider、QWeather、Mock 自动降级 |
| 具身执行 | Robot Gateway、任务/导航/应急契约、能力状态和安全联锁 |
| 实时通信 | WebSocket、MJPEG、HTTP 轮询/推送 |

### 5.2 关键代码目录

| 路径 | 职责 |
|---|---|
| `backend/main.py` | FastAPI 应用、路由注册、后台采集任务和 WebSocket 入口 |
| `backend/api/` | REST API 路由 |
| `backend/models/` | Pydantic 业务模型和接口 Schema |
| `backend/services/` | 用户、设备、健康、告警、摄像头和桥接业务逻辑 |
| `backend/repositories/` | SQLite/业务仓储 |
| `backend/ml/`、`ai/` | 健康评分、规则与异常检测 |
| `iot/` | 串口、MQTT、BLE 报文解析和采集 |
| `agent/` | 智能体、RAG、提示词和模型适配 |
| `agent/robot_companion/` | 康伴智能体、上下文融合、动作规划、安全守卫和天气 Provider |
| `backend/api/robot_*.py` | 康伴、机器人任务、导航、应急和实时通道路由 |
| `backend/services/robot_*.py` | Robot Gateway、任务、导航、风险融合和安全联锁服务 |
| `frontend/vue-dashboard/` | Vue 社区端和家属端 |
| `mobile/flutter_app/` | Flutter 老人端/家属端能力 |
| `fall_detection_model_bundle/` | 跌倒检测模型、训练、评估和运行资源 |
| `pose_detection_model_bundle/` | 姿态检测配置与运行脚本 |
| `docs/knowledge-base/` | RAG 使用的健康与处置知识文档 |
| `scripts/` | 启动、诊断、训练、导出和 smoke 测试脚本 |

## 6. 核心功能模块

### 6.1 用户、认证与关系管理

系统支持老人、家属和社区工作人员注册，登录后返回会话 Token 与用户信息。老人和家属通过关系记录关联，设备绑定到老人后，健康数据、告警和报告才能获得正确业务归属。

当前同时保留两套注册入口：

- `/api/v1/auth/register/*`：公开注册流程；
- `/api/v1/users/*/register`：需要具有写权限的 Bearer 会话，面向社区管理操作。

这两套入口是当前兼容结构，不代表应由客户端同时调用。

### 6.2 设备接入与绑定

设备域将“设备主档”“在线状态”和“业务绑定状态”分开管理：

- 接入模式：`serial`、`mqtt`、`ble`、`mock`；
- 在线状态：由 `DeviceStatus` 表示；
- 激活状态：由 `DeviceActivationState` 表示；
- 绑定状态：`unbound`、`bound`、`disabled`。

推荐流程是先注册用户，再登记设备，最后绑定到老人。设备换绑会保留绑定履历。串口模式可通过 `serial-target` 切换当前采集目标。

### 6.3 健康数据采集与实时推送

主系统可从 Mock、串口、MQTT 或显式 HTTP 接口接收 `HealthSample`。T10 串口链路支持 A/B 包合并、广播 SOS 补抓、MAC 标准化、无效全零样本过滤和历史字段补齐。

有效样本进入系统后依次执行：

1. 数据格式与范围校验；
2. 设备身份和来源匹配；
3. 样本持久化；
4. 实时规则告警；
5. 智能异常分析；
6. 社区风险聚合；
7. 健康 WebSocket 广播。

### 6.4 健康评分、趋势与预警

系统提供两类分析方式：

- 单次快照评分：心率、血氧、收缩压、舒张压、体温、跌倒标记和数据准确率；
- 时间窗口预警：聚合多个时间点，抑制短时抖动，输出风险、活动事件和稳定化解释。

评分链路由规则权重与静态模型融合。硬阈值事件可直接提升风险，模型不可用时是否允许纯规则降级由运行配置决定。

### 6.5 告警与通知

告警来源包括：

- 手环 SOS；
- 生命体征异常；
- 模型/统计异常；
- 社区群体风险；
- 设备状态异常；
- Vision Service 跌倒事件。

告警进入优先级队列后可由客户端查询或确认。SOS 和跌倒告警包含去重、同源事件折叠和确认后冷却逻辑，避免一次物理事件产生多次弹窗。

当前“移动推送”主要是主系统内部生成并保存推送记录；代码中的 `NotificationService` 为模拟投递实现，不能等同于已经接入厂商级 APNs、FCM 或国内推送通道。

### 6.6 社区看板与家属关怀

社区看板提供老人数量、家属数量、设备在线/离线/待激活状态、健康均值、告警数量、高风险老人、近期趋势和关系拓扑。家属页面按会话范围展示关联老人数据。

正式目录和 Demo 目录目前并存。当正式用户数据不足时，部分目录能力可能回退到演示数据，以保证比赛展示连续性。

### 6.7 AI 智能体、RAG 与报告

智能体支持：

- 单设备健康分析；
- 社区健康态势分析；
- 风险排序和告警摘要；
- 老人/社区周期报告；
- 健康评分自然语言解释；
- 流式输出、工具调用轨迹、图表附件和引用来源；
- 使用本地知识库检索处置建议。

模型提供方可按配置使用 Qwen/DashScope 或 Ollama。接口可用不代表模型一定可用，应先查询 `/api/v1/chat/capabilities`、`/api/v1/voice/status` 或 `/api/v1/omni/status`。

### 6.8 康伴智能体与环境感知

康伴智能体是独立于健康智能体的具身陪伴决策模块，当前能力链为：

```text
老人话语
  → 健康上下文 + 天气上下文 + 机器人状态
  → 意图识别
  → Action Planner
  → Safety Guard
  → 不可执行 Action Plan
```

天气通过 WeatherProvider 抽象接入，默认使用 Mock；配置 QWeather 后可获取实时天气，请求失败时自动降级。当前天气进入上下文，但尚未作为完整动作决策因子。位置仍为 Mock，尚未实现 LocationProvider。

### 6.9 Go2 机器人任务与工作台

Go2 子系统提供机器人健康状态、能力状态、任务、导航、应急处置和 WebSocket 实时通道。前端机器人工作区统一呈现任务中心、状态诊断、建图巡航、应急流程和跟随协同。

当前跟随页面只维护本地意图状态，不向机器人发送开始或停止跟随命令。真实运动必须经过能力检查、安全联锁和 Robot Gateway，不能把页面状态解释为硬件执行状态。

### 6.10 摄像头、视觉服务与跌倒桥接

主系统自身提供摄像头状态、快照、MJPEG 代理流、音频状态、摄像头源注册与切换能力。复杂视频识别可由独立 Vision Service 承担。

Vision Service 与主系统有两种联动方式：

1. 主系统轮询 Vision Service 的健康、视频源和最新结构化结果；
2. Vision Service 主动调用 `/api/v1/video-bridge/fall-events` 推送确认跌倒事件。

主系统接收跌倒事件后进行来源校验、事件去重、老人/家属/设备上下文注入，并转为统一告警。

### 6.11 语音与多模态

- ASR：上传音频并转写文本；
- TTS：将文本合成为 MP3、WAV 或 PCM；
- Omni：结合音频、文本和健康上下文进行多模态分析。

这些能力依赖外部或本地模型配置，应使用状态接口判断是否已配置，而不是仅以 HTTP 路由存在作为可用依据。

### 6.12 模型微调与诊断

模型微调接口主要用于查询能力、模板、数据集、评估门禁和适配器状态，以及触发数据集导出或评估流程。它属于开发/比赛调优工具，不应直接暴露给普通业务用户。

## 7. 关键业务流程

### 7.1 登录与访问

```text
客户端提交用户名和密码
  → POST /api/v1/auth/login
  → 返回 token、user、expires_at
  → 后续受保护接口携带 Authorization: Bearer <token>
  → GET /api/v1/auth/me 恢复会话
  → 前端按 user.role 决定页面范围
```

### 7.2 用户、设备和关系建立

```text
注册老人/家属
  → 建立 family ↔ elder 关系
  → 登记设备主档
  → 绑定设备到老人
  → 必要时切换串口采集目标
  → 健康样本开始归属到该老人
```

推荐接口顺序：

1. `POST /api/v1/users/elders/register`
2. `POST /api/v1/users/families/register`
3. `POST /api/v1/relations/family-bind`
4. `POST /api/v1/devices/register`
5. `POST /api/v1/devices/bind`
6. 串口设备需要时调用 `POST /api/v1/devices/serial-target`

### 7.3 健康样本与告警

```text
手环/HTTP/MQTT/Mock 样本
  → 校验、合包和持久化
  → 规则告警 + 智能异常分析
  → 告警队列与推送记录
  → /ws/health/{device_mac}
  → /ws/alarms
  → Vue/Flutter 展示或弹窗
  → 人工确认告警
```

### 7.4 视觉跌倒告警

```text
Vision Service 检测到确认跌倒
  → POST /api/v1/video-bridge/fall-events
  → 校验来源 IP 或 X-Vision-Service-Token
  → incident_id / camera_id + track_id 去重
  → 注入老人、家属和设备上下文
  → 生成主系统 fall 告警
  → WebSocket 广播并进入告警队列
```

### 7.5 智能体报告

```text
选择社区、老人或设备范围
  → 汇总历史健康数据、告警和关系上下文
  → 检索 docs/knowledge-base
  → 调用配置的 LLM
  → 返回分析、建议、引用、图表或报告附件
  → 前端展示或导出
```

### 7.6 康伴智能体决策

```text
老人话语
  → POST /api/v1/robot-agent/dialogue
  → 读取真实健康上下文
  → WeatherProvider 获取天气，失败时回退 Mock
  → 识别陪伴、散步、天气、健康或紧急意图
  → 生成 Action Plan
  → Safety Guard 检查
  → 返回回复、上下文、动作计划和安全状态
  → 当前不执行机器人运动
```

## 8. 数据模型与存储

### 8.1 核心实体

| 实体 | 关键字段 | 说明 |
|---|---|---|
| SessionUser | `id`、`username`、`name`、`role`、`community_id`、`family_id` | 登录会话用户 |
| ElderProfile | 老人身份、年龄、公寓、家属关系、设备关系 | 社区和家属业务主体 |
| FamilyProfile | 家属身份、关系、社区信息 | 与一个或多个老人关联 |
| DeviceRecord | `mac_address`、`model_code`、`ingest_mode`、`status`、`bind_status`、`user_id` | 设备主档与业务归属 |
| HealthSample | 心率、体温、血氧、血压、电量、步数、SOS、来源和原始包 | 原始/归一化健康样本 |
| AlarmRecord | 告警类型、级别、设备、时间、上下文、确认状态 | 统一业务告警 |
| DeviceBindLogRecord | 设备、原用户、新用户、操作人、原因和时间 | 绑定审计履历 |
| TargetUserRecord | 目标用户与人脸/视觉关联信息 | 摄像头目标识别业务 |

### 8.2 存储现状

- 本地开发默认数据库 URL 指向 `data/app.db` 的 SQLite；
- PostgreSQL/TimescaleDB Schema 位于 `database/schema.sql`，作为更完整的数据平台预留；
- 健康样本、告警、用户设备关系由仓储层写入本地数据库或运行数据文件；
- RAG 向量数据默认持久化在 `data/chroma`；
- 模型、Scaler、指标和训练配置位于 `data/artifacts`；
- 跌倒/姿态事件与截图位于对应运行数据目录；
- WebSocket 连接、部分告警队列和运行状态为进程内存状态。

由于部分实时状态保存在内存中，当前实现更适合单进程演示和本地联调；多实例部署前需要统一会话、队列和实时广播存储。

## 9. 接口通用约定

### 9.1 地址与在线文档

| 项目 | 默认地址 |
|---|---|
| REST API 基址 | `http://127.0.0.1:8000` |
| API v1 前缀 | `/api/v1` |
| Swagger UI | `http://127.0.0.1:8000/docs` |
| ReDoc | `http://127.0.0.1:8000/redoc` |
| OpenAPI JSON | `http://127.0.0.1:8000/openapi.json` |
| Web 前端 | `http://127.0.0.1:5173` |

跨机器或移动端联调时，将 `127.0.0.1` 替换为主系统主机的实际局域网地址，并确认后端监听 `0.0.0.0:8000`、防火墙允许访问。

### 9.2 数据格式

- 普通请求和响应默认使用 `application/json`；
- ASR 和 Omni 音频上传使用 `multipart/form-data`；
- 摄像头快照返回图片，视频流返回 MJPEG；
- 流式智能体接口返回流式事件，客户端应按实际 `Content-Type` 处理；
- 时间字段使用 ISO 8601，建议统一传 UTC，例如 `2026-07-19T01:30:00Z`；
- MAC 地址在服务端会进行标准化，推荐客户端统一使用大写冒号格式，例如 `53:57:08:00:00:01`。

### 9.3 认证与授权

受保护接口使用：

```http
Authorization: Bearer <token>
```

当前明确需要 Bearer 会话的接口包括：

- `/api/v1/auth/me`；
- 设备注册、绑定、解绑、换绑、删除、串口目标切换；
- 用户管理写接口和家属关系绑定；
- `/api/v1/care/access-profile/me`；
- `/api/v1/care/community/dashboard`；
- `/api/v1/agent/elders`。

设备普通写权限允许 `family`、`community`、`admin`；老人自助绑定只允许 `elder`。社区看板和智能体老人列表只允许 `community`、`admin`。

当前代码没有在 FastAPI OpenAPI 中统一声明 Security Scheme，而是由具体接口手动读取 `Authorization` Header，因此 Swagger UI 不一定显示统一的“Authorize”锁标志。

### 9.4 常见状态码

| 状态码 | 含义 | 常见场景 |
|---|---|---|
| `200` | 成功 | 查询、更新、业务处理成功 |
| `400` | 请求或业务规则错误 | 字段组合错误、设备状态不允许 |
| `401` | 未登录或会话失效 | 缺少 Bearer Token、Token 无效 |
| `403` | 无权限或来源校验失败 | 角色不允许、Vision 推送来源不可信 |
| `404` | 资源不存在 | 用户、设备、告警、摄像头源不存在 |
| `409` | 业务冲突 | 重复设备、重复绑定、跌倒事件未生成新告警 |
| `422` | Schema 校验失败 | 必填字段缺失、数值越界、枚举错误 |
| `501` | 当前工作区未启用 | 跌倒模拟接口当前固定返回未启用 |
| `502` | 上游服务失败 | Vision Service 探测或切换失败 |

## 10. 关键接口契约

### 10.1 登录

```http
POST /api/v1/auth/login
Content-Type: application/json
```

请求：

```json
{
  "username": "community_admin",
  "password": "123456"
}
```

响应关键字段：

| 字段 | 类型 | 说明 |
|---|---|---|
| `token` | string | 后续 Bearer 会话令牌 |
| `user.id` | string | 用户 ID |
| `user.username` | string | 登录名 |
| `user.name` | string | 显示名称 |
| `user.role` | enum | `elder`、`family`、`community`、`admin` |
| `user.community_id` | string | 社区范围 |
| `user.family_id` | string/null | 家属业务范围 |
| `expires_at` | datetime/null | 会话到期时间 |

`/auth/mock-login` 使用相同请求/响应结构，但只用于 Demo 兼容。`/auth/mock-accounts` 会公开演示账号信息，不应在生产环境保持开放。

### 10.2 用户注册

老人注册的主要字段：

| 字段 | 必填 | 约束 |
|---|---|---|
| `name` | 是 | 老人姓名 |
| `phone` | 是 | 手机号/登录标识来源 |
| `password` | 是 | 最少 6 位 |
| `age` | 是 | 50～120 |
| `apartment` | 是 | 房间或住址 |
| `community_id` | 否 | 默认 `community-haitang` |

家属注册主要增加 `relationship`，社区工作人员注册不需要年龄和公寓。管理写入口需要 Bearer Token，`/auth/register/*` 为当前公开注册入口。

### 10.3 设备登记与绑定

登记设备：

```http
POST /api/v1/devices/register
Authorization: Bearer <token>
```

```json
{
  "mac_address": "53:57:08:00:00:01",
  "device_name": "T10-WATCH-01",
  "model_code": "t10_v3",
  "ingest_mode": "serial"
}
```

绑定设备：

```http
POST /api/v1/devices/bind
Authorization: Bearer <token>
```

```json
{
  "mac_address": "53:57:08:00:00:01",
  "target_user_id": "elder-001",
  "operator_id": "community-user-001",
  "new_ingest_mode": "serial"
}
```

设备登记默认形成未绑定主档；绑定成功后返回绑定日志。常见冲突包括 `DEVICE_ALREADY_EXISTS`、`DEVICE_ALREADY_BOUND` 和 `TARGET_USER_ALREADY_HAS_DEVICE_OF_SAME_MODEL`。

### 10.4 健康样本接入

```http
POST /api/v1/health/ingest
Content-Type: application/json
```

```json
{
  "device_mac": "53:57:08:00:00:01",
  "timestamp": "2026-07-19T01:30:00Z",
  "heart_rate": 76,
  "temperature": 36.5,
  "blood_oxygen": 98,
  "blood_pressure": "122/78",
  "battery": 86,
  "steps": 3210,
  "sos_flag": false,
  "source": "serial",
  "packet_type": "response_b"
}
```

核心约束：

- `heart_rate`：0～240；
- `temperature`：0～45；
- `blood_oxygen`：0～100；
- `battery`：0～100；
- `device_mac`、`heart_rate`、`temperature`、`blood_oxygen` 必填；
- 全零或明显无效样本可能通过 Schema 校验，但会在业务校验阶段被丢弃。

### 10.5 健康评分

```http
POST /api/v1/health/score
```

请求字段：`heart_rate`、`spo2`、`sbp`、`dbp`、`body_temp`、`fall_detection`、`data_accuracy`、`elderly_id`、`device_id`、`timestamp`。除 `fall_detection` 和 `data_accuracy` 外均为主要必填业务字段。

响应包含评分结果、风险等级、告警预测、结构化解释和服务元数据。实际完整结构以 `HealthScoreApiResponse` OpenAPI Schema 为准。

### 10.6 窗口预警

```http
POST /api/v1/health/warning/check
```

请求由可选 `current_data` 和 `window_data[]` 组成。建议优先传递时间窗口数据，让系统执行事件聚合和稳定化，避免只用单点数据造成边界抖动。

### 10.7 AI 社区分析

```http
POST /api/v1/chat/analyze/community
```

主要字段：

| 字段 | 说明 |
|---|---|
| `question` | 用户问题或报告指令 |
| `role` | 默认 `community` |
| `mode` / `provider` | `auto`、`qwen`、`tongyi`、`ollama` 中受 Schema 允许的值 |
| `history_minutes` | 分析历史窗口，默认 1440 分钟 |
| `device_macs` | 指定设备范围 |
| `workflow` | 总览、风险排序、告警摘要、设备/老人聚焦、报告或自由对话 |
| `focus_device_mac` | 聚焦设备 |
| `subject_elder_id` | 聚焦老人 |
| `window` | `day` 等报告窗口 |
| `history` | 对话历史 |
| `include_report` | 是否附带报告结构 |

需要逐事件接收输出时调用 `/api/v1/chat/analyze/community/stream`。

### 10.8 Vision Service 跌倒事件上报

```http
POST /api/v1/video-bridge/fall-events
X-Vision-Service-Token: <optional-token>
Content-Type: application/json
```

最小必填字段只有 `camera_id`，但正式联调建议提供完整事件身份和置信度：

```json
{
  "camera_id": "camera_01",
  "stream_name": "primary",
  "source": "vision_service",
  "event_type": "fall_confirmed",
  "state": "confirmed_fall",
  "status": "confirmed_fall",
  "service_state": "running",
  "severity": "L3",
  "risk": "high",
  "fall_detected": true,
  "fall_prob": 0.94,
  "fall_score": 0.94,
  "track_id": "target-001",
  "incident_id": "fall-camera_01-20260719-001",
  "bbox": [318.0, 244.0, 712.0, 981.0],
  "snapshot_url": "http://<vision-host>:8000/fall-events/snapshots/fall-001.jpg",
  "timestamp": "2026-07-19T01:30:00Z",
  "demo": false,
  "scores": {
    "detector": 0.94,
    "posture": 0.91,
    "hybrid": 0.94
  },
  "metadata": {
    "source_camera_name": "room-a"
  }
}
```

来源校验满足以下任一条件：

- 请求来源 IP 与当前配置的 Vision Service 主机一致；
- `X-Vision-Service-Token` 与主系统运行配置中的推送令牌一致。

成功响应关键字段：`accepted`、`pushed`、`alarm_id`、`alarm_type`、`alarm`、`camera_id`、`risk`、`fall_prob`、`triggered_at`、`elder_id`、`elder_name`。

### 10.9 Vision Service 运行配置

```http
PATCH /api/v1/video-bridge/runtime-config
```

```json
{
  "base_url": "http://<vision-host>:8000",
  "camera_id": "camera_01",
  "poll_enabled": true,
  "poll_hz": 2.0,
  "timeout_seconds": 2.5,
  "push_token": "",
  "target_device_mac": "CAMERA-01",
  "target_elder_id": "elder-001",
  "target_family_ids": ["family-001"]
}
```

`poll_hz` 允许 0.2～5.0，`timeout_seconds` 允许 0.5～30.0。该接口当前会改变进程运行配置，但没有统一 Bearer 鉴权，上线前必须收紧访问控制。

## 11. HTTP 接口目录

本节按 Go2 小康语音闭环接入后的运行实例整理，共 **192 个 HTTP 操作**。字段、枚举、默认值和响应 Schema 以 `/openapi.json` 为最终机器可读契约。

### 11.1 系统状态（4）

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/healthz` | 主系统健康检查和身份识别 |
| GET | `/api/v1/system/info` | 运行模式、采集、模型、Vision 和 Demo 配置摘要 |
| GET | `/api/v1/system/demo-data/status` | Demo 数据状态 |
| POST | `/api/v1/system/demo-data/refresh` | 刷新社区演示数据窗口 |

### 11.2 认证（7）

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/v1/auth/mock-accounts` | 列出演示账号 |
| POST | `/api/v1/auth/login` | 正式/统一登录 |
| POST | `/api/v1/auth/mock-login` | Demo 登录兼容入口 |
| GET | `/api/v1/auth/me` | 根据 Bearer Token 恢复会话 |
| POST | `/api/v1/auth/register/elder` | 公开注册老人 |
| POST | `/api/v1/auth/register/family` | 公开注册家属 |
| POST | `/api/v1/auth/register/community-staff` | 公开注册社区工作人员 |

### 11.3 用户与关系（4）

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/api/v1/users/elders/register` | 管理端注册老人，需要写权限 |
| POST | `/api/v1/users/families/register` | 管理端注册家属，需要写权限 |
| POST | `/api/v1/users/community-staff/register` | 管理端注册社区人员，需要写权限 |
| POST | `/api/v1/relations/family-bind` | 建立家属—老人关系，需要写权限 |

### 11.4 设备（11）

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/v1/devices` | 设备列表 |
| GET | `/api/v1/devices/{mac_address}` | 设备详情 |
| GET | `/api/v1/devices/{mac_address}/bind-logs` | 绑定履历 |
| POST | `/api/v1/devices/register` | 登记设备主档 |
| POST | `/api/v1/devices/bind` | 绑定设备到目标用户 |
| POST | `/api/v1/devices/unbind` | 解绑设备 |
| POST | `/api/v1/devices/rebind` | 换绑设备 |
| DELETE | `/api/v1/devices/{mac_address}` | 删除设备主档 |
| POST | `/api/v1/devices/bind/self` | 老人自助绑定 |
| POST | `/api/v1/devices/unbind/self` | 老人/授权用户自助解绑 |
| POST | `/api/v1/devices/serial-target` | 切换串口采集目标 |

### 11.5 关怀目录与看板（4）

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/v1/care/directory` | 社区关怀目录，保留 Demo 回退 |
| GET | `/api/v1/care/directory/family/{family_id}` | 家属范围目录 |
| GET | `/api/v1/care/access-profile/me` | 当前老人/家属访问范围 |
| GET | `/api/v1/care/community/dashboard` | 社区聚合看板，需要社区/管理员会话 |

### 11.6 健康数据与分析（10）

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/api/v1/health/ingest` | 接收健康样本 |
| GET | `/api/v1/health/realtime/{device_mac}` | 最新实时样本 |
| GET | `/api/v1/health/trend/{device_mac}` | 分钟窗口趋势，支持 `minutes`、`limit` |
| GET | `/api/v1/health/devices/{device_mac}/history` | 桶化历史，支持 `window`、`bucket` |
| GET | `/api/v1/health/community/overview` | 社区健康概览 |
| POST | `/api/v1/health/community/window-report` | 生成社区窗口报告 |
| GET | `/api/v1/health/community/window-report/export` | 导出社区窗口报告数据 |
| GET | `/api/v1/health/intelligent/{device_mac}` | 设备智能分析 |
| POST | `/api/v1/health/score` | 结构化健康评分 |
| POST | `/api/v1/health/warning/check` | 时间窗口预警检查 |

### 11.7 告警（5）

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/v1/alarms` | 告警列表，支持设备和活动状态过滤 |
| GET | `/api/v1/alarms/queue` | 优先级告警队列 |
| GET | `/api/v1/alarms/queue/snapshot` | 队列统计快照 |
| GET | `/api/v1/alarms/mobile-pushes` | 移动推送记录，带会话时按角色过滤 |
| POST | `/api/v1/alarms/{alarm_id}/acknowledge` | 确认告警并广播队列变化 |

### 11.8 智能体与聊天（12）

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/api/v1/agent/community/summary` | 社区窗口结构化总结 |
| GET | `/api/v1/agent/elders` | 智能体可分析老人列表，需要社区权限 |
| POST | `/api/v1/agent/health/explain` | 健康评分解释 |
| POST | `/api/v1/agent/health-score/insight` | 健康评分洞察 |
| POST | `/api/v1/chat/analyze` | 设备分析兼容入口 |
| POST | `/api/v1/chat/analyze/device` | 设备级 AI 分析 |
| POST | `/api/v1/chat/analyze/device/stream` | 设备级流式分析 |
| POST | `/api/v1/chat/analyze/community` | 社区级 AI 分析 |
| POST | `/api/v1/chat/analyze/community/stream` | 社区级流式分析 |
| POST | `/api/v1/chat/report/device` | 设备健康报告 |
| GET | `/api/v1/chat/capabilities` | 模型、RAG、流式等能力状态 |
| GET | `/api/v1/chat/mcp-tools` | 智能体工具规格 |

### 11.9 摄像头（14）

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/v1/camera/status` | 摄像头状态 |
| GET | `/api/v1/camera/stream-status` | 视频流状态 |
| GET | `/api/v1/camera/health` | 摄像头健康检查 |
| GET | `/api/v1/camera/snapshot` | 原始快照 |
| GET | `/api/v1/camera/processed-snapshot` | 处理后快照 |
| GET | `/api/v1/camera/family-snapshot` | 家属端快照 |
| GET | `/api/v1/camera/stream.mjpg` | 原始 MJPEG 流 |
| GET | `/api/v1/camera/processed-stream.mjpg` | 处理后 MJPEG 流 |
| GET | `/api/v1/camera/family-stream.mjpg` | 家属端 MJPEG 流 |
| GET | `/api/v1/camera/audio/status` | 音频能力状态 |
| GET | `/api/v1/camera/audio/stream-status` | 音频流状态 |
| GET | `/api/v1/camera/setup` | 查询摄像头设置 |
| POST | `/api/v1/camera/setup` | 更新摄像头设置 |
| GET | `/api/v1/camera/detection-models/status` | 视觉/姿态模型状态 |

### 11.10 摄像头源（25）

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/v1/camera-sources` | 摄像头源列表 |
| GET | `/api/v1/camera-sources/registration` | 注册和选择状态 |
| POST | `/api/v1/camera-sources/registration/local/select` | 选择本地摄像头 |
| POST | `/api/v1/camera-sources/registration/external` | 注册外部摄像头 |
| DELETE | `/api/v1/camera-sources/registration/external/{camera_id}` | 删除外部摄像头 |
| POST | `/api/v1/camera-sources/registration/select` | 选择已注册摄像头 |
| GET | `/api/v1/camera-sources/active` | 当前活动源详情 |
| GET | `/api/v1/camera-sources/active/status` | 当前源状态 |
| GET | `/api/v1/camera-sources/active/snapshot` | 当前源快照 |
| GET | `/api/v1/camera-sources/active/stream-status` | 当前源流状态 |
| GET | `/api/v1/camera-sources/active/stream.mjpg` | 当前源 MJPEG 流 |
| GET | `/api/v1/camera-sources/active/audio/status` | 当前源音频状态 |
| GET | `/api/v1/camera-sources/active/audio/stream-status` | 当前源音频流状态 |
| POST | `/api/v1/camera-sources/active/ptz` | 当前源云台控制 |
| GET | `/api/v1/camera-sources/{camera_id}` | 指定源详情 |
| GET | `/api/v1/camera-sources/{camera_id}/status` | 指定源状态 |
| GET | `/api/v1/camera-sources/{camera_id}/snapshot` | 指定源快照 |
| GET | `/api/v1/camera-sources/{camera_id}/stream-status` | 指定源流状态 |
| GET | `/api/v1/camera-sources/{camera_id}/stream.mjpg` | 指定源原始流 |
| GET | `/api/v1/camera-sources/{camera_id}/processed-snapshot` | 指定源处理后快照 |
| GET | `/api/v1/camera-sources/{camera_id}/stream.processed.mjpg` | 指定源处理后流 |
| GET | `/api/v1/camera-sources/{camera_id}/audio/status` | 指定源音频状态 |
| GET | `/api/v1/camera-sources/{camera_id}/audio/stream-status` | 指定源音频流状态 |
| GET | `/api/v1/camera-sources/{camera_id}/talk/status` | 指定源对讲状态 |
| POST | `/api/v1/camera-sources/{camera_id}/ptz` | 指定源云台控制 |

### 11.11 视频桥接与统一 Vision 代理（16）

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/api/v1/video-bridge/analysis` | 接收通用视频分析结果 |
| GET | `/api/v1/video-bridge/status` | 视频桥接综合状态 |
| GET | `/api/v1/video-bridge/runtime-config` | 查询桥接运行配置 |
| PATCH | `/api/v1/video-bridge/runtime-config` | 更新桥接运行配置 |
| POST | `/api/v1/video-bridge/vision/poll-once` | 立即轮询一次 Vision Service |
| GET | `/api/v1/video-bridge/vision/health` | 查询上游视觉健康状态 |
| GET | `/api/v1/video-bridge/vision/source` | 查询上游视频源 |
| GET | `/api/v1/video-bridge/vision/latest` | 查询上游最新识别结果 |
| POST | `/api/v1/video-bridge/vision/probe` | 探测视觉流 |
| POST | `/api/v1/video-bridge/vision/switch-host` | 切换视觉主机 |
| POST | `/api/v1/video-bridge/fall-events` | 接收确认跌倒并生成告警 |
| POST | `/api/v1/video-bridge/simulate-fall-alarm` | 当前工作区未启用，固定返回 501 |
| GET | `/api/v1/vision/health` | 面向客户端的统一视觉健康代理 |
| GET | `/api/v1/vision/status` | 统一视觉状态代理 |
| GET | `/api/v1/vision/source` | 统一视觉源代理 |
| GET | `/api/v1/vision/results/latest` | 统一最新视觉结果代理 |

### 11.12 目标用户与本地/外部摄像头识别（16）

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/v1/target-users` | 目标用户列表 |
| POST | `/api/v1/target-users` | 创建目标用户 |
| DELETE | `/api/v1/target-users/{user_id}` | 删除目标用户 |
| GET | `/api/v1/target-users/status` | 目标用户服务状态 |
| POST | `/api/v1/target-users/match` | 匹配目标用户 |
| POST | `/api/v1/target-users/fall-detect` | 对目标用户执行跌倒检测 |
| GET | `/api/v1/target-users/external-camera/health` | 外部摄像头健康状态 |
| GET | `/api/v1/target-users/external-camera/config` | 查询外部摄像头配置 |
| POST | `/api/v1/target-users/external-camera/config` | 更新外部摄像头配置 |
| POST | `/api/v1/target-users/external-camera/probe` | 探测外部摄像头 |
| GET | `/api/v1/target-users/external-camera/discover` | 发现外部摄像头 |
| POST | `/api/v1/target-users/external-camera/refresh` | 刷新外部摄像头状态 |
| POST | `/api/v1/target-users/external-camera/bootstrap` | 引导配置外部摄像头 |
| POST | `/api/v1/target-users/external-camera/fall-detect` | 外部摄像头跌倒检测 |
| GET | `/api/v1/target-users/local-camera/snapshot` | 本地摄像头快照 |
| POST | `/api/v1/target-users/local-camera/pose-detect` | 本地摄像头姿态检测 |

### 11.13 语音与 Omni（6）

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/api/v1/voice/asr` | 上传音频并执行语音识别 |
| POST | `/api/v1/voice/tts` | 文本转语音 |
| GET | `/api/v1/voice/status` | ASR/TTS 配置状态 |
| POST | `/api/v1/omni/analyze` | 音频、文本和健康上下文多模态分析 |
| POST | `/api/v1/omni/analyze/stream` | 老人端语音回复文字及 PCM 音频 NDJSON 流式输出，并保留完整 WAV 兜底 |
| GET | `/api/v1/omni/status` | Omni 模型状态 |

`/api/v1/omni/analyze/stream` 的 multipart 请求字段、事件字段、错误语义和兼容性说明见 `docs/omni-streaming-api.md`。

### 11.14 模型微调（8）

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/v1/model-finetune/overview` | 微调模块总览 |
| GET | `/api/v1/model-finetune/capabilities` | 当前可用能力 |
| GET | `/api/v1/model-finetune/templates` | 训练/导出模板 |
| GET | `/api/v1/model-finetune/datasets` | 数据集状态 |
| POST | `/api/v1/model-finetune/datasets/export` | 导出微调数据集 |
| GET | `/api/v1/model-finetune/eval-gates` | 评估门禁状态 |
| POST | `/api/v1/model-finetune/eval-gates/run` | 执行评估门禁 |
| GET | `/api/v1/model-finetune/adapters` | 适配器状态 |

### 11.15 康伴与 Go2 小康智能体（3）

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/api/v1/robot-agent/dialogue` | 融合健康、天气与机器人上下文，返回陪伴回复、动作计划和安全状态；当前不执行动作 |
| GET | `/api/v1/go2-companion/status` | 查询 ASR、LLM、TTS 和 Go2 音频接入状态 |
| POST | `/api/v1/go2-companion/voice-turn` | 执行 ASR → 小康对话 → TTS，返回可播放 WAV；当前不声称已在 Go2 播放 |

### 11.16 Go2 机器人任务、导航与应急（47）

| 接口族 | 代表路径 | 用途 |
|---|---|---|
| 状态与诊断 | `/api/v1/robot/health`、`/api/v1/robot/status`、`/api/v1/robot/status/diagnostics` | Robot Gateway 健康、能力和诊断 |
| 任务 | `/api/v1/robot/tasks*` | 任务列表、详情、时间线、观察、取消和 Mock 回调 |
| 跌倒事件与回调 | `/api/v1/robot/events/fall`、`/api/v1/robot/callbacks/*` | 接收跌倒事件及机器人任务状态/结果 |
| 导航 | `/api/v1/robot/navigation/*` | 建图、地图、点位、路线、导航任务和手动接管 |
| 应急 | `/api/v1/robot/emergency/{incident_id}*` | 派遣、确认、升级、恢复、返航和应急对话 |

具体 47 个操作及其请求/响应 Schema 以 `/openapi.json` 为准。

## 12. WebSocket 与实时通信

主系统当前提供 9 个 WebSocket 通道：

| 路径 | 数据方向 | 主要内容 |
|---|---|---|
| `/ws/health/{device_mac}` | 服务端 → 客户端 | 指定设备的 `HealthSample` JSON |
| `/ws/alarms` | 服务端 → 客户端 | 新告警、告警确认和 `alarm_queue` 快照 |
| `/ws/camera` | 服务端 → 客户端 | 原始 JPEG 二进制帧 |
| `/ws/camera/processed` | 服务端 → 客户端 | 处理后 JPEG 二进制帧 |
| `/ws/camera/audio/listen` | 服务端 → 客户端 | 摄像头音频数据 |
| `/ws/robot/status` | 服务端 → 客户端 | 机器人状态、能力和诊断事件 |
| `/ws/robot/navigation` | 服务端 → 客户端 | 建图、地图、路线和导航任务事件 |
| `/ws/robot/emergency/{incident_id}` | 服务端 → 客户端 | 指定应急事件的任务、对话和处置状态 |
| `/ws/robot/point-cloud` | 服务端 → 客户端 | 点云流信息与点云帧 |

连接 `/ws/alarms` 后，服务端会先发送当前活动队列：

```json
{
  "type": "alarm_queue",
  "queue": [],
  "snapshot": {}
}
```

样本进入系统后，`/ws/health/{device_mac}` 收到完整健康样本 JSON；新告警或告警确认后，`/ws/alarms` 会收到告警记录和更新后的队列快照。

当前 WebSocket 注册表是进程内存结构，没有统一鉴权握手和跨实例消息总线。生产化时应增加 Token 校验、心跳协议、断线重连约定和 Redis/Kafka 等跨实例广播层。

## 13. 配置分类

敏感值必须通过本机 `.env` 或安全配置系统提供，不应写入文档、源码或 Git。

| 配置类别 | 代表变量 | 用途 |
|---|---|---|
| 应用 | `APP_NAME`、`HOST`、`PORT`、`API_V1_PREFIX` | 服务身份和监听地址 |
| 数据 | `DATABASE_URL`、`REDIS_URL`、`CHROMA_PATH` | 数据库、缓存和向量库 |
| 采集模式 | `DATA_MODE`、`USE_MOCK_DATA` | Mock、串口或 MQTT |
| 串口 | `SERIAL_PORT`、`SERIAL_BAUDRATE`、`SERIAL_*` | T10 采集器、包类型和 SOS 轮转 |
| MQTT | `MQTT_BROKER_HOST`、`MQTT_TOPIC`、`MQTT_*` | 网关接入 |
| 摄像头 | `CAMERA_IP`、`CAMERA_SOURCE_MODE`、`CAMERA_*` | RTSP、本地相机、音视频流 |
| Vision | `VISION_SERVICE_BASE_URL`、`VISION_SERVICE_CAMERA_ID`、`VISION_SERVICE_*` | 独立视觉服务桥接 |
| 跌倒/姿态 | `FALL_DETECTION_*`、`POSE_DETECTION_*` | 模型、阈值、目标和运行参数 |
| LLM/RAG | `LLM_PROVIDER`、`QWEN_*`、`OLLAMA_*`、`RAG_*` | 智能体、模型和知识检索 |
| 康伴天气 | `WEATHER_PROVIDER`、`QWEATHER_*` | Mock/QWeather 选择、API Host、密钥、位置和超时 |
| Go2/机器人 | `ROBOT_*`、`GO2_*` | Robot Gateway、上游状态、导航和安全策略 |
| 认证 | `JWT_SECRET`、`SEED_DEFAULT_ACCOUNTS` | 会话安全和演示账号 |

不得在问题排查记录、截图、日志或接口响应示例中暴露真实密码、Token、API Key 和摄像头地址凭据。

## 14. 启动与验证

### 14.1 推荐启动顺序

1. 确认 Conda 环境 `health` 和 Node.js 已安装；
2. 按需启动 Redis；
3. 启动 FastAPI 后端；
4. 启动 Vue 前端；
5. 按需启动独立 Vision Service、摄像头运行时和 Flutter 客户端；
6. 执行健康检查和 smoke 测试。

后端：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_server.ps1 -CondaEnv health
```

前端：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_frontend.ps1
```

Redis（Docker Desktop 已启动时）：

```powershell
docker compose -f .\docker\docker-compose.yml up -d redis
```

### 14.2 最小验收

```powershell
Invoke-WebRequest http://127.0.0.1:8000/healthz
Invoke-WebRequest http://127.0.0.1:8000/api/v1/system/info
Invoke-WebRequest http://127.0.0.1:5173/
powershell -ExecutionPolicy Bypass -File .\scripts\smoke_backend_http.ps1
```

如果需要验证视觉联调，再检查：

```text
GET /api/v1/video-bridge/status
GET /api/v1/vision/health
GET /api/v1/vision/results/latest?camera_id=camera_01
```

## 15. 演示建议

推荐演示顺序：

1. 登录社区端，展示社区总览和风险老人；
2. 展示成员、设备登记和关系拓扑；
3. 打开设备实时健康数据与趋势；
4. 触发或回放 SOS，展示秒级告警和确认闭环；
5. 展示窗口分析识别隐性异常；
6. 展示智能体生成社区态势、处置建议和报告；
7. 展示康伴智能体融合健康和天气生成受约束动作计划，并说明当前禁止执行；
8. 展示 Go2 工作台的任务、能力状态与跟随请求安全语义；
9. 在视觉服务已经单独验证可用时，再展示跌倒检测联动；
10. 最后展示家属端或 Flutter 多端同步。

比赛现场优先保证主系统、数据展示和告警主链路稳定。Vision Service、语音和外部模型属于可选增强能力，应准备不可用时的降级讲解，不应在未做健康检查时直接进入演示。

## 16. 当前限制与安全风险

1. **接口鉴权覆盖不完整**：部分设备读取、健康数据、告警确认、摄像头配置和 Vision 运行配置接口当前未统一保护。
2. **演示账号暴露**：`/auth/mock-accounts` 会返回演示账号和默认密码信息，只适用于开发/比赛环境。
3. **默认密钥风险**：配置中存在开发默认 `JWT_SECRET`，生产环境必须替换。
4. **CORS 较宽松**：当前允许任意来源，生产环境应限制可信前端域名。
5. **实时状态单进程**：WebSocket、告警队列和部分会话/缓存为进程内状态，不支持无改造的多实例一致性。
6. **移动推送仍为模拟记录**：尚不能视为完整的厂商推送交付链路。
7. **外部能力依赖配置**：Vision、Qwen/DashScope、Ollama、ASR/TTS/Omni 路由存在，不代表运行时一定已配置成功。
8. **Demo 与正式数据并存**：目录和账号保留兼容回退，正式部署应明确关闭演示入口和自动种子数据。
9. **数据库口径并存**：本地默认 SQLite，Docker/Schema 预留 PostgreSQL/TimescaleDB；上线前必须确认唯一的数据真相源和迁移方案。
10. **接口兼容入口较多**：用户注册、设备分析和视觉代理存在兼容/包装接口，客户端应选择一个标准入口，避免重复调用。
11. **视频模拟接口未启用**：`/api/v1/video-bridge/simulate-fall-alarm` 当前固定返回 501。
12. **医疗边界**：系统输出是健康风险提示和辅助建议，不构成医学诊断或紧急医疗替代方案。
13. **康伴动作禁止执行**：当前 Action Plan 仅用于决策展示，不能解释为 Go2 已接收或执行动作。
14. **跟随能力尚未闭环**：页面只登记本地跟随请求，真实 follow 仍缺少完整能力契约、距离限制、丢失处理、障碍处理、电量约束和紧急停止闭环。

## 17. 联调检查清单

### 主系统基础

- [ ] `/healthz` 返回主系统身份；
- [ ] `/api/v1/system/info` 中运行模式符合预期；
- [ ] 前端能访问后端，且没有端口或 CORS 错误；
- [ ] 登录后 `/api/v1/auth/me` 能恢复同一用户；
- [ ] 用户角色与页面范围一致。

### 设备与健康数据

- [ ] 设备已登记且 MAC 一致；
- [ ] 设备已绑定到正确老人；
- [ ] 串口目标与实际佩戴设备一致；
- [ ] `/health/realtime/{mac}` 能返回有效样本；
- [ ] `/ws/health/{mac}` 持续收到数据；
- [ ] 全零或无效数据不会触发误告警。

### 告警

- [ ] SOS 或异常能生成告警；
- [ ] `/ws/alarms` 能收到告警和队列快照；
- [ ] 告警确认后队列同步变化；
- [ ] 同一次 SOS/跌倒不会重复弹窗；
- [ ] 家属访问范围不会显示无关设备。

### Vision Service

- [ ] 已通过接口特征区分主系统与 Vision Service；
- [ ] 主系统配置的 `base_url` 指向真实 Vision Service；
- [ ] `/api/v1/vision/health` 不超时；
- [ ] `/api/v1/vision/results/latest` 能取得真实视觉结果；
- [ ] 跌倒事件含稳定的 `incident_id`；
- [ ] 推送 Token 或来源 IP 校验通过；
- [ ] 主系统产生 `alarm_id` 并推送到客户端。

### 智能体与报告

- [ ] `/chat/capabilities` 显示目标模型可用；
- [ ] RAG 知识库加载正常；
- [ ] 分析使用正确设备/老人/社区范围；
- [ ] 报告中的数值可追溯到真实接口数据；
- [ ] 模型不可用时前端能显示明确错误或降级结果。

### 康伴智能体与 Go2

- [ ] `/api/v1/robot-agent/dialogue` 返回健康、天气、动作计划和安全状态；
- [ ] QWeather 不可用时能自动回退 Mock；
- [ ] 康伴动作计划保持 `enabled=false` 和 `not_executed`；
- [ ] `/api/v1/robot/status` 与机器人工作台的能力状态口径一致；
- [ ] 跟随页面明确显示请求未发送至机器人；
- [ ] 机器人运动必须经过能力检查、安全联锁和 Robot Gateway。

## 18. 相关文档

- `README.md`：项目概览和后端能力；
- `setup.md`：Windows 本地部署与启动；
- `docs/architecture.md`：总体架构和设备管理口径；
- `docs/main-system-video-bridge-integration.md`：主系统与独立视觉服务桥接；
- `docs/codex-debug-rules.md`：主系统与 Vision Service 身份确认规则；
- `docs/system_startup_and_recovery_manual.md`：启动、恢复和视频联调；
- `docs/demo-script.md`：比赛演示脚本；
- `docs/VOICE_ARCHITECTURE.md`：语音能力架构；
- `docs/robot_companion_agent_contract.md`：康伴智能体、天气 Provider、动作计划和安全边界；
- `docs/go2_companion_voice_loop.md`：Go2 小康 ASR、Qwen 对话、TTS 闭环和硬件播放边界；
- `docs/robot_task_contract.md`：机器人任务和回调契约；
- `docs/robot_navigation_frontend_contract.md`：机器人导航前端契约；
- `docs/robot_emergency_workflow_contract.md`：机器人应急处置流程；
- `docs/knowledge-base/`：智能体 RAG 知识文档；
- `PROJECT_SUMMARY_FOR_CHATGPT.md`：项目全量上下文总结。

## 19. 文档维护规则

发生以下变化时必须更新本文：

- 新增、删除或修改 REST/WebSocket 接口；
- 请求字段、返回字段、枚举、默认值或错误码变化；
- 角色权限和认证方式变化；
- 主系统与 Vision Service 的职责或桥接方式变化；
- 数据库、数据真相源或告警持久化方式变化；
- 演示主流程和默认启动方式变化。

更新接口时至少记录：接口地址、请求方式、请求字段、返回字段、新增/删除/修改字段、旧版本兼容性、前端影响、演示影响和测试方式。
