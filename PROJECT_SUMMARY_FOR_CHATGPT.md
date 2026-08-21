# 项目详细总结文稿

## 1. 项目一句话概述

本项目是一个面向智慧康养 / 养老社区场景的 AIoT 健康监测与预警平台，围绕老人手环、摄像头、移动端、社区端和智能体分析，实现生命体征采集、健康评分、SOS / 跌倒告警、家属关怀与社区运营看板。

系统服务对象包括社区管理人员、家属、老人和演示 / 调试人员，核心目标是在比赛和答辩演示场景下稳定展示“可穿戴设备 + 视觉检测 + AI 智能分析 + 多端联动”的智慧养老闭环。

## 2. 项目背景与业务目标

项目背景来自智慧养老、居家 / 社区康养和比赛演示场景。仓库中的 `README.md`、`setup.md`、`docs/` 以及前后端代码都表明，系统重点关注老人健康监测、异常预警、家属通知、社区值守和智能体辅助分析。

核心业务目标包括：

- 实时采集 T10 手环或模拟设备的心率、血氧、血压、体温、步数、电量、SOS 等数据。
- 对单点或时间窗口生命体征进行规则 + 模型融合评分，输出健康分、风险等级、异常标签和处置建议。
- 对 SOS、生命体征异常、智能异常、社区风险和视频跌倒事件生成告警，并通过 WebSocket 推送到前端。
- 支持社区端查看老人、家属、设备、告警、趋势、交接报告和关系拓扑。
- 支持家属 / 老人移动端查看绑定设备、健康指标、告警、报告、语音交互和视频关怀。
- 支持独立视觉服务或摄像头运行时接入主系统，将跌倒检测结果转成主系统告警。
- 支持 RAG / 智能体问答、社区报告、设备健康报告、语音 ASR / TTS / Omni 交互。

## 3. 用户角色与使用场景

### 社区管理员 / 社区工作人员

相关代码：

- `backend/models/user_model.py`
- `backend/api/care_api.py`
- `frontend/vue-dashboard/src/views/CommunityPage.vue`
- `frontend/vue-dashboard/src/views/CommunityAgentPage.vue`
- `frontend/vue-dashboard/src/views/MemberDevicePage.vue`

主要能力：

- 登录社区端账号，例如演示账号 `community_admin`。
- 查看社区总览、老人风险排序、设备状态、最近告警、趋势图、关系拓扑。
- 管理成员与设备，包括老人注册、设备登记、设备绑定 / 解绑、绑定历史。
- 查看社区智能体工作台，按社区或老人维度生成分析、风险排序、告警摘要、报告。
- 访问调试入口、模拟告警、查看视频桥接 / 摄像头状态。

典型流程：

1. 登录社区端。
2. 进入总览页查看高风险老人和未确认告警。
3. 点击老人 / 设备查看实时体征和历史趋势。
4. 在成员设备页登记手环并绑定老人。
5. 进入智能体页生成社区日报、老人报告或处置建议。

### 家属用户

相关代码：

- `frontend/vue-dashboard/src/views/FamilyPage.vue`
- `mobile/flutter_app/lib/features/care/screens/family_home_screen.dart`
- `backend/api/care_api.py`

主要能力：

- 登录家属账号，例如 `family01`、`family02` 等演示账号。
- 仅查看与自己关联老人相关的数据。
- 查看老人实时健康指标、趋势、风险建议、告警、健康报告。
- 接收或查看移动端推送记录。
- 使用语音 / 智能体关怀功能。

典型流程：

1. 登录家属端。
2. 查看绑定老人健康状态。
3. 如有 SOS 或异常告警，查看告警详情并处理。
4. 查看历史趋势或健康报告。

### 老人用户

相关代码：

- `backend/api/auth_api.py`
- `backend/api/device_api.py`
- `mobile/flutter_app/lib/features/care/screens/elder_home_screen.dart`

主要能力：

- 老人账号可登录移动端。
- 查看自己的基础健康建议和绑定状态。
- 自助绑定 / 解绑真实串口设备。
- 使用语音助手进行健康问答。
- 触发手环 SOS 后由系统通知社区 / 家属。

根据当前代码推测，老人端在 Web 前端中的入口较弱，主要由 Flutter 移动端承载。

### 调试 / 演示人员

相关代码：

- `frontend/vue-dashboard/src/views/DebugPage.vue`
- `scripts/diagnostics/`
- `tests/`

主要能力：

- 启动 mock 数据、串口采集、摄像头、视觉桥接等演示链路。
- 查看系统状态、数据源、WebSocket、摄像头流、视频桥接状态。
- 运行诊断脚本和测试脚本。

## 4. 核心功能模块

### 4.1 设备接入与绑定模块

主要功能：

- 设备注册、查询、删除。
- 设备绑定老人、解绑、重新绑定。
- 老人自助绑定 / 解绑。
- 串口采集目标切换。
- 绑定日志记录。
- 支持 `serial`、`mqtt`、`ble`、`mock` 多种接入模式。

相关位置：

- `backend/api/device_api.py`
- `backend/services/device_service.py`
- `backend/models/device_model.py`
- `backend/models/device_bind_model.py`
- `frontend/vue-dashboard/src/views/MemberDevicePage.vue`

与其他模块关系：

- 设备绑定关系决定健康数据归属。
- 串口采集只会把数据写入已注册 / 已绑定的有效设备链路。
- 社区看板、家属端、告警和智能体分析都依赖设备与老人关系。

