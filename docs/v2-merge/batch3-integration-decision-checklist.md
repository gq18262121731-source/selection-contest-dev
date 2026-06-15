# Batch 3 Integration Decision Checklist

## 1. 当前阶段结论

- Batch 1 已完成并验证通过。
  - 提交：`9109511`
  - 范围：文档、知识库、`fall_detection` 配置、`camera_runtime_external` 文档、`target-user-console`
- Batch 2 已完成并验证通过。
  - 提交：`b0222fd`
  - 范围：诊断脚本、训练/评估/导入导出脚本、`fall pose` 相关模块、`frame worker`、`VideoBridgePage`
- Batch 2 Fix 已完成并验证通过。
  - 提交：`2915260`
  - 范围：`scripts/quick_diagnose.py`、`scripts/train_fall_pose_sequence.py`
- `temp69-batch2-verified` 是当前稳定停靠点。
- 当前阶段的低风险高价值内容已迁入并验证通过，但尚未进入主接线层集成。
- 第三批不应继续盲目迁移文件，而应进入可观测、可回退、可关闭的旁路集成阶段。

## 2. P0 决策项

- Fall 新链路：
  - 默认作为实验/备用链路保留。
  - 不替换当前运行中的现有跌倒检测链路。
- Video Bridge：
  - 默认作为预埋接口和占位页面保留。
  - 不接 RTSP。
  - 不接 YOLO。
  - 不接 `FallStateMachine`。
  - 不接现有告警主链路。
- 摄像头真相源：
  - 第三批前必须先验证统一。
  - 必须优先遵守 `camera-current-source-of-truth.md` 中的单一真相源规则。
- 第三批目标：
  - 只做最小旁路接通。
  - 不做架构替换。

## 3. P1 待融合模块

### 后端主接线层

- `backend/main.py`
- `backend/dependencies.py`
- `backend/config.py`

### 前端主接线层

- `frontend/vue-dashboard/src/api/client.ts`
- 路由接线层
- 导航接线层
- 壳层布局接线层

### 移动端主入口

- `mobile/flutter_app/lib/main.dart`

### Fall 新模块

- `backend/models/fall_pose_tcn_model.py`
- `backend/services/fall_event_catalog_service.py`
- `backend/services/fall_event_state_machine.py`
- `backend/services/fall_pose_sequence_service.py`
- `backend/services/fall_response_knowledge_service.py`
- `backend/services/frame_analysis_worker_service.py`
- `backend/services/pose_detection_config_service.py`
- `backend/workers/frame_analysis_worker.py`

### Video Bridge 同名差异文件

- `backend/api/video_bridge_api.py`
- `backend/services/video_bridge_service.py`

## 4. P2 验证缺口

- 新旧 fall 链路效果对比验证尚未完成。
- Video Bridge 业务价值验证尚未完成。
- 摄像头真相源一致性验证尚未完成。
- 后端启动级验证尚未完成。
- 前端构建级验证尚未完成。
- 真实摄像头流验证尚未完成。

## 5. 第三批推荐原则

- 不覆盖主链路。
- 不替换现有 fall 检测。
- 不接告警主链路。
- 不接移动端主入口。
- 所有新增能力必须有开关。
- 默认关闭。
- 能单独验证。
- 能一键回滚。

## 6. 第三批禁止事项

- 禁止整文件覆盖 `backend/main.py`。
- 禁止整文件覆盖 `backend/dependencies.py`。
- 禁止整文件覆盖 `backend/config.py`。
- 禁止改动移动端主入口。
- 禁止让 Video Bridge 直接控制摄像头。
- 禁止让实验 fall 链路直接触发现有 SOS/告警。

## 7. 第三批最小可做范围

- 只增加配置开关。
- 只增加只读状态接口。
- 只增加实验状态页或占位入口。
- 只做 `import` / `startup` 验证。
- 只做单一真相源检查脚本。
- 不改变现有业务行为。

## 8. Go / No-Go 条件

### Go 条件

- `health` 环境后端能启动。
- 当前主链路可用。
- 摄像头真相源明确。
- 新 fall 链路有独立验证入口。
- Video Bridge 有明确业务调用方。

### No-Go 条件

- 需要改 `main` / `dependencies` / `config` 大片代码。
- 需要替换现有 fall 链路。
- 需要动移动端主入口。
- 需要接真实告警。
- 不能证明新链路价值高于现链路。
