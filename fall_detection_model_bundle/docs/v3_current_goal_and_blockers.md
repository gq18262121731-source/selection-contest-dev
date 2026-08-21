# 跌倒检测 V3 当前目标、已完成内容与阻塞问题

生成日期：2026-05-18

## 1. 最终要得到什么效果

本轮升级的最终目标不是简单替换一个 `.pt` 权重，而是得到一套可以安全接入当前系统的 **跌倒检测 V3 模型包**。它应该在不破坏现有后端、前端、移动端告警链路的前提下，替换或增强当前 `private_scene_fusion_v2` 跌倒检测方案。

理想最终效果如下：

1. 摄像头画面中老人真实跌倒时，系统能稳定进入 `confirmed_fall`，而不是只停留在 `suspected_fall`。
2. 老人睡觉、躺下、坐下、弯腰、捡东西、被家属搀扶、多人经过时，不应误触发 `confirmed_fall`。
3. 多人同屏时，系统能尽量判断跌倒对象是否为目标老人，避免把旁人动作绑定到老人。
4. 前端仍能显示原有的摄像头画面、姿态/跌倒 overlay、告警面板和复核结果。
5. 后端仍走现有告警链路，不需要推倒重写业务系统。
6. 移动端和家属端收到的告警应更稳定，重复告警和误报减少。
7. Qwen/VLM 复核只用于疑似事件解释、误报降级和报告生成，不能阻塞高置信紧急告警。
8. 所有新模型必须先通过 replay/shadow/灰度验证，最后再通过配置无缝切换。

最终交付物应包含：

```text
fall_detection_model_bundle/v3_upgrade_lab/exports/promoted/
  configs/model_registry.v3.promoted.yaml
  configs/vlm_review.v3.yaml
  configs/scene_roi_profiles.v3.yaml
  configs/evaluation_gates.yaml
  weights/yolo26n-pose.pt 或更优姿态模型
  weights/yolo26_fall_detector_v3_best.pt
  weights/骨架时序模型权重
  reports/replacement_gate_report.v3.md
  reports/replay 对比报告
  package_manifest.json
  rollback_to_private_scene_fusion_v2.md
```

只有当 `package_manifest.json` 中出现：

```json
{
  "promotion_gate_passed": true
}
```

并且 `replacement_gate_report.v3.md` 明确写明 V3 可晋级时，才能把它作为生产替换方案。

## 2. 当前已经完成了什么

目前已经完成的是 **V3 升级实验体系与第一轮 CPU 训练/验证**，包括：

### 2.1 已建立隔离实验区

位置：

```text
fall_detection_model_bundle/v3_upgrade_lab/
```

这个目录用于放新模型、新数据、新配置、新报告，不直接覆盖生产模型。

### 2.2 已下载 YOLO26 候选权重

位置：

```text
fall_detection_model_bundle/v3_upgrade_lab/weights/yolo26/
```

已下载：

```text
yolo26n-pose.pt
yolo26s-pose.pt
yolo26n.pt
yolo26s.pt
yolo26n-seg.pt
```

### 2.3 已增加 V3 独立模型注册表

位置：

```text
fall_detection_model_bundle/v3_upgrade_lab/configs/model_registry.v3.yaml
```

里面包含：

```text
fall_v3_shadow_yolo26_pose
fall_v3_recall_probe
fall_v3_hard_negative_guard
```

这些 profile 用于 replay/shadow，不直接替换生产。

### 2.4 已支持后端可选加载 V3 registry

新增环境变量：

```env
FALL_DETECTION_MODEL_REGISTRY_PATH=
```

默认空值时，后端仍使用旧 registry。只有显式配置时，才会加载 V3 registry。

### 2.5 已导入现有外部数据和权重

从：

```text
D:\Program\model\fall_detection
```

同步到了 V3 实验区：

```text
fall_detect_existing 数据集
fall_detect_v2_recall_existing 数据集
private_dryrun_videos
private_raw_videos
pose_tcn_fall_v2.pt
yolo_fall_detector_v1.pt 参考权重
```

### 2.6 已跑私有 dry-run replay

使用两个私有视频：

```text
scene_fall_dryrun.mp4
scene_safe_dryrun.mp4
```

跑了 baseline 和 V3 profile 对比。

报告位置：

```text
fall_detection_model_bundle/v3_upgrade_lab/reports/replay_matrix_*/
```

### 2.7 已训练 YOLO26 detector CPU probe/refine

训练产物：

```text
fall_detection_model_bundle/v3_upgrade_lab/weights/yolo26/yolo26_fall_detector_v3_best.pt
```

注意：这是 CPU 环境下的小规模 probe/refine，不是最终全量训练模型。

