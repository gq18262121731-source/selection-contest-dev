# 跌倒检测模型与相关模型技术报告

生成日期：2026-05-09  
项目根目录：`D:/Program/410health_new/health1`  
外部跌倒模型目录：`D:/Program/model/fall_detection`

## 1. 报告结论

当前项目中的跌倒检测能力不是一个单独的模型，而是一套多模型、多阶段、多证据融合的视觉安全检测系统。它包含以下核心能力：

- YOLO 实时目标检测：快速发现人体、跌倒候选框、倒地姿态目标。
- YOLO Pose 姿态估计：提取人体 17 点骨架，判断人体结构和姿态角度。
- GRU 姿态时序模型：判断连续动作序列是否符合跌倒过程。
- TCN + Transformer 混合时序模型：捕捉局部动作突变和较长时间窗口内的关键帧关系。
- 姿态风险分类模型：对人体局部图像 crop 做风险姿态判断。
- 目标人物识别：使用 YuNet + SFace + 人体体态特征，过滤非目标老人。
- ByteTrack 多目标跟踪：保证连续帧中目标身份稳定。
- 状态机与伤害等级评估：把模型分数转成可执行的安全事件状态。
- 多模态大模型复核：在高风险快照上做二次视觉语义确认，降低最终误报。

当前部署 profile 为 `private_scene_fusion_v2`。该 profile 使用五路融合，但语义时序分支当前权重为 `0.00`，即模型存在、已训练，但默认不参与最终融合得分。

当前主力分支权重如下：

| 分支 | 当前权重 | 当前作用 |
| --- | ---: | --- |
| GRU 姿态时序模型 | 0.15 | 补充短时动作过程判断 |
| Hybrid TCN + Transformer | 0.45 | 主时序判断分支，当前权重最高 |
| Semantic Temporal | 0.00 | 已训练候选分支，当前 profile 未启用 |
| 姿态风险分类 | 0.30 | 单帧姿态异常证据 |
| YOLO 跌倒检测器 | 0.10 | 显式 fall/fallen 目标证据 |

默认融合阈值：

```text
threshold = 0.65
alert_hold = 3
```

这意味着系统不是看到一帧异常就报警，而是需要融合分数、连续状态和持续时间共同满足条件。

## 2. 当前检索到的关键代码与模型位置

### 2.1 后端项目代码

| 文件 | 作用 |
| --- | --- |
| `backend/services/fall_detection_service.py` | 后端实时跌倒检测守护服务，负责启动外部实时脚本并消费 JSONL 事件 |
| `backend/services/fall_frame_test_service.py` | 单帧跌倒检测服务，加载 YOLO 跌倒检测器和姿态风险分类器 |
| `backend/services/target_user_fall_service.py` | 目标人物专属跌倒检测桥接服务 |
| `backend/services/target_user_service.py` | 目标人物注册、脸部 embedding、人体 profile、目标匹配 |
| `backend/services/target_pose_service.py` | 目标 ROI 姿态估计和姿态规则判断 |
| `backend/services/posture_event_service.py` | 目标人物姿态事件分类，如快速跌倒、慢性倾倒、异常静止 |
| `backend/services/external_camera_bridge_service.py` | 外部摄像头运行时桥接，抓取最新帧后进入目标人物跌倒检测 |
| `backend/services/voice_service.py` | 多模态大模型跌倒快照复核 |
| `backend/dependencies.py` | 服务装配、告警处理、多模态复核调度 |
| `backend/api/target_user_api.py` | 目标人物、图片检测、外部摄像头检测接口 |
| `backend/api/camera_api.py` | 摄像头跌倒检测状态、快照、模拟告警接口 |
| `backend/config.py` | 跌倒检测、模型目录、多模态复核、阈值等配置 |

### 2.2 外部跌倒模型包

| 路径 | 作用 |
| --- | --- |
| `D:/Program/model/fall_detection/configs/model_registry.yaml` | 模型注册表和融合 profile |
| `D:/Program/model/fall_detection/scripts/realtime_fall_monitor.py` | 实时跌倒检测主脚本 |
| `D:/Program/model/fall_detection/scripts/train_temporal_gru.py` | GRU 姿态时序模型训练脚本 |
| `D:/Program/model/fall_detection/scripts/train_temporal_tcn_transformer.py` | TCN + Transformer 混合时序模型训练脚本 |
| `D:/Program/model/fall_detection/scripts/train_temporal_semantic_mix.py` | 语义时序模型训练脚本 |
| `D:/Program/model/fall_detection/scripts/llm_fall_review.py` | 旧版多模态复核脚本 |

### 2.3 当前主要权重文件