### 4.2 健康数据采集与实时推送模块

主要功能：

- 接收 `HealthSample` 样本。
- 支持 mock 数据循环、串口读取、MQTT 读取、演示 overlay 数据。
- 过滤无效样本。
- 合并串口 A / B 包或用上一时刻数据补齐缺失字段。
- 持久化样本、刷新聚合统计、广播 WebSocket。

相关位置：

- `backend/main.py`
- `backend/api/health_api.py`
- `backend/models/health_model.py`
- `backend/services/health_data_repository.py`
- `iot/serial_reader.py`
- `iot/mqtt_listener.py`
- `frontend/vue-dashboard/src/composables/useDeviceTrend.ts`

主要接口：

- `POST /api/v1/health/ingest`
- `GET /api/v1/health/realtime/{device_mac}`
- `GET /api/v1/health/trend/{device_mac}`
- `WS /ws/health/{device_mac}`

### 4.3 健康评分与预警模块

主要功能：

- 对心率、血氧、血压、体温、跌倒标志、数据准确率进行评分。
- 使用规则引擎 + PyTorch MLP 模型融合。
- 支持硬阈值升级，如血氧低、心率极端、血压高、体温高、跌倒。
- 使用稳定化服务处理短期抖动，输出 `stabilized_vitals`、`active_events` 和 `score_adjustment_reason`。
- 支持单点评分和窗口预警。

相关位置：

- `backend/api/health_api.py`
- `backend/services/health_score_service.py`
- `backend/services/warning_service.py`
- `backend/services/health_stability_service.py`
- `backend/ml/inference.py`
- `backend/ml/rule_engine.py`
- `backend/models/static_health_model.py`

主要接口：

- `POST /api/v1/health/score`
- `POST /api/v1/health/warning/check`

### 4.4 告警与通知模块

主要功能：

- 根据实时样本生成 SOS、生命体征异常、智能异常、社区风险、设备状态、跌倒类告警。
- 告警进入优先级队列。
- 支持确认 / 消警。
- SOS 有去重、持续按键抑制和确认后冷却逻辑。
- 跌倒告警也有确认后短冷却逻辑。
- 生成移动端推送记录。
- WebSocket 广播告警和队列快照。

相关位置：

- `backend/api/alarm_api.py`
- `backend/services/alarm_service.py`
- `backend/models/alarm_model.py`
- `backend/services/alarm_priority_queue.py`
- `backend/services/notification_service.py`
- `frontend/vue-dashboard/src/components/layout/CommunitySosOverlay.vue`
- `frontend/vue-dashboard/src/components/layout/FallAlertOverlay.vue`

主要接口：

- `GET /api/v1/alarms`
- `GET /api/v1/alarms/queue`
- `GET /api/v1/alarms/queue/snapshot`
- `GET /api/v1/alarms/mobile-pushes`
- `POST /api/v1/alarms/{alarm_id}/acknowledge`
- `WS /ws/alarms`

### 4.5 社区看板与关系拓扑模块

主要功能：

- 社区、老人、家属、设备目录。
- 社区总览指标：老人数量、家属数量、设备在线 / 离线 / 待激活、告警数量、高风险老人、平均健康分、平均血氧等。
- 风险老人排序。
- 最近告警列表。
- 12 小时趋势。
- 老人 - 家属 - 设备关系拓扑。
- 家属 / 老人访问权限视图。

相关位置：

- `backend/api/care_api.py`
- `backend/services/care_service.py`
- `backend/models/care_model.py`
- `frontend/vue-dashboard/src/views/CommunityPage.vue`
- `frontend/vue-dashboard/src/views/CommunityTopologyPage.vue`
- `frontend/vue-dashboard/src/composables/useCommunityDashboard.ts`

主要接口：

- `GET /api/v1/care/directory`
- `GET /api/v1/care/directory/family/{family_id}`
- `GET /api/v1/care/access-profile/me`
- `GET /api/v1/care/community/dashboard`

### 4.6 智能体分析、RAG 与报告模块

主要功能：

- 设备级健康分析。
- 社区级分析。
- 流式智能体输出。
- 社区报告、老人报告、设备健康报告。
- 工具调用轨迹、图表附件、报告附件、引用来源。
- 本地知识库检索，支持 Chroma、BM25、重排和降级。
- 根据配置使用 Qwen / DashScope、Ollama 或本地模型路由。

相关位置：

- `backend/api/chat_api.py`
- `backend/api/agent_api.py`
- `agent/agent_service.py`
- `agent/community_langgraph_agent.py`
- `agent/langchain_rag_service.py`
- `agent/rag_service.py`
- `backend/services/community_insight_service.py`
- `frontend/vue-dashboard/src/views/CommunityAgentPage.vue`
- `frontend/vue-dashboard/src/composables/useCommunityAgentWorkbench.ts`
- `docs/knowledge-base/`

主要接口：

- `POST /api/v1/chat/analyze`
- `POST /api/v1/chat/analyze/device`
- `POST /api/v1/chat/analyze/device/stream`
- `POST /api/v1/chat/analyze/community`
- `POST /api/v1/chat/analyze/community/stream`
- `POST /api/v1/chat/report/device`
- `GET /api/v1/chat/capabilities`
- `POST /api/v1/agent/community/summary`
- `POST /api/v1/agent/health/explain`
- `GET /api/v1/agent/elders`

### 4.7 摄像头、视觉服务与跌倒检测桥接模块

主要功能：

