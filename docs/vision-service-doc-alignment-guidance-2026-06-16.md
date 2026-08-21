# Vision Service 文档对齐改写指引

## 1. 文档目的

本文档用于给 Vision Service / 跌倒检测模块一侧提供一份明确、可执行的改写方向，确保其对外接口文档与当前主系统真实实现、真实边界、真实联调基线保持一致。

这份文档的核心目标不是让 Vision Service 回退代码能力，而是：

1. 保留已经实现的增强能力
2. 但在文档中准确区分“当前主系统默认依赖的基础契约”和“Vision Service 额外提供的可选增强能力”
3. 避免主系统、Vision Service、联调人员因为文档表述不一致而产生误解

一句话总结：

```text
这次需要改的是文档定位，不是主系统已实现接口代码本身
```

## 2. 当前主系统真实基线

先明确当前主系统的真实现状。这一部分应作为 Vision Service 文档的前提假设。

### 2.1 主系统当前角色

主系统当前已经明确为：

- Vision Service Consumer
- 服务消费侧状态整合者
- 告警接收与业务映射方

主系统当前不是：

- RTSP Owner
- Camera Runtime Owner
- Vision Pipeline Owner

因此：

- RTSP、拉流、解码、检测、姿态、跌倒判定、WebRTC 属于 Vision Service
- 主系统只消费 Vision Service 输出的状态与结果

### 2.2 主系统当前默认依赖的基础契约

Vision Service 文档里应该把下面四个接口写成“当前主系统默认依赖的基础契约”：

```http
GET /healthz
GET /status?camera_id=camera_01
GET /stream/source?camera_id=camera_01
GET /integration/results/{camera_id}/latest
```

这是当前主系统最真实、最稳定、最应该被强调的接口基线。

### 2.3 主系统当前对外暴露的代理接口

主系统内部已经通过代理层对外暴露了：

```http
GET /api/v1/vision/health
GET /api/v1/vision/status
GET /api/v1/vision/source
GET /api/v1/vision/results/latest
```

这组接口是主系统自己暴露给前端或其他主系统内部调用方的接口。

因此 Vision Service 文档必须明确：

- 这四个 `/api/v1/vision/*` 是主系统接口
- Vision Service 不需要直接实现这四个路径
- Vision Service 只需要提供底层真实源接口：
  - `/healthz`
  - `/status`
  - `/stream/source`
  - `/integration/results/{camera_id}/latest`

### 2.4 主系统当前跌倒告警接收基线

如果 Vision Service 采用“确认跌倒后主动推送给主系统”的模式，主系统当前稳定可用的接收接口是：

```http
POST /api/v1/video-bridge/fall-events
```

这条链路目前已经是真实联调通过的主系统能力，文档里可以明确保留。

## 3. 这次反馈的核心结论

Vision Service 那份 `main_system_interface_status_2026-06-16.md` 里，主要问题不在接口功能本身，而在以下四个层面：

1. 把“可选增强能力”写成了“主系统当前默认契约”
2. 把 Vision Service 自己的部署变量写得像主系统变量
3. 把 Vision Service 仓库的测试表述得像主系统仓库测试
4. 把 RTSP/源细节写得过重，弱化了主系统真正消费的状态字段

这四点都需要改。

## 4. 必须遵守的改写原则

Vision Service 文档改写时，建议严格遵守以下原则。

### 4.1 基础契约和可选增强能力必须拆开写

必须分成两层：

#### 第一层：当前主系统默认依赖的基础契约

只写：

```http
GET /healthz
GET /status
GET /stream/source
GET /integration/results/{camera_id}/latest
```

以及必要时补充：

```http
POST /api/v1/video-bridge/fall-events
```

#### 第二层：Vision Service 额外提供的可选增强能力

单独列成“可选增强能力”一节，写清楚：

```http
GET /integration/fall-alerts/{camera_id}/poll
```

以及：

```text
/status.polling_alert
```

但必须加粗说明：

```text
这些能力当前不是主系统默认契约
主系统当前未接入
如果未来接入，可简化弹窗判断逻辑
```

### 4.2 Vision Service 变量和主系统变量必须分开写

这一点非常关键。

文档中不能把：

```text
VISION_SERVICE_PUBLIC_BASE_URL
```

写成主系统当前配置项。

正确做法是拆成两组：

#### A. Vision Service 侧变量

这组是 Vision Service 自己的部署变量，例如：

- `VISION_SERVICE_PUBLIC_BASE_URL`
- 其他仅属于 Vision Service 进程的变量

#### B. 主系统侧变量

这组必须写主系统真实存在、真实使用的变量名。当前主系统使用的是：

- `VISION_SERVICE_BASE_URL`
- `VISION_SERVICE_CAMERA_ID`
- `VISION_SERVICE_POLL_ENABLED`
- `VISION_SERVICE_TIMEOUT_SECONDS`
- `VISION_SERVICE_PUSH_TOKEN`