| 模型 | 路径 | 大小 | 最后修改时间 | 当前状态 |
| --- | --- | ---: | --- | --- |
| YOLO 跌倒检测器 | `D:/Program/model/fall_detection/weights/yolo_fall_detector_v1.pt` | 5.46 MB | 2026-04-29 12:48 | 已接入 |
| YOLO Pose | `D:/Program/model/fall_detection/yolo11n-pose.pt` | 未在权重目录表中显示 | 项目外部根目录 | 已接入 |
| YOLO Person | `D:/Program/model/fall_detection/yolo11n.pt` | 未在权重目录表中显示 | 项目外部根目录 | 已接入 |
| 姿态风险二分类 | `D:/Program/model/fall_detection/runs/yolo_posture_person_binary_cls_v1/weights/best.pt` | 11.02 MB | 2026-04-27 22:01 | 已接入 |
| GRU 姿态时序 v1 | `D:/Program/model/fall_detection/weights/gru_pose_fall_v1.pt` | 0.77 MB | 2026-04-27 17:56 | 已接入 |
| GRU 姿态时序 v2 | `D:/Program/model/fall_detection/weights/gru_pose_fall_v2_w16.pt` | 0.77 MB | 2026-04-27 17:59 | 已训练，候选 |
| Hybrid TCN + Transformer 私有真实场景 | `D:/Program/model/fall_detection/weights/hybrid_tcn_transformer_private_real_v1.pt` | 4.02 MB | 2026-04-28 16:22 | 已接入 |
| Hybrid TCN + Transformer fallback | `D:/Program/model/fall_detection/weights/hybrid_tcn_transformer_v2_matchgru.pt` | 4.02 MB | 2026-04-28 08:52 | fallback |
| Semantic Temporal 私有真实场景 | `D:/Program/model/fall_detection/weights/semantic_mix_falldb_private_real_v1.pt` | 2.33 MB | 2026-04-28 16:23 | 已训练，默认权重 0 |
| Semantic Temporal fallback | `D:/Program/model/fall_detection/weights/semantic_mix_falldb_v1.pt` | 2.33 MB | 2026-04-28 09:13 | fallback |
| YuNet 人脸检测 | `D:/Program/410health_new/health1/data/target_user_assets/face_detection_yunet.onnx` | 0.23 MB | 2026-05-07 12:03 | 已接入 |
| SFace 人脸识别 | `D:/Program/410health_new/health1/data/target_user_assets/face_recognition_sface.onnx` | 38.70 MB | 2026-05-07 12:03 | 已接入 |

## 3. 当前真实运行链路

### 3.1 后端实时摄像头跌倒检测链路

实时链路由 `FallDetectionService` 启动：

```text
后端服务启动
  -> FallDetectionService.start()
  -> D:/Program/model/fall_detection/scripts/realtime_fall_monitor.py
  -> 加载模型注册表
  -> 打开摄像头流或后端 MJPEG 检测流
  -> 对每帧/间隔帧做姿态估计、目标检测、时序推理
  -> 进入状态机
  -> 写入 JSONL 事件
  -> 后端 tail JSONL
  -> 生成告警、WebSocket 推送、快照复核
```

实时脚本中的主要输出字段包括：

```text
track_id
event_type
state
severity
fall_score
scores.gru
scores.hybrid
scores.semantic
scores.posture
scores.detector
posture_label
observations
injury.level
injury.state
injury.score
injury.reason
snapshot_path
```

这说明它不是简单输出 `true/false`，而是输出可追踪、可复核、可解释的安全事件记录。

### 3.2 目标人物专属跌倒检测链路

目标人物链路由 `TargetUserFallService` 执行：

```text
输入图片或外部摄像头最新帧
  -> YOLO person 或 fallback fall detector 找人
  -> ByteTrack 跟踪目标
  -> YuNet + SFace + body profile 匹配目标老人
  -> 非目标则过滤
  -> 目标命中后裁剪 ROI
  -> FallFrameTestService 做 YOLO 跌倒检测和姿态风险分类
  -> TargetPoseService 做 YOLO Pose 姿态估计
  -> PostureEventService 判断姿态事件
  -> 返回 target_match、fall_result、pose_result、posture_event、diagnostics
```

该链路的核心价值是减少“画面里其他人触发老人跌倒告警”的风险。

## 4. 使用到的高端/前沿技术与实际效果

### 4.1 YOLO 实时视觉检测

当前使用：

```text
yolo11n.pt
yolo_fall_detector_v1.pt
```

技术属性：

- 单阶段目标检测。
- 推理速度快，适合实时视频。
- 可直接输出人体框、跌倒框、类别、置信度。

对模型效果的贡献：

- 让系统具备实时视觉发现能力。
- 快速定位画面中人体位置。
- 为目标跟踪、ROI 裁剪、姿态估计提供空间基础。
- 对显式 `fall/fallen` 姿态给出直接证据。