- 本地摄像头状态、快照、MJPEG 流、处理后帧、音频状态。
- 摄像头源注册与切换。
- 独立 Vision Service 桥接。
- 轮询 Vision Service 的健康状态、数据源、最新识别结果。
- 接收跌倒事件，将事件提升为主系统告警。
- 目标用户识别、外部摄像头配置、本地姿态检测、跌倒检测接口。
- `fall_detection_model_bundle` 中包含训练、评估、实时监控、模型权重与 v3 升级实验。

相关位置：

- `backend/api/camera_api.py`
- `backend/api/camera_source_api.py`
- `backend/api/video_bridge_api.py`
- `backend/services/video_bridge_service.py`
- `backend/api/vision_api.py`
- `backend/api/target_user_api.py`
- `fall_detection_model_bundle/`
- `pose_detection_model_bundle/`
- `frontend/vue-dashboard/src/views/VideoBridgePage.vue`

主要接口：

- `GET /api/v1/camera/*`
- `GET /api/v1/camera-sources/*`
- `GET /api/v1/vision/health`
- `GET /api/v1/vision/results/latest`
- `POST /api/v1/video-bridge/fall-events`
- `POST /api/v1/video-bridge/vision/poll-once`
- `PATCH /api/v1/video-bridge/runtime-config`
- `WS /ws/camera`
- `WS /ws/camera/processed`
- `WS /ws/camera/audio/listen`

### 4.8 语音、ASR、TTS 与 Omni 模块

主要功能：

- 上传音频做 ASR。
- 文本转语音。
- 音频 + 文本 + 健康上下文的 Omni 分析。
- 面向老人角色时强调温和、简短、基于已有数据，不虚构测量值。
- 使用 DashScope / Qwen 兼容 OpenAI API。

相关位置：

- `backend/api/voice_api.py`
- `backend/api/omni_api.py`
- `backend/services/voice_service.py`
- `mobile/flutter_app/lib/features/voice/`

主要接口：

- `POST /api/v1/voice/asr`
- `POST /api/v1/voice/tts`
- `GET /api/v1/voice/status`
- `POST /api/v1/omni/analyze`
- `GET /api/v1/omni/status`

### 4.9 移动端模块

主要功能：

- Flutter 多端应用。
- 登录、注册、会话管理。
- 家属首页、老人首页、设备详情、历史数据、告警中心。
- 智能体、语音、视频连接调试。
- 本地服务器地址配置。

相关位置：

- `mobile/flutter_app/lib/main.dart`
- `mobile/flutter_app/lib/core/network/api_client.dart`
- `mobile/flutter_app/lib/features/auth/`
- `mobile/flutter_app/lib/features/care/`
- `mobile/flutter_app/lib/features/health/`
- `mobile/flutter_app/lib/features/alarm/`
- `mobile/flutter_app/lib/features/agent/`
- `mobile/flutter_app/lib/features/voice/`

## 5. 技术栈与运行环境

### 后端

- Python 3.11，`pyproject.toml` 要求 `>=3.11`。
- FastAPI + Uvicorn。
- Pydantic v2 / pydantic-settings。
- SQLite 默认本地持久化，配置项 `database_url` 默认为 `sqlite+aiosqlite:///data/app.db`。
- Docker Compose 中预留 PostgreSQL 15 / TimescaleDB。
- Redis 用于基础服务预留，当前代码中主要实时状态仍多为内存 + SQLite。
- PyTorch + scikit-learn + joblib 用于健康评分模型。
- Ultralytics / OpenCV / ONNX Runtime 用于视觉和跌倒检测相关能力。
- LangChain、LangGraph、ChromaDB、Ollama、OpenAI SDK、DashScope 用于智能体、RAG 和语音 / 大模型服务。

### 前端

- Vue 3 + Vite + TypeScript。
- 无 Vue Router，使用自定义 hash 路由。
- ECharts 用于图表。
- `lucide-vue-next` 用于图标。
- `html2canvas` + `jspdf` 用于报告导出。
- Tailwind / PostCSS 存在配置，但主要样式看起来以自定义 CSS 为主。

### 移动端

- Flutter。
- 支持 Android、iOS、Web、Windows、macOS、Linux 工程结构。
- 包含健康、告警、关怀、智能体、语音、设置等 feature 分层。

### 数据库

- 本地开发默认 SQLite。
- Docker 环境预留 TimescaleDB schema。
- `database/schema.sql` 定义了 PostgreSQL / TimescaleDB 表结构，包括用户、设备、关系、健康数据、告警、聚合表等。

### 部署

- 本地推荐：后端 FastAPI + 前端 Vite + Redis。
- Docker：`docker/Dockerfile`、`docker/docker-compose.yml` 提供 backend、postgres、redis、chromadb、ollama。
- 需要注意：Dockerfile 只安装了 `fastapi uvicorn pydantic pydantic-settings`，与完整 `requirements.txt` 不一致，根据当前代码推测 Docker 后端镜像可能无法运行完整功能。

## 6. 项目目录结构说明