如果文档是发给主系统团队或联调人员，必须明确写：

```text
上面两组变量分别属于不同服务，不能混用
```

### 4.3 测试结论必须说明测试发生在哪个仓库

以后任何“测试已通过”都必须区分来源。

建议统一改成这种写法：

#### Vision Service 仓库测试

```text
以下测试在 Vision Service 仓库执行通过：
...
```

#### 主系统仓库测试

```text
以下测试或联调验证在主系统仓库完成：
...
```

绝对不要继续写成一种让人误解为：

```text
这些测试是在主系统仓库里执行通过
```

如果当前主系统仓库并不存在对应测试文件，就不要把这些文件名写成“主系统已覆盖测试”。

### 4.4 RTSP 相关字段应降级为调试字段

在 `/stream/source` 或 `/status` 文档说明里，RTSP masked URL 可以保留，但必须降级为：

- 调试字段
- 排障字段
- 非主契约核心字段

文档真正应该强调的是主系统当前真实消费的字段：

- `camera_id`
- `stream_state`
- `frame_age_ms`
- `service_state`
- `camera_lost`
- `capture_stale`
- `fall_state`
- `risk`
- `risk_level`
- `fall_prob`
- `fall_score`
- `incident_id`
- `snapshot_url`

## 5. 建议如何重写现有文档

以下内容可以作为对 `main_system_interface_status_2026-06-16.md` 的直接改写指导。

## 5.1 标题建议

建议把文档标题从类似：

```text
主系统接口状态说明
```

改成更精确的版本，例如：

```text
Vision Service 与主系统当前对接基线说明
```

或者：

```text
Vision Service 面向主系统的接口基线与可选增强能力说明
```

这样能避免别人误以为本文就是“主系统当前正式接口契约全文”。

## 5.2 第一节“当前结论”建议改写

这一节建议写成：

### 当前结论

- 当前主系统已支持以“主系统主动读取 Vision Service 状态与结果”的模式接入
- 当前主系统默认依赖的基础契约是：
  - `GET /healthz`
  - `GET /status`
  - `GET /stream/source`
  - `GET /integration/results/{camera_id}/latest`
- 当前主系统也支持“Vision Service 确认跌倒后主动 POST 到主系统”的链路：
  - `POST /api/v1/video-bridge/fall-events`
- Vision Service 当前额外实现了若干增强能力，例如：
  - `GET /integration/fall-alerts/{camera_id}/poll`
  - `/status.polling_alert`
- 这些增强能力当前不是主系统默认依赖契约，但未来如果接入，可进一步简化主系统弹窗判断逻辑

## 5.3 “是否全部可用”建议改写

不要写成笼统的“全部可用”。

建议改成两层：

### 接口能力层

可以写：

- Vision Service 基础接口能力已具备
- 可选增强接口能力也已具备

### 主系统当前接入层

必须写：

- 主系统当前默认接入的是基础契约
- 可选增强能力当前尚未成为主系统默认接入基线

这样表述就不会误导别人以为主系统已经依赖 `poll` 接口。

## 5.4 “接口清单”建议重构

建议把接口清单拆成三节。

### A. 当前主系统默认依赖的基础接口

只列：

```http
GET /healthz
GET /status?camera_id=...
GET /stream/source?camera_id=...
GET /integration/results/{camera_id}/latest
```

### B. 主系统可选接入的增强接口

单独列：

```http
GET /integration/fall-alerts/{camera_id}/poll
```

以及：

```text
/status.polling_alert
```

并明确说明：

```text
当前主系统未默认接入
若未来接入，可减少主系统本地弹窗去重与状态判断逻辑
```

### C. 兼容保留或联调用接口

例如：

- `GET /fall-events/snapshots/{filename}`
- `POST /alerting/simulation/send-once`

并明确标注：

```text
用于联调、演示或兼容验证
不是主系统当前基础契约的一部分
```

## 5.5 `/status` 一节建议怎么写

这一节不要把 `polling_alert` 当成主契约核心字段。

建议拆分：

### `/status` 主契约重点字段

- `camera_id`
- `connected`
- `stream_state`
- `frame_age_ms`
- `service_status`
- `latest_result.fall_state`
- `latest_result.risk_level`
- `latest_result.fall_prob`
- `latest_result.incident_id`
- `latest_result.snapshot_url`

### `/status` 可选增强字段

- `polling_alert.should_popup`
- `polling_alert.incident_id`
- `polling_alert.snapshot_url`

并明确注明：

```text
可选增强字段当前不是主系统默认依赖项
```

## 5.6 `/stream/source` 一节建议怎么写

这一节建议加一段说明：

```text
RTSP masked URL、dual stream 等字段可作为调试信息保留，
但主系统当前默认关注的是流是否在线、帧是否新鲜、当前 source 状态是否稳定，
而不是把 RTSP 本身作为主系统 future architecture center。
```