主要解决的问题：

- “画面里有没有人？”
- “人在哪里？”
- “是否出现明显倒地目标？”

局限：

- 单帧 YOLO 难以可靠区分躺下、坐地、弯腰、跌倒。
- 对遮挡、低光、模糊、极端视角敏感。
- 因此项目没有单独依赖 YOLO，而是与时序模型和状态机融合。

### 4.2 YOLO Pose 人体关键点估计

当前使用：

```text
yolo11n-pose.pt
```

技术属性：

- 从人体图像中提取 17 个关键点。
- 包括鼻子、眼睛、耳朵、肩、肘、腕、髋、膝、踝。
- 输出每个关键点坐标和置信度。

对模型效果的贡献：

- 把人体从“矩形框”变成“结构化骨架”。
- 可以计算躯干角度、身体倾斜、手部位置、头肩髋关系。
- 能把视觉问题转成动作结构问题。
- 为 GRU、TCN、Transformer 时序模型提供输入。

主要解决的问题：

- “这个人是站着、坐着、弯腰，还是倒地？”
- “身体是否快速倾斜？”
- “是否存在慢性滑倒、瘫坐、前倾等姿态事件？”

局限：

- 关键点在遮挡、背身、被家具遮住时可能不稳定。
- 老人在地面边缘、床边、桌边时，关键点可能被误识别。

### 4.3 姿态归一化与运动学特征工程

实现位置：

```text
D:/Program/model/fall_detection/scripts/train_temporal_gru.py
normalize_pose()
```

核心做法：

- 以人体框中心为坐标原点。
- 以人体框高度做尺度归一化。
- 保留关键点置信度。
- 计算关键点速度。
- 加入人体宽高比和中心高度特征。

对模型效果的贡献：

- 减少摄像头距离变化带来的影响。
- 减少不同分辨率、不同画面尺寸导致的坐标偏差。
- 让模型关注动作结构，而不是像素绝对位置。
- 能表达“快速下坠”“身体变横”“中心高度下降”等动态信息。

主要解决的问题：

- “同一个跌倒动作在远处和近处看起来坐标差异很大。”
- “不同摄像头分辨率下模型不能直接比较像素坐标。”

### 4.4 GRU 姿态时序模型

当前权重：

```text
D:/Program/model/fall_detection/weights/gru_pose_fall_v1.pt
```

技术属性：

- GRU 属于循环神经网络。
- 适合建模连续时间序列。
- 当前输入是连续窗口内的人体关键点、速度、人体框特征。

对模型效果的贡献：

- 识别“跌倒过程”，而不是单帧姿态。
- 捕捉从站立到失衡、下坠、倒地的连续变化。
- 降低单帧误判。
- 与 TCN + Transformer 主分支形成互补。

当前融合权重：

```text
0.15
```

说明：

- 它不是当前最重的分支，但能提供稳定的时序辅助。
- 对明显连续跌倒动作有价值。

### 4.5 Hybrid TCN + Transformer 时序模型

当前主模型：

```text
D:/Program/model/fall_detection/weights/hybrid_tcn_transformer_private_real_v1.pt
```

fallback：

```text
D:/Program/model/fall_detection/weights/hybrid_tcn_transformer_v2_matchgru.pt
```

技术组成：

- TCN：时序卷积网络。
- Dilated Convolution：膨胀卷积，扩大时间感受野。
- Residual Block：残差结构，降低训练难度。
- Transformer Encoder：全局时序关系建模。
- Attention Pooling：自动关注关键时间片段。
- Max Pooling：保留最强异常信号。
- Focal Loss：强化难样本学习。
- Hard Negative Weighting：提高坐下、躺下、弯腰等难负样本权重。

对模型效果的贡献：

- TCN 擅长捕捉局部动作突变，例如身体突然下坠。
- Transformer 擅长捕捉跨帧关系，例如先失衡、再倒地、再静止。
- Attention 让模型自动关注最关键的帧，而不是平均看待所有帧。
- Hard Negative 和 Focal Loss 提升边界动作区分能力。

当前融合权重：

```text
0.45
```

说明：

- 这是当前 `private_scene_fusion_v2` 中权重最高的分支。
- 说明当前部署策略把它作为主时序判断模型。

已检索到的训练指标摘要：

| 训练运行 | 最佳验证 Accuracy | 最佳验证 Precision | 最佳验证 Recall | 最佳验证 F1 | 测试 Accuracy | 测试 F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `hybrid_tcn_transformer_private_real_v1` | 0.8466 | 0.7740 | 0.8692 | 0.8188 | 0.6931 | 未完整显示 |
| `hybrid_tcn_transformer_v2_matchgru` | 0.8356 | 0.7500 | 0.8621 | 0.8021 | 0.7433 | 未完整显示 |
| `hybrid_tcn_transformer_v1` | 0.8221 | 0.7250 | 0.8923 | 0.8000 | 0.7208 | 未完整显示 |

