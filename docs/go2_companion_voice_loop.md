# Go2 小康对话与语音闭环 V1.1

## 目标

V1 已打通一轮自然语音交互：

```text
音频文件
  → Qwen ASR
  → 小康文本对话
  → Qwen TTS
  → 返回 WAV 音频
```

V1.1 新增不依赖 Go2 硬件的文本对话入口，把当前老人健康数据和
QWeather 实时天气作为可信上下文传给小康。动作规划、导航和真实
follow 仍不在本阶段范围内。

语音接口也支持相同的可选上下文。提供 `elder_id` 后，链路变为：

```text
音频文件
  → Qwen ASR
  → 当前老人健康数据 + QWeather
  → 小康文本对话
  → Qwen TTS
  → 返回 WAV 音频和上下文来源
```

不提供 `elder_id` 时仍按 V1 普通语音对话运行，保持旧调用兼容。

`/voice-turn` 接收的是短音频文件，因此使用 `qwen3-asr-flash` HTTP 文件
识别模型。`qwen3-asr-flash-realtime-*` 只用于 WebSocket 实时音频流，
不能传给文件识别接口。当前适配器只作用于 Go2 Companion，不修改项目中
其他实时语音模块。

## 接口

### 状态

```http
GET /api/v1/go2-companion/status
```

返回 ASR、LLM、TTS 的配置状态和模型，以及 Go2 麦克风、扬声器接入状态。

### 健康与天气联动文本对话

```http
POST /api/v1/go2-companion/text-turn
Content-Type: application/json
```

请求字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `elder_id` | string | 是 | 老人标识，用于读取老人和设备绑定关系 |
| `text` | string | 是 | 老人的文本输入 |
| `session_id` | string | 否 | 对话会话标识；默认使用 `elder_id` |
| `device_mac` | string | 否 | 指定老人名下设备；省略时使用默认绑定设备 |
| `location_hint` | string | 否 | 位置展示提示，不作为 QWeather 鉴权参数 |

请求示例：

```json
{
  "elder_id": "elder01_02",
  "device_mac": "53:57:08:00:00:01",
  "session_id": "demo-context",
  "text": "我想出去散步。"
}
```

返回新增的数据：

| 字段 | 说明 |
|---|---|
| `reply` | 小康结合上下文生成的 2–3 句回复 |
| `context.health` | 健康风险、数据新鲜度、跌倒和 SOS 状态 |
| `health_metrics` | 当前心率、血氧、体温、血压、步数和健康分 |
| `context.environment` | 天气、温度、湿度、风力及 `qweather/mock` 来源 |
| `context.robot` | 当前机器人在线和运动许可边界 |

健康数据来自现有实时数据流；天气由 `WEATHER_PROVIDER` 选择 QWeather
或 Mock。QWeather 调用失败时仍会自动降级，但响应中的
`context.environment.provider` 会明确显示实际来源，避免把演示天气误称为
实时天气。

小康当前使用 `qwen3.5-flash` 时显式关闭深度思考模式。陪伴问答只需要基于
已提供事实生成 2–3 个短句，关闭思考可以降低语音交互等待时间，也避免为
简单健康和天气提醒消耗额外推理 Token。

### 单轮语音

```http
POST /api/v1/go2-companion/voice-turn
Content-Type: multipart/form-data
```

请求字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `file` | audio file | 是 | WAV、MP3 或 PCM；最大 10 MiB |
| `session_id` | string | 是 | 对话会话标识，用于隔离不同老人或演示会话 |
| `voice` | string | 否 | Qwen TTS 音色，默认 `Serena` |
| `elder_id` | string | 否 | 提供后启用健康和天气上下文 |
| `device_mac` | string | 否 | 指定老人名下设备；需与 `elder_id` 对应 |
| `location_hint` | string | 否 | 位置展示提示 |

返回字段：

| 字段 | 说明 |
|---|---|
| `transcript` | ASR 转写文本 |
| `reply` | 小康回复文本 |
| `audio_b64` / `audio_url` | TTS 生成的 WAV 音频 |
| `asr_provider` | ASR Provider |
| `llm_provider` / `llm_model` | 对话模型信息 |
| `tts_provider` / `tts_voice` | TTS Provider 和音色 |
| `grounded` | 是否已经使用健康与天气上下文 |
| `context` | 联动时返回健康风险、天气来源、位置和机器人能力边界 |
| `health_metrics` | 联动时返回实时监测值；旧调用中为 `null` |
| `playback` | 客户端播放和 Go2 播放边界 |

示例：

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/v1/go2-companion/voice-turn `
  -F "file=@sample.wav;type=audio/wav" `
  -F "session_id=demo-elder-001" `
  -F "voice=Serena" `
  -F "elder_id=elder01_02" `
  -F "device_mac=53:57:08:00:00:01" `
  -F "location_hint=南京"
```

## 当前硬件边界

当前仓库没有经过验证的 Go2 麦克风采集或扬声器播放协议。因此接口会返回：

```json
{
  "playback": {
    "mode": "response_only",
    "go2_status": "not_configured",
    "ready_for_client_playback": true
  }
}
```

这表示语音音频已经生成，可由调用端播放；不表示 Go2 已经播放。接入真机前，需要确认 Go2 音频 SDK、网关端点、采样率、编码格式、停止播放和故障回执。

截至 2026-07-29 的官方资料核对结果：

- Unitree 官方 Python SDK README 对 Go2 公开说明的是 `VuiClient` 音量与灯光控制，没有给出 Go2 音频文件播放示例；
- 官方仓库中的 `AudioClient` 当前位于 `unitree_sdk2py/g1/audio`；
- 官方仓库仍有一个未答复的 Go2 音频文件播放问题。

因此当前实现不复用 G1 AudioClient，也不把 VuiClient 音量控制误认为音频播放。参考：

- <https://github.com/unitreerobotics/unitree_sdk2_python>
- <https://github.com/unitreerobotics/unitree_sdk2_python/tree/master/unitree_sdk2py/g1/audio>
- <https://github.com/unitreerobotics/unitree_sdk2_python/issues/154>

## 兼容性与影响

- V1.1 新增 `/api/v1/go2-companion/text-turn`，没有删除或修改现有语音接口字段。
- `/voice-turn` 只新增可选表单字段和响应字段；不提供 `elder_id` 时，ASR、普通小康对话和 TTS 行为与 V1 一致。
- 当前没有前端页面依赖新接口，既有 Vue、Flutter、健康智能体和 Go2 任务链保持兼容。
- 文本接口只生成回复，不执行机器人动作、不联系家属、不写入数据库。
- 演示时可以上传一段老人语音并播放返回的 WAV；必须明确说明声音由调用端播放，而不是真实 Go2 扬声器。
- 不修改数据库、导航、follow、Robot Gateway 运动接口或比赛告警主流程。

## 测试

```powershell
C:\Users\Test1\.conda\envs\health\python.exe -m pytest tests/test_go2_companion_voice.py tests/test_go2_companion_context.py tests/test_qwen_file_asr_service.py -q
```

自动化测试使用 Mock ASR、Qwen 和 TTS，不访问真实 DashScope，也不声称完成真机音频验证。单独的运行态验收可以使用已配置的 QWeather 和 Qwen，但不得输出 API Key。

## 人格

小康使用独立的语音人格：

- 温和、自然，面向老人；
- 每次回答 2 到 3 个短句；
- 不虚构健康、天气或机器人能力；
- 不进行医学诊断；
- 不声称已经执行机器人动作。
