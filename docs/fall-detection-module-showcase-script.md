# 跌倒检测模块技能展示代码与话术

## 一、核心代码定位

当前脚本 `run_fall_media_demo.py` 里真正和跌倒检测模型强相关的核心不是参数解析、画框或 JSON 保存，而是下面三段：

1. 模型调用核心：`FallFrameTestService.detect_frame()`
2. 模型融合评分核心：`FallFrameTestService._score()` 和 `_resolve_status()`
3. 视频事件判断核心：`FallEventStateMachine.apply()`

对应文件：

- `D:\Program\410health_new\health1\backend\services\fall_frame_test_service.py`
- `D:\Program\410health_new\health1\backend\services\fall_event_state_machine.py`
- `D:\Program\410health_new\health1\scripts\run_fall_media_demo.py`
- `D:\Program\410health_new\health1\scripts\showcase_fall_detection_module.py`

## 二、展示代码 1：模型加载与单帧推理

```python
service = FallFrameTestService(get_settings())
warmup = service.warmup(imgsz=640, posture_imgsz=384)

result = service.detect_frame(
    frame,
    include_annotated_image=False,
    imgsz=640,
    posture_imgsz=384,
)
```

**讲解话术：**

接下来展示跌倒检测模块的核心推理过程。
我首先创建 `FallFrameTestService`，它内部会加载两个本地模型：一个是用于人体跌倒目标定位的 YOLO 检测模型，另一个是用于判断人体姿态风险的 YOLO 姿态分类模型。

在推理时，系统将每一帧图像传入 `detect_frame()`。这个函数不会只输出一个简单的“是否跌倒”，而是会返回检测框、类别置信度、姿态标签、姿态分数、综合跌倒分数以及报警等级，为后续视频事件判断提供基础数据。

## 三、展示代码 2：目标检测 + 姿态分类

```python
detections = self._detect_objects(frame, imgsz=imgsz, posture_imgsz=posture_imgsz)
scores = self._score(detections)
status = self._resolve_status(scores)
```

**讲解话术：**

这里是跌倒检测模块最关键的三步。

第一步，系统调用 YOLO 检测模型，在画面中找到人体或疑似跌倒区域，并得到检测框和类别置信度。

第二步，系统会把检测框中的人体区域裁剪出来，再送入姿态分类模型，判断当前人体姿态是否属于高风险姿态。

第三步，系统不是单独相信某一个模型输出，而是把检测模型分数、姿态模型分数、躺卧类别分数以及人体框宽高比等几何特征融合成一个 `fall_score`。这样做的目的，是减少单一模型在光照、遮挡、角度变化下产生的误判。

## 四、展示代码 3：跌倒风险融合评分

```python
fall = max(detector, prone, posture * 0.78, heuristic)

if scores["detector"] >= 0.35 or scores["fall"] >= 0.72:
    return "fall"
if scores["fall"] >= 0.42 or scores["prone"] >= 0.35 or scores["heuristic"] >= 0.42:
    return "suspected"
return "normal"
```

**讲解话术：**

这一段是当前跌倒检测模块的风险融合逻辑。

`detector` 表示目标检测模型直接判断为跌倒的置信度；`posture` 表示姿态分类模型判断为风险姿态的概率；`prone` 用来处理躺卧类目标；`heuristic` 则根据人体框的宽高比和面积比例补充判断。

最终系统取这些信号中的最大风险值作为 `fall_score`。当分数超过高风险阈值时，状态会被判定为 `fall`；当分数处于中间区间时，系统先标记为 `suspected`，也就是疑似跌倒，等待后续视频帧继续确认。

## 五、展示代码 4：视频时序事件判断

```python
smoother = FallEventStateMachine()

display_result = smoother.apply(
    last_result,
    frame_index=frame_index,
    time_s=frame_index / fps,
    fps=fps,
)
```

**讲解话术：**

单帧检测容易出现抖动，例如某一帧是 `fall`，下一帧又变成 `normal`。这在真实视频中会造成报警不稳定。

因此我在模型后面增加了一个跌倒事件状态机。它会观察最近多帧的检测结果，把单帧输出升级成完整的视频事件状态，状态流转包括：

```text
normal -> suspected -> falling -> fallen -> recovery -> normal
```

当连续多帧都出现高风险信号时，系统才会从疑似状态进入跌倒状态；当短时间内模型分数下降时，状态机也不会立刻取消报警，而是会保留一段时间，避免检测框短暂丢失导致事件中断。

## 六、展示代码 5：报警等级输出

```python
alarm = {
    "level": level,
    "should_alert": level in {"danger", "critical"},
    "reason": state,
    "event_duration_s": round(event_duration_s, 3),
    "max_fall_score": round(max_score, 4),
}
```

**讲解话术：**

在状态机输出事件状态后，系统会继续生成报警等级。

如果只是短暂风险，报警等级是 `watch` 或 `warning`；如果已经确认跌倒并持续一段时间，报警等级会升级为 `danger`；如果持续时间更长或者最高跌倒分数很高，则升级为 `critical`。

这样前端和后端业务逻辑就不需要直接理解模型细节，只需要根据 `alarm.level` 和 `should_alert` 判断是否弹窗、是否入库、是否通知人工处理。

## 七、完整展示话术

接下来展示当前项目中的跌倒检测模块。

我将本地视频逐帧输入到模型中，首先由 YOLO 跌倒检测模型完成人体区域和跌倒类别的定位；随后，系统会把人体框裁剪出来，送入姿态分类模型，进一步判断人体是否处于躺卧、倾倒等高风险姿态。

为了避免只依赖单一模型导致误判，我在代码中融合了四类信号：检测模型置信度、姿态分类分数、躺卧类别分数以及人体框宽高比几何特征。系统会根据这些信号计算综合跌倒分数 `fall_score`，并先给出单帧级别的 `normal`、`suspected` 或 `fall` 判断。

但是视频检测不能只看单帧。人在跌倒过程中会经历站立、失衡、倒地、保持倒地等连续动作，如果只看一帧，很容易出现状态跳变。因此我又加入了跌倒事件状态机，将逐帧模型结果升级为事件级判断。

状态机的核心流程是：

```text
normal -> suspected -> falling -> fallen -> recovery -> normal
```

也就是说，系统会先观察风险帧是否连续出现，再决定是否进入跌倒事件；一旦进入跌倒事件，即使中间个别帧检测分数下降，也会通过保持机制维持事件连续性，从而减少画面抖动和检测框丢失带来的误报、漏报。

最终，系统会输出检测后的视频、每一帧的检测框、跌倒分数、事件状态、报警等级以及 JSON 结构化结果。这样既可以用于模型效果展示，也可以用于后续评估集构建、误检样本收集和模型继续训练。

## 八、运行展示命令

```powershell
C:\Users\YANG\.conda\envs\fall-media-demo\python.exe D:\Program\410health_new\health1\scripts\showcase_fall_detection_module.py D:\Program\410health_new\health1\data\fall_media_demo\inputs\fall_demo_01_input.mp4 --max-frames 160
```

如果要生成带检测框的视频，使用：

```powershell
C:\Users\YANG\.conda\envs\fall-media-demo\python.exe D:\Program\410health_new\health1\scripts\run_fall_media_demo.py D:\Program\410health_new\health1\data\fall_media_demo\inputs\fall_demo_01_input.mp4 -o D:\Program\410health_new\health1\data\fall_media_demo\fall_demo_01_detected_showcase.mp4 --save-frame-records --save-review-frames
```