工程解读：

- 验证集 Recall 偏高，符合养老安全场景中“优先发现风险”的目标。
- 测试集指标低于验证集，说明仍存在跨场景泛化压力。
- 当前系统通过状态机、多模型融合和多模态复核来补偿单模型泛化不足。

### 4.6 Semantic Temporal Net 语义时序模型

当前模型：

```text
D:/Program/model/fall_detection/weights/semantic_mix_falldb_private_real_v1.pt
```

fallback：

```text
D:/Program/model/fall_detection/weights/semantic_mix_falldb_v1.pt
```

技术组成：

- 语义姿态特征。
- 1D 时序卷积。
- Transformer Encoder。
- Attention Pooling。
- FallDatabase 骨架数据混合训练。
- Hard Negative 加权。

对模型效果的贡献：

- 更关注身体结构和动作语义，而不是原始图像外观。
- 理论上更容易跨场景迁移。
- 对不同摄像头、背景、衣着变化更稳健。

当前部署状态：

```text
semantic weight = 0.00
```

这意味着：

- 模型存在，并已训练。
- 当前默认部署 profile 不使用它贡献最终 fall_score。
- 它可以作为后续 A/B 测试或新 profile 的候选分支。

已检索到的训练指标摘要：

| 训练运行 | 最佳验证 Accuracy | 最佳验证 Precision | 最佳验证 Recall | 最佳验证 F1 | 测试 Accuracy |
| --- | ---: | ---: | ---: | ---: | ---: |
| `semantic_mix_falldb_private_real_v1` | 0.8918 | 0.7955 | 0.8655 | 0.8290 | 0.7913 |
| `semantic_mix_falldb_private_dryrun_v1` | 0.9030 | 0.8704 | 0.7991 | 0.8332 | 0.8145 |
| `semantic_mix_falldb_v1` | 0.8904 | 0.7904 | 0.8686 | 0.8277 | 0.7977 |

工程解读：

- 语义模型指标并不弱。
- 当前权重为 0 更像是保守部署选择，不代表模型没有价值。
- 后续可以通过回放集验证是否把权重从 `0.00` 提升到 `0.05` 或 `0.10`。

### 4.7 YOLO 姿态风险分类模型

当前模型：

```text
D:/Program/model/fall_detection/runs/yolo_posture_person_binary_cls_v1/weights/best.pt
```

技术属性：

- 对人体 crop 做姿态风险分类。
- 输入不是整张图，而是目标人物区域。
- 输出姿态标签和风险分数。

对模型效果的贡献：

- 提供单帧姿态风险证据。
- 当时序窗口尚未积累足够帧时，能更早给出风险提示。
- 对已经倒地、横躺、明显异常姿态敏感。

当前融合权重：

```text
0.30
```

说明：

- 这是第二高权重分支。
- 它与 Hybrid 时序模型形成“单帧 + 时序”的组合。

局限：

- 容易受到坐姿、躺姿、床边动作影响。
- 必须配合状态机、目标跟踪和多模态复核。

### 4.8 多模型加权融合

实时脚本中最终分数结构：

```text
fall_score =
  gru_score * gru_weight
  + hybrid_score * hybrid_weight
  + semantic_score * semantic_weight
  + posture_score * posture_weight
  + detector_score * detector_weight
```

对模型效果的贡献：

- 把不同证据源组合成统一分数。
- 单帧视觉、时序动作、姿态分类、显式跌倒检测互相校验。
- 降低单模型失效造成的误报或漏报。

工程意义：

- YOLO 负责快。
- Pose 负责结构。
- GRU/TCN/Transformer 负责过程。
- 姿态分类负责局部风险。
- 状态机负责稳定决策。

这是当前系统最关键的工程设计之一。

### 4.9 ByteTrack 多目标跟踪

使用位置：

```text
backend/services/target_user_fall_service.py
```

技术属性：

- 多目标跟踪算法。
- 通过检测框和置信度维持 track_id。
- 适合多人视频流场景。

对模型效果的贡献：

- 连续帧中保持同一个人的身份。
- 防止目标在多人场景中跳变。
- 支持目标人物缓存、ROI 裁剪、跌倒状态持续判断。

主要解决的问题：

- “这一帧的人和上一帧的人是不是同一个？”
- “目标老人被短暂遮挡后是否还能继续跟踪？”
- “是否应该沿用最近一次目标匹配结果？”

局限：

- 目标长期遮挡、多人交叉、画面模糊时可能出现 track switch。
- 当前实现仍需要目标人物匹配和缓存共同兜底。