| 路径 | 作用 |
|---|---|
| `backend/` | FastAPI 后端主体，包含 API、模型、服务、仓储、ML 推理、配置。 |
| `frontend/vue-dashboard/` | Vue 社区端 / 家属端 Web 前端。 |
| `mobile/flutter_app/` | Flutter 移动端应用。 |
| `agent/` | 智能体、RAG、LangGraph、分析服务、提示词和模型接口。 |
| `iot/` | 串口和 MQTT 采集适配。 |
| `database/schema.sql` | PostgreSQL / TimescaleDB 初始化 schema。 |
| `docker/` | Dockerfile 和 docker-compose。 |
| `docs/` | 项目文档、部署说明、摄像头 / 手环 / 比赛 / 模型 / 演示文档、知识库。 |
| `docs/knowledge-base/` | RAG 知识库 Markdown 文档。 |
| `fall_detection_model_bundle/` | 跌倒检测模型、脚本、权重、训练评估、runtime bridge。 |
| `pose_detection_model_bundle/` | 姿态检测模型配置和实时检测脚本。 |
| `scripts/` | 启动、训练、诊断、模型调优、摄像头和手环排查脚本。 |
| `tests/` | 后端单元测试和接口测试。 |
| `data/` | 本地 SQLite、模型 artifacts、Chroma、运行数据等，具体内容依赖本地运行状态。 |
| `configs/` | LLM 微调、LLaMA Factory 等配置。 |

## 7. 前端架构说明

前端入口是 `frontend/vue-dashboard/src/main.ts`，挂载 `frontend/vue-dashboard/src/App.vue`。`App.vue` 负责：

- 调用 `useSessionAuth` 恢复或创建登录会话。
- 调用 `useHashRouting` 做页面路由。
- 登录前显示 `LoginPage`。
- 登录后显示 `AppShell`，再按 `activePage` 渲染页面。

路由设计：

- `#/overview`：社区总览。
- `#/topology`：社区关系拓扑。
- `#/members`：成员与设备。
- `#/agent`：社区智能体工作台。
- `#/family`：家属端。
- `#/debug`：调试页，仅社区 / admin 可访问。

角色控制：

- `family` 只能访问 `family`。
- `community` / `admin` 可访问 `overview`、`topology`、`members`、`agent`，debug 入口另行判断。
- `elder` 在 Web 前端中没有明显主页面，仓库中更偏向移动端承载老人视图。

接口调用：

- `frontend/vue-dashboard/src/api/client.ts` 集中定义 TypeScript 类型和 API 方法。
- 默认 `VITE_API_BASE` 为 `http://localhost:8000/api/v1`。
- 默认 `VITE_WS_BASE` 为 `ws://localhost:8000`。
- WebSocket 包括 `healthSocket(mac)` 和 `alarmSocket()`。

状态管理：

- 没有 Pinia / Vuex。
- 主要使用 Composition API composables，例如 `useSessionAuth`、`useHashRouting`、`useCommunityDashboard`、`useCommunityWorkspace`、`useCommunityAgentWorkbench`、`useDeviceTrend`、`useCareDirectoryDashboard`、`useRelationActions`、`useReportExport`。

主要页面：

- `LoginPage.vue` / `auth/AuthLoginPage.vue`：登录和注册入口。
- `CommunityPage.vue`：社区总览。
- `CommunityTopologyPage.vue`：关系拓扑。
- `MemberDevicePage.vue`：老人、家属、设备登记和绑定管理。
- `CommunityAgentPage.vue`：智能体分析。
- `FamilyPage.vue`：家属关怀。
- `DebugPage.vue`：调试页。
- `VideoBridgePage.vue`：视频桥接页。

## 8. 后端架构说明

后端入口是 `backend/main.py`。架构特点：

- FastAPI 应用统一挂载多个 `APIRouter`，全局前缀默认为 `/api/v1`。
- lifespan 启动后台任务：mock 数据流、demo overlay 数据流、串口采集流、MQTT 采集流、Vision Service 轮询。
- 提供系统信息接口和多个 WebSocket 通道。

后端大致分层：

- `backend/api/`：HTTP 路由层。
- `backend/models/`：Pydantic 业务模型和 PyTorch 模型定义。
- `backend/schemas/`：健康评分、预警、解释等 API schema。
- `backend/services/`：核心业务服务。
- `backend/repositories/`：SQLite 持久化仓储。
- `backend/ml/`：预处理、特征工程、规则、推理、训练。
- `agent/`：智能体与 RAG 逻辑。
- `iot/`：设备采集适配。

权限认证：

- 当前实现为服务内存 session token。
- 登录后返回 token，前端放入 localStorage。
- 后续请求使用 `Authorization: Bearer <token>`。
- 写操作通过 `require_write_session_user` 或 `require_session_user` 检查角色。
- 不是 JWT，没有发现真实 RBAC 中间件或统一鉴权依赖注入。

异常处理：

- 多数 API 捕获 `ValueError` 或业务 `ServiceError`，转换为 HTTP 状态码。
- 健康评分接口使用统一 envelope：`code/message/data`。
- 部分接口直接返回模型或 dict。

## 9. 数据库与数据模型

### PostgreSQL / TimescaleDB schema

相关文件：`database/schema.sql`

核心表：

- `users`：用户基础信息，字段包括 `id`、`name`、`role`、`phone`、`password_hash`、`created_at`。
- `devices`：设备表，字段包括 `mac_address`、`device_name`、`model_code`、`ingest_mode`、`user_id`、`status`、`activation_state`、`bind_status`、`last_seen_at`。
- `family_relations`：老人和家属关系。
- `device_bind_logs`：设备绑定 / 解绑 / 重绑日志。
- `health_data`：健康数据 hypertable，字段包括心率、体温、血氧、血压、电量、SOS。
- `sensor_samples`：更完整的传感器样本表，包含步数、设备 UUID、环境温度、表面温度、包类型、原始 A / B 包、异常分、健康分。
- `alarms`：基础告警表。
- `health_scores`：健康评分结果表。
- `alert_events`：结构化告警事件。
- `device_status_history`：设备状态变化历史。
- `sensor_hourly_rollups` / `sensor_daily_rollups`：小时 / 日聚合。

