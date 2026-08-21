# 老人端 Omni 文字流式接口

## 接口用途

老人端上传一段语音后，服务端在模型生成过程中交错返回文字和 PCM 音频分片。Android 老人端使用系统 `AudioTrack` 连续播放；模型输出结束后仍返回完整 WAV，供不支持 PCM 流播放的平台兜底。该接口只改变传输方式，不改变健康上下文、老人端提示词或模型配置。

原接口 `POST /api/v1/omni/analyze` 保留，继续返回聚合 JSON，旧版本客户端不受影响。

## 请求

```text
POST /api/v1/omni/analyze/stream
Content-Type: multipart/form-data
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---:|---|---|
| `file` | file | 是 | 无 | 支持 WAV、MP3、M4A、AAC、MP4、AMR、3GP |
| `prompt` | string | 否 | 老人端简短健康回答提示词 | 用户附加要求 |
| `role` | string | 否 | `elder` | 调用方角色 |
| `device_mac` | string | 否 | `null` | 用于读取当前设备健康上下文 |

## 响应

```text
Content-Type: application/x-ndjson
Cache-Control: no-cache
```

每行是一个独立 JSON 事件，正常顺序为：

```json
{"type":"answer.delta","delta":"您好，"}
{"type":"audio.delta","delta":"...","sequence":0,"encoding":"pcm_s16le","sample_rate":24000,"channels":1}
{"type":"answer.delta","delta":"今天状态比较平稳。"}
{"type":"audio.delta","delta":"...","sequence":1,"encoding":"pcm_s16le","sample_rate":24000,"channels":1}
{"type":"audio.completed","audio_b64":"...","audio_pcm_b64":"...","audio_url":"data:audio/wav;base64,...","audio_sample_rate":24000,"fmt":"wav","voice":"Chelsie"}
{"type":"answer.completed","ok":true,"answer":"您好，今天状态比较平稳。","provider":"dashscope-compatible/qwen2.5-omni-7b","model":"qwen2.5-omni-7b","voice":"Chelsie"}
```

### 事件字段

| 事件 | 字段 | 说明 |
|---|---|---|
| `answer.delta` | `delta` | 本次新增的文字片段，客户端应直接追加 |
| `audio.delta` | `delta`、`sequence`、`encoding`、`sample_rate`、`channels` | Base64 PCM16 音频片段；片段按事件顺序拼接，单个 `delta` 不保证可独立 Base64 解码 |
| `audio.completed` | `audio_b64`、`audio_pcm_b64`、`audio_url`、`audio_sample_rate`、`fmt`、`voice` | 完整音频，用于不支持 PCM 流播放的平台和失败兜底 |
| `answer.completed` | `ok`、`answer`、`provider`、`model`、`voice` | 完整文字和模型元数据 |
| `error` | `ok=false`、`error` | 流启动后的模型或服务错误 |

音频不可用时可能没有 `audio.delta` 和 `audio.completed`，客户端仍应保留已经收到的文字。上传格式不支持或文件过小时，在流启动前返回 HTTP 400；模型调用在响应头发出后失败时，HTTP 状态保持 200，并以 `error` 事件结束。

## 兼容性与影响

- 新增接口，不删除或修改旧接口字段。
- 老版本 Flutter、Web 和其他调用方可以继续使用 `/api/v1/omni/analyze`。
- Android Flutter 客户端能够实时消费文字和 PCM 音频流，并通过系统 `AudioTrack` 连续播放。
- Windows Flutter 客户端能够实时显示文字，但本阶段使用完整 WAV 播放兜底。
- Flutter Web 使用默认 Dio 浏览器适配器时会在完整响应到达后再解析 NDJSON，接口兼容但不保证逐段到达。
- 流中断时 Android 会停止并清理当前音频轨，避免残留播放。
- 不修改数据库、模型权重、健康数据结构、告警流程或比赛演示主路径。

## 测试方式

```powershell
curl.exe -N -X POST "http://127.0.0.1:8000/api/v1/omni/analyze/stream" `
  -F "file=@sample.wav;type=audio/wav" `
  -F "role=elder" `
  -F "device_mac=AA:BB:CC:DD:EE:FF"
```

服务测试：

```powershell
conda run -n health python -m pytest tests/test_omni_logic.py tests/test_omni_stream_api.py -q
```