### 2.8 已生成失败样本再训练清单

位置：

```text
fall_detection_model_bundle/v3_upgrade_lab/manifests/retraining_manifest.v3.csv
```

当前共挖出：

```text
总失败项：24
P1 hard-negative confirmed false positive：9
P2 positive missed confirmed fall：15
```

### 2.9 已生成数据采集计划

位置：

```text
fall_detection_model_bundle/v3_upgrade_lab/reports/data_collection_plan.v3.md
```

该文档说明了每个养老场景至少要采集多少正样本和困难负样本。

### 2.10 已生成替换门禁报告

位置：

```text
fall_detection_model_bundle/v3_upgrade_lab/reports/replacement_gate_report.v3.md
```

当前结论：

```text
Promotable now: false
```

### 2.11 已生成 blocked 导出包

位置：

```text
fall_detection_model_bundle/v3_upgrade_lab/exports/promoted/
```

当前包不是生产可替换包，而是 review/继续训练用包。

当前 `package_manifest.json` 中明确：

```json
{
  "profile_name": "fall_v3_final_promoted_blocked",
  "promotion_gate_passed": false,
  "note": "This package is blocked for production replacement. Keep production on private_scene_fusion_v2."
}
```

## 3. 当前真实训练和评估结果

### 3.1 旧 detector 在现有验证集上的表现

旧模型：

```text
fall_detection_model_bundle/weights/yolo_fall_detector_v1.pt
```

在 `fall_detect_existing` 验证集上结果约为：

```text
mAP50 ≈ 0.428
Recall ≈ 0.678
```

### 3.2 新 YOLO26 detector CPU probe/refine 表现

新模型：

```text
fall_detection_model_bundle/v3_upgrade_lab/weights/yolo26/yolo26_fall_detector_v3_best.pt
```

当前 CPU probe/refine 后结果约为：

```text
mAP50 ≈ 0.317
Recall ≈ 0.466
```

并且 `fall` 类召回仍然偏低。

结论：

```text
当前 YOLO26 detector 还不能替换旧 detector。
```

### 3.3 replay 结果

私有 `scene_fall_dryrun.mp4`：

```text
baseline：只进入 suspected_fall，没有 confirmed_fall
V3：只进入 suspected_fall，没有 confirmed_fall
```

私有 `scene_safe_dryrun.mp4`：

```text
正常阈值：没有 confirmed false positive
降低阈值后：会出现 confirmed false positive
```

结论：

```text
靠调阈值不能解决问题。
降低阈值会引入误报，但正样本仍不能稳定 confirmed。
必须补数据并重新训练 detector / temporal / fusion。
```

## 4. 当前遇到的主要问题

### 问题 1：当前环境不是 CUDA 训练环境

当前 `health` 环境检测结果：

```text
torch: 2.11.0+cpu
cuda: False
device: cpu
```

这意味着：

1. 只能跑小规模 CPU probe。
2. 无法高效训练 YOLO26s、YOLO26 pose、长 epoch detector。
3. 无法合理训练/评估完整时序模型矩阵。
4. 当前训练结果不能代表 V3 模型上限。

要解决：

```powershell
conda run -n health python -m pip uninstall -y torch torchvision torchaudio
conda run -n health python -m pip install --index-url https://download.pytorch.org/whl/cu121 torch torchvision torchaudio
```

然后确认：

```powershell
conda run -n health python -c "import torch; print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu')"
```

### 问题 2：现场授权视频样本不足

目前只有少量 dry-run 视频，不足以训练出真正贴合养老场景的模型。

尤其缺少：

```text
卧室低光跌倒
床边跌落
沙发/床上正常躺下
老人弯腰捡东西
坐下/起身
走廊多人经过
护工/家属搀扶
目标老人半遮挡
远景小目标跌倒
跌倒后静止
跌倒后被扶起
```

要解决：

按下面文档补采集：

```text
fall_detection_model_bundle/v3_upgrade_lab/reports/data_collection_plan.v3.md
```

### 问题 3：当前正样本只到 suspected，不能 confirmed

`scene_fall_dryrun.mp4` 中，旧模型和 V3 都只输出 `suspected_fall`。

这说明：

1. detector 分支对这个场景的 fall/fallen 支持不够。
2. temporal 分支没有给出足够确认分。
3. 状态机没有足够证据把 suspected 推进 confirmed。

要解决：

1. 把该视频作为正样本重点回流训练。
2. 标注 `fall_transition`、`impact`、`fallen_immobile` 阶段。
3. 用它训练 detector 和 temporal。
4. replay 验证必须达到 confirmed。

### 问题 4：降低阈值会导致 safe 视频误报