### 本地 SQLite

当前后端服务中，`DeviceService`、`HealthDataRepository`、`ScoreRepository`、`WarningRepository` 等更实际地使用 SQLite，默认路径来自 `backend/config.py` 的 `database_url`。

根据当前代码判断，比赛 / 本地演示默认更偏 SQLite；PostgreSQL / TimescaleDB schema 是部署或后续扩展预留。

### Pydantic 核心模型

- `HealthSample`：实时样本。
- `DeviceRecord`：设备记录。
- `AlarmRecord`：告警记录。
- `CareDirectory`：社区、老人、家属目录。
- `CommunityDashboardSummary`：社区看板汇总。
- `HealthScoreResponse`：健康评分结果。
- `VideoAnalysisPushRequest` / `VideoBridgeFallEventRequest`：视觉桥接数据。
- `AgentDeviceHealthReport`：智能体设备健康报告。

## 10. 接口与数据流转

### 用户登录流程

1. 前端调用 `POST /api/v1/auth/login`。
2. 后端 `CareService.login` 先尝试正式用户，再尝试 demo 用户。
3. 登录成功后返回 `token`、`user`、`expires_at`。
4. 前端保存 token 到 localStorage。
5. 后续调用 `/auth/me` 恢复登录状态。

相关文件：

- `backend/api/auth_api.py`
- `backend/services/care_service.py`
- `frontend/vue-dashboard/src/composables/useSessionAuth.ts`

### 设备绑定流程

1. 社区端或老人端提交设备 MAC、设备名、接入方式、目标老人。
2. 后端校验 MAC 格式、设备是否存在、目标用户是否存在、是否已有同型号设备。
3. 注册或绑定设备。
4. 若是串口设备，可能设置为 active serial target。
5. 写入绑定日志。
6. 社区看板和家属端通过目录 / 设备接口看到更新。

### 健康数据采集流程

1. 样本来自 mock 循环、串口、MQTT 或前端 / 外部 `POST /health/ingest`。
2. `ingest_sample` 检查设备是否存在，更新在线状态。
3. 对缺失字段尝试用上一时刻样本补齐。
4. 无效样本被丢弃，不进入告警评估。
5. 实时告警优先评估并广播。
6. 计算健康分，持久化样本，刷新 rollup。
7. 通过 `WS /ws/health/{device_mac}` 推送给前端。
8. 智能异常和社区风险按窗口补充生成告警。

### 报警触发流程

1. `AlarmService.evaluate` 根据样本生成告警。
2. 告警进入优先级队列。
3. SOS 按设备和时间窗口去重。
4. 告警持久化，并通过 `WS /ws/alarms` 广播。
5. 前端弹出 SOS / 跌倒 overlay 或更新告警面板。
6. 用户确认告警后，后端标记 acknowledged 并广播队列快照。

### 跌倒检测流程

1. 独立视觉服务推送 `POST /api/v1/video-bridge/fall-events`，或主系统轮询 Vision Service 最新结果。
2. `VideoBridgeService` 规范化事件，判断是否可提升为告警。
3. `_ingest_video_bridge_alarm_event` 构造 `AlarmRecord`。
4. 告警进入主系统告警服务，与 SOS / 健康异常共用队列和 WebSocket。
5. 前端显示跌倒告警 overlay。

## 11. AI / 智能体 / 模型相关功能

### 健康评分模型

使用：

- PyTorch MLP 多任务模型：`StaticHealthMultiTaskModel`。
- 输入：心率、血氧、收缩压、舒张压、体温、跌倒标志、数据准确率及派生特征。
- 输出：健康分、风险原始分、心率 / 血氧 / 血压 / 体温告警概率。
- 与规则引擎融合后输出最终健康分和风险等级。

相关位置：

- `backend/models/static_health_model.py`
- `backend/ml/inference.py`
- `backend/ml/feature_engineering.py`
- `scripts/train_static_model.py`

### 规则引擎

使用硬阈值和子项评分，支持解释性标签：

- `tachycardia`
- `bradycardia`
- `low_spo2`
- `hypertension`
- `fever`
- `fall_detected`
- `poor_signal_quality`

相关位置：`backend/ml/rule_engine.py`

### RAG 与智能体

使用：

- LangChain / LangGraph。
- ChromaDB、本地知识库、BM25、可选重排。
- Qwen / DashScope、Ollama、本地模型路由。
- 社区智能体可以输出流式阶段、工具调用、附件、引用和报告。

相关位置：

- `agent/`
- `docs/knowledge-base/`
- `backend/api/chat_api.py`
- `backend/services/community_insight_service.py`

当前实现判断：

- RAG、智能体流式接口和测试已存在。
- 真实外部 LLM 是否可用取决于 `.env` 中 `QWEN_API_KEY` / `DASHSCOPE_API_KEY` / Ollama 等配置。
- 如果没有配置，系统会返回降级说明或使用确定性分析结果。

### 语音与多模态

使用：

- DashScope ASR。
- Qwen TTS / CosyVoice 兼容逻辑。
- Qwen Omni 兼容 OpenAI API。
- 输入：音频、文本 prompt、角色、设备 MAC。
- 输出：文本回答、可选音频 base64 / audio URL。

相关位置：