### 4.10 目标人物识别：YuNet + SFace + Body Profile

当前模型：

```text
D:/Program/410health_new/health1/data/target_user_assets/face_detection_yunet.onnx
D:/Program/410health_new/health1/data/target_user_assets/face_recognition_sface.onnx
```

技术组成：

- YuNet：轻量人脸检测。
- SFace：人脸识别 embedding。
- Haar Cascade：人脸检测 fallback。
- Body Profile：人体框比例、面积、中心位置、标签编码等轻量体态特征。

对模型效果的贡献：

- 把“检测到跌倒”升级成“目标老人发生疑似跌倒”。
- 减少护理人员、家属、路人触发误报。
- 在人脸不可用时，使用 body profile 做弱匹配补充。

匹配逻辑摘要：

```text
如果 face_embedding 和 body_profile 都存在：
  fused = 0.75 * face_score + 0.25 * body_score
如果只有 face_embedding：
  fused = face_score
如果只有 body_profile：
  fused = body_score

判定 target 的条件：
  fused >= 0.62
  且 face_score >= 0.62 或 body_score >= 0.72
```

局限：

- body profile 不是强身份识别。
- 背脸、遮挡、低清、强逆光会降低人脸匹配可靠性。
- 多个老人身形相近时，body profile 可能不足以区分。

### 4.11 ROI 目标区域裁剪

使用位置：

```text
backend/services/target_user_fall_service.py
```

技术做法：

- 先定位目标人物 bbox。
- 按比例扩展 bbox。
- 裁剪目标 ROI。
- 在 ROI 内执行跌倒检测和姿态估计。
- 再把检测框坐标映射回原图。

对模型效果的贡献：

- 降低背景干扰。
- 降低非目标人物干扰。
- 提升推理速度。
- 让姿态估计更聚焦于目标老人。

实际价值：

- 对室内养老场景很重要，因为画面中可能有桌椅、床、护理人员、家属和其他老人。

### 4.12 跌倒状态机

状态机配置：

```text
D:/Program/410health_new/health1/configs/fall_detection/room_camera_alert_rules.yaml
D:/Program/model/fall_detection/configs/alert_rules.yaml
```

主要状态：

```text
normal
suspected_fall
confirmed_fall
post_fall_monitoring
recovery_watch
recovered
injury_watch
abnormal_recovery
needs_assistance
emergency
```

对模型效果的贡献：

- 防止一帧误检直接变成报警。
- 引入持续时间、姿态稳定性、倒地时长、恢复行为。
- 把模型输出转成护理流程能理解的状态。

典型效果：

```text
短暂弯腰 -> 可能只是 suspected 或不触发
持续倒地 -> confirmed_fall
倒地后不动 -> post_fall_monitoring / emergency
倒地后恢复但步态异常 -> abnormal_recovery / injury_watch
```

这是从“模型分类器”走向“业务安全系统”的关键层。

### 4.13 跌倒后伤害风险评估

规则配置：

```text
D:/Program/410health_new/health1/configs/fall_detection/room_camera_injury_rules.yaml
D:/Program/model/fall_detection/configs/injury_rules.yaml
```

使用指标：

- 倒地持续时间。
- 静止时间。
- 恢复延迟。
- 目标中心移动速度。
- 晃动幅度。
- 左右肢体运动不对称。
- 疑似跛行分数。

输出等级：

| 等级 | 含义 |
| --- | --- |
| I0 | 正常或无伤害证据 |
| I1 | 已恢复，继续观察 |
| I2 | 伤害观察 |
| I3 | 异常恢复 |
| I4 | 需要协助 |
| I5 | 紧急 |

对模型效果的贡献：

- 不只判断“有没有跌倒”，还判断“跌倒后是否需要立即人工介入”。
- 支持告警分级。
- 避免所有跌倒事件都以同一等级推送。

业务价值：

- 对养老护理更实际。护理人员关心的不只是是否摔倒，还关心是否无法起身、是否恢复异常、是否可能受伤。

### 4.14 多模态大模型快照复核

使用位置：

```text
backend/services/voice_service.py
backend/dependencies.py
```

支持 provider：

```text
qwen_omni
siliconflow_script
auto
disabled
```

默认 Qwen Omni 模型 ID：

```text
qwen2.5-omni-7b
```

触发条件：

- 多模态复核开关开启。
- 事件存在 `snapshot_path`。
- 快照文件存在。
- `fall_score` 大于等于 `fall_detection_multimodal_min_score`。
- provider 可用。

对模型效果的贡献：

- 使用视觉语言模型对现场截图做二次判断。
- 对明显误报做降级。
- 识别“坐姿、办公、弯腰、无明显跌倒迹象”等假阳性线索。
- 给告警附加可读原因。

工程定位：