建议强调字段：

- `camera_id`
- `running`
- `main_stream_state`
- `analysis_stream_state`
- `main_connected`
- `analysis_connected`
- `main_frame_age_ms`
- `analysis_frame_age_ms`
- `message`

而把：

- `main_rtsp_url_masked`
- `analysis_rtsp_url_masked`

降级为调试字段。

## 5.7 “与主系统文档的对齐情况”建议怎么写

建议改成三块：

### 已对齐的基础契约

- `GET /healthz`
- `GET /status`
- `GET /stream/source`
- `GET /integration/results/{camera_id}/latest`
- `incident_id`
- `snapshot_url`
- `fall_state / risk / fall_prob / metadata`

### Vision Service 额外提供的增强能力

- `GET /integration/fall-alerts/{camera_id}/poll`
- `/status.polling_alert`

### 当前仍需主系统自行决定是否接入的能力

明确写：

```text
以上增强能力当前不是主系统正式基线的一部分
是否接入由主系统后续版本决定
```

## 5.8 “是否需要主系统修改”建议怎么写

这一节要避免写成“主系统必须修改”。

建议改成：

### 不修改也能工作

如果主系统继续按当前基线工作，则：

- 只依赖 `/healthz`
- `/status`
- `/stream/source`
- `/integration/results/{camera_id}/latest`

即可完成当前只读状态消费方案。

### 如果主系统未来愿意进一步简化弹窗逻辑

可以新增接入：

- `GET /integration/fall-alerts/{camera_id}/poll`

但这属于未来可选增强，不是当前联调前提。

## 5.9 “测试结论”建议怎么写

建议固定改成如下模板：

### Vision Service 仓库内已验证

- 以下接口、逻辑、测试已在 Vision Service 仓库完成验证：
  - ...
  - ...

### 主系统侧已联调验证

- 已与主系统完成的联调项：
  - 主系统可访问 Vision Service `/healthz`
  - 主系统可访问 `/status`
  - 主系统可访问 `/stream/source`
  - 主系统可访问 `/integration/results/{camera_id}/latest`
  - 主系统可接收 `POST /api/v1/video-bridge/fall-events`

如果要列测试命令，必须明确这些命令属于哪个仓库。

## 6. 建议 Vision Service 文档中的最终表述

下面是一段建议直接放进文档中的正式表述，可直接引用。

### 建议正式表述

```text
当前 Vision Service 面向主系统的基础契约为：

1. GET /healthz
2. GET /status?camera_id=...
3. GET /stream/source?camera_id=...
4. GET /integration/results/{camera_id}/latest

这四项构成当前主系统默认依赖的只读状态消费基线。

除此之外，Vision Service 还额外提供了若干可选增强能力，例如：

1. GET /integration/fall-alerts/{camera_id}/poll
2. /status.polling_alert

这些增强能力当前不是主系统默认依赖项，但如果未来主系统接入，可进一步简化弹窗判断、事件去重与告警展示逻辑。

如果 Vision Service 采用“确认跌倒后主动推送到主系统”的模式，则主系统当前支持：

POST /api/v1/video-bridge/fall-events

以上表述意味着：

- Vision Service 可以保留并继续演进增强能力
- 但对主系统当前正式基线的描述，必须以基础契约为准
```

## 7. 本轮不建议做的事

这次不建议 Vision Service 做以下动作：

1. 不要要求主系统立即改成必须依赖 `poll` 接口
2. 不要把 `/status.polling_alert` 写成主系统当前正式契约字段
3. 不要把 Vision Service 自己的部署变量混写成主系统配置项
4. 不要在主系统对接文档里把 RTSP 字段继续写成中心地位
5. 不要把 Vision Service 仓库测试写成主系统仓库测试

## 8. 本轮建议立即执行的修改清单

建议 Vision Service 一侧立即执行以下修改：

1. 修改 `main_system_interface_status_2026-06-16.md` 的标题与定位
2. 将基础契约与可选增强能力拆成两个章节
3. 把 `GET /integration/fall-alerts/{camera_id}/poll` 降级为“可选增强接口”
4. 把 `/status.polling_alert` 降级为“可选增强字段”
5. 将配置拆分为：
   - Vision Service 侧变量
   - 主系统侧变量
6. 将测试说明改为：
   - Vision Service 仓库验证
   - 主系统侧联调验证
7. 将 `/stream/source` 中 RTSP masked URL 改写为调试字段

## 9. 最终结论

这次主系统的反馈，本质上不是否定 Vision Service 已实现的能力，而是要求文档回到“当前主系统真实依赖基线”。

因此，Vision Service 最合适的改法是：

- 保留增强能力
- 但下调其在文档中的契约级别
- 用基础契约作为主叙述
- 用增强能力作为未来可选优化

一句话定稿：

```text
代码能力可以更强，但对主系统的正式文档必须先对齐当前主系统真实基线
```