- `backend/services/voice_service.py`
- `backend/api/voice_api.py`
- `backend/api/omni_api.py`

### 视觉与跌倒检测

使用：

- YOLO / pose / TCN / GRU / hybrid transformer 等模型资产和脚本。
- 主系统通过 Video Bridge 接收外部视觉服务结果。
- `fall_detection_model_bundle/` 中有多版训练、评估和 runtime bridge。

当前实现是否完整：

- 主系统桥接和告警接入较完整，有测试覆盖。
- 视觉模型训练 / 替换链路较庞大，部分像 v3 upgrade lab 是实验 / 升级资产。
- 根据当前代码推测，比赛演示中主系统更依赖“外部 Vision Service + 桥接接口”，而不是所有视觉推理都在主后端直接完成。

## 12. 权限、认证与安全机制

已实现：

- 登录接口返回临时 token。
- token 存储在 `CareService` 内存 session。
- 前端 localStorage 保存 token。
- 后端通过 `Authorization: Bearer` 解析用户。
- 部分接口限制 community / admin，例如智能体老人列表、社区 dashboard。
- 写操作需要 writer 权限。
- 视频桥接 push 可配置 token 和来源校验。
- `.env.example` 提供配置示例，真实 `.env` 不应提交。

风险：

- 当前 session token 是内存态，服务重启即失效，不适合生产分布式部署。
- 密码哈希在 `UserService` 中使用 SHA256，未见 salt / bcrypt 应用于正式用户。
- CORS 当前 `allow_origins=["*"]`，生产环境风险较高。
- 部分接口没有统一鉴权，例如设备列表、告警列表等可能在演示场景下开放。
- `.env.example` 被 docker-compose 作为 env_file 使用，真实部署需要替换为安全配置。

## 13. 部署与启动方式

根据仓库文件，常见启动方式如下。

### 后端

推荐脚本：

```powershell
conda run -n helth powershell -ExecutionPolicy Bypass -File .\scripts\start_server.ps1
```

备用：

```powershell
conda run -n helth python .\scripts\run_server.py
```

或：