- 它不是主检测模型。
- 它是告警复核层。
- 它适合降低最终通知到护理人员的误报率。

风险：

- 依赖外部 API。
- 复核耗时高于本地视觉模型。
- 只能基于单张快照，不应虚构图中看不到的运动过程。

### 4.15 Focal Loss

使用位置：

```text
D:/Program/model/fall_detection/scripts/train_temporal_tcn_transformer.py
D:/Program/model/fall_detection/scripts/train_temporal_semantic_mix.py
```

技术作用：

- 降低简单样本在损失中的权重。
- 提高难样本影响。
- 对正负样本不平衡问题更友好。

对模型效果的贡献：

- 让模型更关注容易误判的跌倒边界动作。
- 提高对少数跌倒样本的学习效率。
- 配合 hard negative，对养老场景中的躺下、坐下、弯腰更有针对性。

### 4.16 Hard Negative Mining / 难负样本加权

使用样本标签：

```text
lying
lie_down
sit_down
sitting
```

技术作用：

- 把“看起来像跌倒但实际不是跌倒”的样本加大训练权重。

对模型效果的贡献：

- 降低坐下、躺下、弯腰、地面活动导致的误报。
- 让模型学会更细粒度地区分“倒地风险”和“正常低姿态行为”。

这是养老场景中非常必要的训练策略，因为老人可能会坐床边、坐沙发、弯腰取物、靠在椅子上休息。

### 4.17 CUDA 与半精度推理

使用位置：

```text
FallFrameTestService
TargetUserService
TargetPoseService
```

技术作用：

- 如果 `torch.cuda.is_available()` 为真，则使用 GPU。
- GPU 可用时启用 half precision。

对模型效果的贡献：

- 降低推理延迟。
- 提高视频流处理帧率。
- 让多个视觉模型组合在实时链路中可运行。

注意：

- 是否真正生效取决于当前 Python 环境、PyTorch CUDA 版本、显卡驱动和显卡可用性。

## 5. 模型融合后的业务效果

### 5.1 相比单一 YOLO 模型的提升

单一 YOLO 的问题：

- 只看当前帧。
- 难以判断动作过程。
- 容易把躺下、坐下、弯腰识别成跌倒。
- 对遮挡和角度敏感。

当前系统提升：

- 使用时序模型判断过程。
- 使用姿态模型判断人体结构。
- 使用状态机要求持续性。
- 使用目标人物识别过滤非目标。
- 使用多模态复核降低最终误报。

### 5.2 相比单一姿态模型的提升

单一姿态模型的问题：

- 关键点会抖动。
- 遮挡时关键点缺失。
- 只凭角度无法完全判断跌倒。

当前系统提升：

- YOLO bbox 和 posture classifier 提供图像证据。
- 时序模型处理关键点变化。
- 状态机处理短暂抖动。
- ByteTrack 维持连续目标身份。

### 5.3 相比传感器式跌倒检测的提升

视觉跌倒检测优势：

- 不要求老人佩戴设备。
- 能观察现场状态。
- 能提供快照作为复核证据。
- 能区分目标人物和非目标人物。

视觉跌倒检测风险：

- 受光照、遮挡、角度影响。
- 涉及隐私和摄像头部署位置。
- 需要现场标定和回放验证。

## 6. 当前系统的技术边界

### 6.1 当前已经接入主链路的能力

- YOLO fall detector。
- YOLO pose。
- GRU 姿态时序。
- Hybrid TCN + Transformer。
- YOLO 姿态风险分类。
- YuNet + SFace 目标人物识别。
- ByteTrack 跟踪。
- ROI 裁剪。
- 状态机。
- 伤害等级规则。
- 多模态快照复核。

### 6.2 已训练但当前默认未启用或贡献很低的能力

- Semantic Temporal Net：当前 `semantic` 权重为 `0.00`。
- 多个候选/fallback 权重：例如 `gru_pose_fall_v2_w16.pt`、`hybrid_tcn_transformer_v2_matchgru.pt`。
- 外部旧版 SiliconFlow 复核脚本：仅在 provider 选择或 API key 条件满足时使用。

### 6.3 当前不是强项的场景

- 夜间低光、逆光。
- 人体被床、桌、沙发大面积遮挡。
- 多人交叉走动。
- 老人和护理人员身形相似且人脸不可见。
- 摄像头只拍到身体一部分。
- 老人缓慢滑落到地面且动作幅度很小。
- 老人在床上翻身、坐床边、地面康复训练等复杂低姿态活动。

## 7. 配置现状

当前默认配置在 `backend/config.py` 中：