高召回阈值搜索显示，降低阈值后 `scene_safe_dryrun.mp4` 会出现 confirmed false positive。

这说明：

1. 不能靠阈值解决召回。
2. 需要 hard-negative 训练。
3. 需要 lying/sitting/bending/safe 动作和 fall 的区分能力。

要解决：

将 `scene_safe_dryrun.mp4` 和类似动作加入 hard-negative 训练集。

### 问题 5：YOLO26 CPU probe 还不如旧模型

当前新 YOLO26 detector 只是 CPU probe/refine，验证指标低于旧 detector。

这不代表 YOLO26 不行，而是说明：

1. 当前训练轮数太少。
2. 数据不够贴合。
3. 缺少 GPU 全量训练。
4. 还没有做 hard-negative mining 后的二次训练。

要解决：

在 CUDA 环境运行：

```text
fall_detection_model_bundle/v3_upgrade_lab/run_full_gpu_training_v3.ps1
```

## 5. 为什么现在不能直接替换

当前不能替换的原因很明确：

1. V3 detector 指标低于旧 detector。
2. 私有正样本还不能 confirmed。
3. 降阈值会造成 hard-negative confirmed false positive。
4. 当前导出包门禁未通过。
5. 当前训练只是 CPU probe，不是完整 CUDA 训练。

如果现在强行替换，会导致：

```text
真实跌倒仍可能只停在 suspected
安全动作可能误报 confirmed
系统整体效果可能低于现有模型
```

因此当前生产应保持：

```env
FALL_DETECTION_MODEL_REGISTRY_PATH=
FALL_DETECTION_PROFILE=private_scene_fusion_v2
```

## 6. 接下来应该怎么做

### 第一步：补数据

按：

```text
fall_detection_model_bundle/v3_upgrade_lab/manifests/retraining_manifest.v3.csv
fall_detection_model_bundle/v3_upgrade_lab/reports/data_collection_plan.v3.md
```

补充授权视频和标注。

最低目标：

```text
每个主要场景至少 8 段正样本
每类困难负样本至少 6 段
```

### 第二步：每个视频补 sidecar JSON

示例：

```json
{
  "label": "fall_transition",
  "kind": "positive",
  "scene_type": "living_room_far_view",
  "segment_start_s": 2.4,
  "segment_end_s": 6.8,
  "target_user_id": "elder_demo_001",
  "camera_id": "CAMERA-192.168.8.254",
  "lighting": "normal",
  "distance_level": "far",
  "occlusion_level": "partial",
  "multi_person": false,
  "target_visible": true,
  "authorized_for_training": true
}
```

### 第三步：切换 CUDA 环境

确认 CUDA 可用：

```powershell
conda run -n health python -c "import torch; print(torch.cuda.is_available())"
```

必须输出：

```text
True
```

### 第四步：运行全量 GPU 训练流水线

```powershell
powershell -ExecutionPolicy Bypass -File .\fall_detection_model_bundle\v3_upgrade_lab\run_full_gpu_training_v3.ps1
```

该脚本会执行：

```text
导入数据
构建 scene manifest
训练 YOLO26s fall detector
跑 replay matrix
挖 hard negatives
生成 retraining manifest
搜索 fusion 权重
评估 VLM review
生成 replacement gate
导出 candidate package
```

### 第五步：检查门禁

查看：

```text
fall_detection_model_bundle/v3_upgrade_lab/reports/replacement_gate_report.v3.md
```

必须变成：

```text
Promotable now: true
```

并且：

```json
"promotion_gate_passed": true
```

才可以替换。

## 7. 替换方式

门禁通过后，才允许配置：

```env
FALL_DETECTION_MODEL_REGISTRY_PATH=D:\Program\health(5-12)\fall_detection_model_bundle\v3_upgrade_lab\exports\promoted\configs\model_registry.v3.promoted.yaml
FALL_DETECTION_PROFILE=fall_v3_final_promoted
```

如果出现问题，回滚：

```env
FALL_DETECTION_MODEL_REGISTRY_PATH=
FALL_DETECTION_PROFILE=private_scene_fusion_v2
```

回滚说明也已导出：

```text
fall_detection_model_bundle/v3_upgrade_lab/exports/promoted/rollback_to_private_scene_fusion_v2.md
```

## 8. 当前状态一句话总结

当前已经完成了 V3 升级框架、候选模型下载、数据同步、CPU 训练、replay 验证、失败挖掘、再训练清单、采集计划和 blocked 导出包。

但是 V3 目前 **还没有达到可替换生产模型的门槛**。真正的下一步是补充授权场景数据，并在 CUDA 环境跑全量训练与回放门禁，直到 `promotion_gate_passed=true`。