```powershell
conda run -n helth python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

健康检查：

```powershell
curl http://127.0.0.1:8000/healthz
```

### 前端

推荐脚本：

```powershell
conda run -n helth powershell -ExecutionPolicy Bypass -File .\scripts\start_frontend.ps1
```

手动：

```powershell
cd frontend\vue-dashboard
npm install
npm run dev
```

### Redis

```powershell
cd docker
docker compose up -d redis
```

### Docker Compose

```powershell
cd docker
docker compose up -d
```

注意：`docker-compose.yml` 会启动 backend、postgres、redis、chromadb、ollama。但 Dockerfile 依赖明显少于 `requirements.txt`，完整功能可能不可用。

### 移动端

```powershell
cd mobile\flutter_app
flutter run
```

## 14. 当前项目完成度判断

### 已完成

- FastAPI 主服务结构和多模块路由。
- Vue 社区 / 家属 Web 前端基本框架。
- 登录、demo 账号、session 恢复。
- 设备注册、绑定、解绑、绑定日志。
- 健康数据模型、实时查询、趋势查询。
- 健康评分、规则引擎、稳定化、窗口预警。
- SOS 告警去重、确认、队列、WebSocket 推送。
- 社区 dashboard、关系拓扑、家属访问视图。
- 智能体分析接口、流式输出、报告结构、RAG 测试。
- 视频桥接接口和跌倒告警接入。
- 语音 ASR / TTS / Omni API。
- 测试覆盖较多核心业务：评分、规则、告警、串口解析、设备绑定、RAG、视频桥接。

### 部分完成

- Docker 部署：配置存在，但镜像依赖不完整。
- PostgreSQL / TimescaleDB：schema 完整，但运行时默认更偏 SQLite。
- 真实 LLM / RAG：代码完整度较高，但依赖外部 API key、本地模型或 Chroma 状态。
- 视觉跌倒检测：主系统桥接成熟，完整视觉模型训练与替换流程仍像实验 / 升级体系。
- 权限体系：演示可用，但不是生产级认证授权。
- Flutter 移动端：目录和功能完整，但本次未逐文件验证所有页面运行状态。

### 未完成或待确认

- 生产级用户认证、密码安全、权限隔离。
- 完整部署文档与 Docker 镜像依赖一致性。
- PostgreSQL 与 SQLite 双存储之间的一致性策略。
- 真实手环、真实摄像头、真实 DashScope / Ollama 环境下的端到端验收。
- 前端部分中文在终端读取时出现编码异常，需在浏览器和源码编辑器中确认真实显示。
- 演示数据、正式数据、mock 数据之间的边界仍需文档化。

## 15. 当前代码中的明显问题与风险

1. 文档和源码中文在终端读取中出现编码显示异常
   可能是终端编码问题，也可能部分文件存在编码损坏。前端页面和错误文案需要浏览器确认。

2. Dockerfile 依赖不足
   `docker/Dockerfile` 只安装 FastAPI 基础依赖，但项目实际依赖 PyTorch、pandas、joblib、requests、dashscope、opencv、langchain 等大量包，完整服务在 Docker 中很可能启动后功能缺失。

3. SQLite 与 PostgreSQL schema 并存
   代码中大量服务直接使用 SQLite，本地默认配置也是 SQLite；`database/schema.sql` 是 PostgreSQL / TimescaleDB。需要明确生产数据源，否则容易出现“schema 有但代码没用”的维护风险。

4. 鉴权偏演示化
   token 内存存储、SHA256 密码哈希、CORS 全开放、部分查询接口无鉴权，适合比赛演示但不适合生产。

5. 业务模块较多，耦合度偏高
   `backend/dependencies.py` 和 `backend/main.py` 承载大量单例、启动任务、演示数据、摄像头、智能体和采集逻辑，后续维护容易互相影响。

6. 演示数据与正式数据混用风险
   代码支持 demo directory、formal users、mock devices、serial devices，并有特殊覆盖逻辑。演示稳定性强，但如果进入正式部署，需要严格隔离数据模式。

7. 前端无正式路由和全局状态框架
   当前用 hash routing + composables 足够演示，但页面继续扩展后，权限、缓存、错误边界和导航状态会更难维护。

8. 外部服务依赖较多
   Qwen / DashScope、Ollama、Chroma、Vision Service、串口采集器、摄像头运行时都可能影响演示，需要启动前检查脚本和降级策略。

## 16. 后续开发建议

1. 优先固化演示主流程
   明确“登录 -> 社区总览 -> 设备绑定 -> 实时数据 -> SOS / 跌倒告警 -> 智能体报告”的标准验收脚本，并保持每次修改后跑 smoke test。

2. 统一运行环境与依赖
   修正 Dockerfile，使其与 `requirements.txt` 或专门的 runtime requirements 对齐；明确 Python 版本、CUDA / CPU 版本、模型 artifacts 路径。

3. 明确数据源策略
   选择 SQLite 演示版或 PostgreSQL / TimescaleDB 正式版，并写清哪些 repository 使用哪种存储。

4. 强化认证和权限
   生产前建议引入 JWT 或服务端 session 存储、bcrypt / argon2、接口统一依赖鉴权、角色权限矩阵和 CORS 白名单。

5. 梳理 mock / demo / formal 数据边界
   把演示数据生成、真实设备接入、正式用户注册的边界写成文档，避免比赛现场误操作。

6. 拆分启动任务和依赖单例
   后续可将采集、摄像头、视觉轮询、智能体、告警队列拆成更清晰的 runtime manager。

7. 补齐接口文档
   对设备、健康、告警、社区、智能体、视频桥接、语音接口生成 OpenAPI 摘要或 Markdown 契约。

8. 做一次前端编码和 UI 文案检查
   重点检查中文是否乱码、按钮是否显示正常、移动端响应式是否稳定。

9. 增加端到端测试
   覆盖登录、设备绑定、样本 ingest、WebSocket 告警、确认告警、智能体流式输出、视频跌倒事件推送。

## 17. 给 ChatGPT 的压缩版项目上下文

这是一个智慧康养 / 养老社区 AIoT 健康监测与预警系统，面向比赛演示和真实联调场景。系统由 FastAPI 后端、Vue 3 Web 前端、Flutter 移动端、IoT 采集、AI 智能体、语音服务、摄像头 / 跌倒检测桥接组成。核心业务是采集老人手环数据，包括心率、血氧、血压、体温、步数、电量、SOS 等，通过规则引擎和 PyTorch MLP 模型融合计算健康评分，输出风险等级、异常标签、触发原因和建议动作，并将 SOS、生命体征异常、智能异常、社区风险、跌倒事件等统一生成告警，通过 WebSocket 推送到社区端和家属端。

后端入口是 `backend/main.py`，按 `/api/v1` 挂载 `devices`、`health`、`alarms`、`care`、`chat`、`agent`、`camera`、`video-bridge`、`vision`、`voice`、`omni` 等路由。设备模块支持注册、绑定、解绑、重绑和串口目标切换；健康模块支持样本写入、实时查询、趋势查询、评分和窗口预警；告警模块支持优先级队列、SOS 去重、确认和移动推送记录；care 模块构建社区、老人、家属、设备目录和社区 dashboard；chat / agent 模块支持社区 / 老人 / 设备智能分析、流式输出、RAG 知识检索、图表附件和报告；video-bridge 模块用于接入独立视觉服务，将确认跌倒事件转成主系统告警；voice / omni 模块通过 DashScope / Qwen 做 ASR、TTS 和音频多模态问答。

前端位于 `frontend/vue-dashboard`，是 Vue 3 + Vite + TypeScript 单页应用，不使用 Vue Router，而是 `useHashRouting` 管理 hash 路由。登录后按角色分流：family 只能进入家属页，community / admin 可进入社区总览、关系拓扑、成员设备、智能体工作台。API 集中在 `src/api/client.ts`，默认后端地址为 `http://localhost:8000/api/v1`，WebSocket 地址为 `ws://localhost:8000`。移动端位于 `mobile/flutter_app`，包含登录、家庭 / 老人首页、健康、历史、告警、智能体、语音和设置等模块。

数据层默认本地 SQLite，`backend/config.py` 默认 `database_url` 指向 `data/app.db`；同时 `database/schema.sql` 提供 PostgreSQL / TimescaleDB schema，包含 users、devices、family_relations、device_bind_logs、health_data、sensor_samples、alarms、health_scores、alert_events、rollups 等表。部署上支持本地 conda 环境、Vite 前端、Redis，以及 Docker Compose 中的 backend / postgres / redis / chromadb / ollama，但当前 Dockerfile 依赖明显不足，完整功能更适合按 `requirements.txt` 本地运行。项目已有较多测试，覆盖规则引擎、评分 API、串口解析、告警服务、设备绑定、RAG、Omni、视频桥接等。主要风险是认证偏演示化、CORS 全开放、SQLite 与 PostgreSQL 并存、Docker 依赖不完整、mock / demo / formal 数据边界复杂，以及部分中文文案在终端读取时出现编码异常，需浏览器确认。