```text
fall_detection_enabled = False
fall_detection_model_root = D:\Program\model\fall_detection
fall_detection_profile = private_scene_fusion_v2
fall_detection_speed_profile = accuracy
fall_detection_multimodal_enabled = True
fall_detection_multimodal_provider = auto
fall_detection_multimodal_min_score = 0.45
fall_detection_multimodal_timeout_seconds = 45
```

注意：

- 默认代码配置里 `fall_detection_enabled` 是 `False`。
- 实际运行是否开启取决于 `.env`。
- 本报告未写入 `.env` 中任何密钥或敏感值。

## 8. 当前模型指标摘要

已检索到的训练指标如下，注意这些指标来自现有 `metrics.json`，不同模型的训练集、验证集和测试集划分可能不同，不能直接简单横向比较。

| 运行名 | 最佳验证 Epoch | 最佳验证 Accuracy | 最佳验证 Precision | 最佳验证 Recall | 最佳验证 F1 | 测试 Accuracy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `gru_pose_fall_v1` | 10 | 0.8222 | 0.7582 | 0.7931 | 未记录 | 0.8011 |
| `gru_pose_fall_v2_w16` | 7 | 0.8385 | 0.8271 | 0.7333 | 未记录 | 0.7769 |
| `hybrid_tcn_transformer_private_dryrun_v1` | 4 | 0.8344 | 0.7794 | 0.8154 | 0.7970 | 0.7761 |
| `hybrid_tcn_transformer_private_real_v1` | 6 | 0.8466 | 0.7740 | 0.8692 | 0.8188 | 0.6931 |
| `hybrid_tcn_transformer_v1` | 15 | 0.8221 | 0.7250 | 0.8923 | 0.8000 | 0.7208 |
| `hybrid_tcn_transformer_v2_matchgru` | 9 | 0.8356 | 0.7500 | 0.8621 | 0.8021 | 0.7433 |
| `semantic_mix_falldb_private_dryrun_v1` | 2 | 0.9030 | 0.8704 | 0.7991 | 0.8332 | 0.8145 |
| `semantic_mix_falldb_private_real_v1` | 8 | 0.8918 | 0.7955 | 0.8655 | 0.8290 | 0.7913 |
| `semantic_mix_falldb_v1` | 16 | 0.8904 | 0.7904 | 0.8686 | 0.8277 | 0.7977 |

工程解读：

- Hybrid 模型在当前 profile 中权重最高，符合其较强验证召回表现。
- Semantic 模型指标较好，但当前权重为 0，需要通过回放验证决定是否启用。
- 测试指标低于验证指标，说明仍需要现场场景校准。

## 9. 误报与漏报控制策略

当前系统采用多层控制：

### 9.1 误报控制

- 非目标人物过滤。
- ROI 裁剪减少背景干扰。
- Hard Negative 训练降低坐下、躺下、弯腰误报。
- 状态机要求持续性。
- 多模态快照复核可降级明显误报。
- 告警去重和事件状态管理避免重复推送。

### 9.2 漏报控制

- YOLO fall detector 提供直接倒地目标检测。
- 姿态风险分类提供单帧早期风险。
- GRU/TCN/Transformer 捕捉连续动作过程。
- Hybrid profile 中较高 recall 倾向优先发现风险。
- 疑似跌倒状态允许先进入观察，而不是直接丢弃。

### 9.3 当前权衡

养老跌倒检测通常不能只追求低误报。实际目标应是：

```text
高风险事件尽量不漏
普通误报由状态机和复核层逐级压低
最终推送给护理人员的告警保持可解释、可分级
```

当前系统设计符合这个方向。

## 10. 从长期工程角度的补充判断

### 10.1 当前系统最有价值的部分

最有价值的不是某一个模型，而是“分层决策架构”：

```text
检测层 -> 姿态层 -> 时序层 -> 目标人物层 -> 状态机层 -> 复核层 -> 告警层
```

这比单模型更接近真实部署要求。跌倒检测在现实环境中有很多边界情况，单模型很难同时做到高召回和低误报。当前系统通过多证据融合和状态机，把模型输出变成可操作事件，这是正确方向。

### 10.2 当前最大的短板

当前最大的短板不是缺少“更高端”的模型，而是缺少稳定的现场闭环数据：

- 当前实际摄像头角度下的正常活动样本。
- 当前实际房间中的跌倒模拟样本。
- 床边、桌边、椅子旁、地面边缘等 hard negative。
- 夜间、遮挡、多人场景样本。
- 每次误报/漏报后的标注回流。

如果没有这些数据，再复杂的模型也会在现场表现不稳定。

### 10.3 当前不建议盲目升级的方向

不建议直接盲目替换为更大的视觉模型，原因：

- 实时性会下降。
- 部署复杂度会上升。
- 当前问题主要是场景泛化和误报闭环，不一定是模型容量不足。
- 本地 GPU/CPU 资源可能成为瓶颈。