## 18. 关键文件索引

| 文件路径 | 文件作用 | 为什么重要 |
|---|---|---|
| `README.md` | 项目概述、环境、核心接口和模型说明 | 理解业务目标和运行方式的第一入口 |
| `setup.md` | Windows 本地部署与启动说明 | 包含实际演示启动流程、账号和排障信息 |
| `pyproject.toml` | Python 项目元信息和 pytest 配置 | 明确 Python 版本和测试路径 |
| `requirements.txt` | 后端完整依赖 | 反映真实技术栈 |
| `backend/main.py` | FastAPI 入口、路由挂载、后台任务、WebSocket | 后端运行核心 |
| `backend/config.py` | 全局配置、模型、串口、LLM、视觉服务配置 | 决定运行模式和外部服务 |
| `backend/dependencies.py` | 服务单例、依赖注入、样本 ingest 核心逻辑 | 串联采集、评分、告警、持久化 |
| `backend/api/health_api.py` | 健康数据、评分、预警、趋势接口 | 核心业务 API |
| `backend/services/health_score_service.py` | 健康评分服务 | 规则、模型、稳定化融合的主入口 |
| `backend/ml/rule_engine.py` | 健康规则引擎 | 风险等级和解释性标签来源 |
| `backend/ml/inference.py` | PyTorch 模型推理 | 模型评分核心 |
| `backend/api/device_api.py` | 设备注册、绑定、解绑接口 | 设备归属和串口目标切换核心 |
| `backend/services/device_service.py` | 设备持久化和绑定逻辑 | 影响数据归属、演示和正式设备关系 |
| `backend/api/alarm_api.py` | 告警查询和确认接口 | 告警闭环入口 |
| `backend/services/alarm_service.py` | 告警去重、队列、确认、推送 | SOS / 跌倒告警稳定性核心 |
| `backend/api/care_api.py` | 社区目录、访问权限、dashboard | 社区端和家属端数据来源 |
| `backend/services/care_service.py` | demo / formal 用户目录、登录、会话 | 角色体系和演示账号核心 |
| `backend/api/chat_api.py` | 智能体问答、流式分析、报告接口 | AI 分析入口 |
| `agent/agent_service.py` | 智能体主服务 | 组织模型、工具、RAG、回答 |
| `agent/langchain_rag_service.py` | LangChain RAG 服务 | 知识库检索和引用来源 |
| `backend/api/video_bridge_api.py` | 视频桥接与跌倒事件接口 | 视觉服务接入主系统的入口 |
| `backend/services/video_bridge_service.py` | Vision Service 轮询、事件提升、运行时配置 | 跌倒检测联调核心 |
| `backend/api/voice_api.py` | ASR / TTS 接口 | 语音能力入口 |
| `backend/api/omni_api.py` | 音频多模态接口 | 老人语音问答入口 |
| `frontend/vue-dashboard/src/App.vue` | 前端根组件和页面分流 | Web 端导航核心 |
| `frontend/vue-dashboard/src/api/client.ts` | 前端 API 类型和请求封装 | 前后端契约集中处 |
| `frontend/vue-dashboard/src/composables/useHashRouting.ts` | hash 路由和角色访问控制 | 页面权限入口 |
| `frontend/vue-dashboard/src/views/CommunityPage.vue` | 社区总览页面 | 演示主页面之一 |
| `frontend/vue-dashboard/src/views/MemberDevicePage.vue` | 成员与设备管理页面 | 设备接入演示关键页面 |
| `frontend/vue-dashboard/src/views/CommunityAgentPage.vue` | 社区智能体页面 | AI 分析演示关键页面 |
| `database/schema.sql` | PostgreSQL / TimescaleDB schema | 数据库设计依据 |
| `docker/docker-compose.yml` | 容器编排 | 部署服务拓扑依据 |
| `mobile/flutter_app/lib/main.dart` | Flutter 应用入口 | 移动端入口 |
| `tests/test_health_api.py` | 健康评分接口测试 | 验证评分、稳定化、解释链路 |
| `tests/test_video_bridge_integration.py` | 视频桥接测试 | 验证跌倒事件转告警 |
| `tests/test_serial_parser.py` | 串口解析测试 | 验证手环数据解析 |

---

## 修改文件列表

- `PROJECT_SUMMARY_FOR_CHATGPT.md`

## 每个文件修改原因

- `PROJECT_SUMMARY_FOR_CHATGPT.md`：根据要求将项目详细总结文稿保存为可复制给 ChatGPT 的上下文文档。

## 是否新增依赖

否。

## 是否修改接口

否。仅新增文档，没有修改请求字段、返回字段或兼容性。

## 是否修改数据库

否。未修改数据库结构或初始化数据。

## 是否影响演示流程

否。本次仅新增 Markdown 文档，不影响比赛演示、答辩演示或 PPT 讲解流程。

## 测试命令

未执行测试命令。本次只新增文档，不涉及代码运行逻辑。

## 测试结果

未测试；原因是文档新增任务不需要运行项目测试。

## 尚未解决的问题

部分中文内容在终端读取中出现编码显示异常，是否为终端编码还是源文件真实乱码，需要在编辑器或浏览器中进一步确认。

## 建议 commit message

```text
docs(summary): 新增项目详细总结文稿
```