更合理的方向是：

- 先做回放评测。
- 再调融合权重。
- 再决定是否引入更大模型或新分支。

## 11. 推荐后续优化路线

### 11.1 第一阶段：把评测闭环补齐

目标：

- 建立固定回放集。
- 每次模型或阈值变化都能量化比较。

建议指标：

```text
跌倒召回率
误报次数/小时
确认告警延迟
目标人物过滤准确率
多模态复核降级准确率
I4/I5 严重事件漏报数
```

建议样本分类：

- 真实跌倒模拟。
- 坐下。
- 躺下。
- 弯腰。
- 坐地。
- 床上活动。
- 护理人员经过。
- 多人同框。
- 遮挡。
- 夜间低光。

### 11.2 第二阶段：验证 Semantic 分支是否启用

当前 semantic 模型指标不弱，但权重为 0。建议新建一个 profile：

```text
private_scene_fusion_v3_candidate:
  gru: 0.12
  hybrid: 0.40
  semantic: 0.08
  posture: 0.28
  detector: 0.12
```

用回放集比较：

- 是否降低误报。
- 是否提高慢性滑倒召回。
- 是否增加延迟。

只有回放结果优于当前 profile，才切换默认配置。

### 11.3 第三阶段：优化目标人物匹配

当前目标人物匹配已经有 YuNet + SFace + body profile，但可以继续增强：

- 注册多角度照片。
- 注册不同光照照片。
- 引入目标人物质量评分。
- 当 face_score 不可靠时降低 body-only 自动确认权重。
- 对 track_id 发生切换的场景增加重验证。

### 11.4 第四阶段：现场阈值标定

重点标定参数：

```text
fall_detection_threshold_override
fall_detection_min_alert_score
fall_detection_confirmation_window_seconds
fall_detection_min_confirmed_hits
fall_detection_min_down_seconds
fall_detection_high_confidence_score
```

标定原则：

- 先保证真实跌倒不漏。
- 再逐步降低坐下/躺下误报。
- 不要只凭单次演示调参。
- 必须基于固定回放集调参。

### 11.5 第五阶段：多模态复核策略优化

建议：

- 只对中高风险告警触发多模态复核。
- 对 `fall_score` 极高且状态机确认的事件，不等待复核即可先推送。
- 对疑似但低置信事件，复核结果可用于降级。
- 保存复核输入、输出和最终人工处理结果，形成后续训练数据。

## 12. 可对外说明的技术亮点

如果需要在答辩、汇报或文档中概括，可以使用以下表述：

1. 系统采用多模态视觉感知架构，结合目标检测、人体姿态估计、姿态分类和时序神经网络，实现对跌倒行为的多证据识别。
2. 时序建模部分使用 GRU 与 TCN + Transformer 混合网络，能够识别从失衡、下坠到倒地静止的动态过程，而不是依赖单帧判断。
3. 系统使用 YOLO Pose 提取人体关键点，并进行尺度归一化和运动学特征建模，提高对不同摄像头距离和分辨率的适应能力。
4. 通过 YuNet + SFace 人脸识别和人体体态特征，实现目标老人专属过滤，降低非目标人员引发误报的概率。
5. 通过 ByteTrack 维持连续帧目标身份，使跌倒状态判断具备时间连续性和跟踪一致性。
6. 通过状态机和伤害等级规则，将模型分数转化为护理场景可执行的事件状态和告警等级。
7. 通过多模态大模型对告警快照进行二次复核，进一步降低复杂低姿态场景下的误报。
8. 训练中引入 Focal Loss 和 Hard Negative 样本加权，针对坐下、躺下、弯腰等高混淆场景提升区分能力。

## 13. 最终评价

当前项目的跌倒检测系统已经具备较完整的工程形态。它不是简单调用一个开源检测模型，而是把多个视觉模型、时序模型、目标人物识别、跟踪、状态机、伤害评估和多模态复核组合成一套养老看护场景下的安全事件系统。

从技术先进性看，项目已经使用了以下现代技术：

```text
YOLO 实时检测
YOLO Pose 姿态估计
GRU 时序建模
TCN + Transformer 混合时序建模
Attention Pooling
Focal Loss
Hard Negative Mining
ByteTrack 多目标跟踪
YuNet + SFace 人脸识别
多模型融合
状态机事件建模
多模态大模型复核
```

从落地角度看，当前系统的核心竞争力不是“用了多少模型”，而是“把模型变成了可解释、可复核、可分级、可告警的业务链路”。这比单纯提高某个模型的离线准确率更重要。

后续工作的重点不应只是继续堆叠更大的模型，而应优先建立现场数据闭环、固定回放评测、阈值标定和误报样本回流。只有这些闭环完成后，模型升级才会真正带来稳定收益。
