<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import {
  Activity,
  Bot,
  Check,
  CircleAlert,
  CloudSun,
  FileAudio,
  HeartPulse,
  LoaderCircle,
  MapPin,
  MessageCircleMore,
  Play,
  Send,
  ShieldCheck,
  Sparkles,
  Upload,
  Volume2,
} from "lucide-vue-next";
import {
  ApiError,
  api,
  type CareDirectory,
  type Go2CompanionContext,
  type Go2CompanionHealthMetrics,
  type Go2CompanionStatus,
} from "../api/client";
import PageHeader from "../components/layout/PageHeader.vue";

type InteractionMode = "text" | "voice";

const scenarioPrompts = [
  "我今天身体怎么样？",
  "南京今天天气怎么样？",
  "我现在想出去散步，可以吗？",
];

const directory = ref<CareDirectory | null>(null);
const serviceStatus = ref<Go2CompanionStatus | null>(null);
const selectedElderId = ref("");
const selectedDeviceMac = ref("");
const locationHint = ref("");
const mode = ref<InteractionMode>("text");
const question = ref(scenarioPrompts[2]);
const audioFile = ref<File | null>(null);
const transcript = ref("");
const reply = ref("");
const context = ref<Go2CompanionContext | null>(null);
const healthMetrics = ref<Go2CompanionHealthMetrics | null>(null);
const responseAudioUrl = ref("");
const providerTrace = ref<string[]>([]);
const loadingDirectory = ref(true);
const submitting = ref(false);
const errorMessage = ref("");
const sessionId = `dashboard-${Date.now().toString(36)}`;

const selectedElder = computed(() =>
  directory.value?.elders.find((item) => item.id === selectedElderId.value) ?? null,
);

const deviceOptions = computed(() => {
  const elder = selectedElder.value;
  if (!elder) return [];
  return elder.device_macs?.length ? elder.device_macs : elder.device_mac ? [elder.device_mac] : [];
});

const configuredStageCount = computed(() => {
  const status = serviceStatus.value;
  if (!status) return 0;
  return [status.asr_configured, status.llm_configured, status.tts_configured].filter(Boolean).length;
});

const canSubmitText = computed(() =>
  Boolean(selectedElderId.value && selectedDeviceMac.value && question.value.trim() && !submitting.value),
);

const canSubmitVoice = computed(() =>
  Boolean(selectedElderId.value && selectedDeviceMac.value && audioFile.value && !submitting.value),
);

const riskLabel = computed(() => ({
  low: "低风险",
  medium: "中风险",
  high: "高风险",
  unknown: "待确认",
}[healthMetrics.value?.risk_level ?? "unknown"]));

const weatherLabel = computed(() => ({
  sunny: "晴",
  rain: "雨",
  windy: "大风",
  hot: "高温",
  cold: "低温",
  unknown: "待确认",
}[context.value?.environment.weather ?? "unknown"]));

watch(selectedElder, (elder) => {
  const macs = elder?.device_macs?.length ? elder.device_macs : elder?.device_mac ? [elder.device_mac] : [];
  selectedDeviceMac.value = macs[0] ?? "";
  resetResult();
});

onMounted(async () => {
  const [directoryResult, statusResult] = await Promise.allSettled([
    api.getCareDirectory(),
    api.getGo2CompanionStatus(),
  ]);

  if (directoryResult.status === "fulfilled") {
    directory.value = directoryResult.value;
    const firstTestableElder = directoryResult.value.elders.find((elder) =>
      Boolean(elder.device_macs?.length || elder.device_mac),
    );
    selectedElderId.value = firstTestableElder?.id ?? directoryResult.value.elders[0]?.id ?? "";
  } else {
    errorMessage.value = formatError(directoryResult.reason, "老人目录加载失败");
  }

  if (statusResult.status === "fulfilled") {
    serviceStatus.value = statusResult.value;
  }
  loadingDirectory.value = false;
});

function resetResult() {
  transcript.value = "";
  reply.value = "";
  context.value = null;
  healthMetrics.value = null;
  responseAudioUrl.value = "";
  providerTrace.value = [];
  errorMessage.value = "";
}

function selectScenario(prompt: string) {
  mode.value = "text";
  question.value = prompt;
}

function handleFile(event: Event) {
  const input = event.target as HTMLInputElement;
  audioFile.value = input.files?.[0] ?? null;
  errorMessage.value = "";
}

async function runTextTurn() {
  if (!canSubmitText.value) return;
  submitting.value = true;
  errorMessage.value = "";
  responseAudioUrl.value = "";
  try {
    const result = await api.runGo2CompanionTextTurn({
      elder_id: selectedElderId.value,
      device_mac: selectedDeviceMac.value,
      location_hint: locationHint.value.trim() || undefined,
      session_id: sessionId,
      text: question.value.trim(),
    });
    transcript.value = question.value.trim();
    reply.value = result.reply;
    context.value = result.context;
    healthMetrics.value = result.health_metrics;
    providerTrace.value = [
      "文本输入",
      "实时健康数据",
      result.context.environment.provider === "qweather" ? "QWeather" : "天气 Mock",
      `${result.llm_provider} · ${result.llm_model}`,
    ];
  } catch (error) {
    errorMessage.value = formatError(error, "智能体回答失败");
  } finally {
    submitting.value = false;
  }
}

async function runVoiceTurn() {
  if (!canSubmitVoice.value || !audioFile.value) return;
  submitting.value = true;
  errorMessage.value = "";
  responseAudioUrl.value = "";
  try {
    const result = await api.runGo2CompanionVoiceTurn({
      file: audioFile.value,
      elder_id: selectedElderId.value,
      device_mac: selectedDeviceMac.value,
      location_hint: locationHint.value.trim() || undefined,
      session_id: sessionId,
    });
    transcript.value = result.transcript;
    reply.value = result.reply;
    context.value = result.context;
    healthMetrics.value = result.health_metrics;
    responseAudioUrl.value = result.audio_url || (
      result.audio_b64 ? `data:audio/${result.audio_format || "wav"};base64,${result.audio_b64}` : ""
    );
    providerTrace.value = [
      `ASR · ${result.asr_provider}`,
      "实时健康数据",
      result.context?.environment.provider === "qweather" ? "QWeather" : "天气 Mock",
      `${result.llm_provider} · ${result.llm_model}`,
      `TTS · ${result.tts_provider}`,
    ];
  } catch (error) {
    errorMessage.value = formatError(error, "语音闭环执行失败");
  } finally {
    submitting.value = false;
  }
}

function formatError(error: unknown, fallback: string) {
  if (error instanceof ApiError) return error.detail || fallback;
  if (error instanceof Error) return error.message || fallback;
  return fallback;
}

function formatObservedAt(value: string | null | undefined) {
  if (!value) return "暂无时间";
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}
</script>

<template>
  <section class="page-stack companion-page">
    <PageHeader
      eyebrow="GO2 COMPANION / GROUNDED DIALOGUE"
      title="小康智能体"
      description="在不连接机器狗运动控制的前提下，验证老人语音或文本输入能否联动实时健康数据、QWeather、大模型与语音合成。"
      :meta="['人格：温和、简短、适老', '健康 + 天气真实联动', 'Go2 运动控制未接入']"
    >
      <template #actions>
        <span class="readiness" :class="{ 'is-ready': configuredStageCount === 3 }">
          <span class="readiness__dot"></span>
          {{ configuredStageCount === 3 ? "语音链路已就绪" : `语音链路 ${configuredStageCount}/3` }}
        </span>
      </template>
    </PageHeader>

    <div class="pipeline-strip" aria-label="智能体处理链路">
      <div :class="{ 'is-ready': serviceStatus?.asr_configured }">
        <FileAudio :size="17" />
        <span><small>01 / 输入</small><strong>ASR 语音识别</strong></span>
      </div>
      <div :class="{ 'is-ready': serviceStatus?.context_grounding_supported }">
        <Activity :size="17" />
        <span><small>02 / 联动</small><strong>健康 + 天气</strong></span>
      </div>
      <div :class="{ 'is-ready': serviceStatus?.llm_configured }">
        <Sparkles :size="17" />
        <span><small>03 / 理解</small><strong>Qwen 智能体</strong></span>
      </div>
      <div :class="{ 'is-ready': serviceStatus?.tts_configured }">
        <Volume2 :size="17" />
        <span><small>04 / 输出</small><strong>TTS 语音合成</strong></span>
      </div>
      <div class="is-boundary">
        <ShieldCheck :size="17" />
        <span><small>安全边界</small><strong>仅返回，不执行动作</strong></span>
      </div>
    </div>

    <div v-if="errorMessage" class="companion-alert" role="alert">
      <CircleAlert :size="19" />
      <div><strong>本次测试未完成</strong><p>{{ errorMessage }}</p></div>
    </div>

    <div class="companion-workspace">
      <aside class="context-rail">
        <header class="section-heading">
          <span><Bot :size="18" /></span>
          <div><small>TEST SUBJECT</small><h2>测试对象与数据源</h2></div>
        </header>

        <div v-if="loadingDirectory" class="inline-loading">
          <LoaderCircle :size="18" class="is-spinning" /> 正在读取老人目录…
        </div>

        <div v-else class="subject-form">
          <label>
            <span>老人</span>
            <select v-model="selectedElderId">
              <option v-for="elder in directory?.elders" :key="elder.id" :value="elder.id">
                {{ elder.name }} · {{ elder.apartment }}
              </option>
            </select>
          </label>
          <label>
            <span>健康设备</span>
            <select v-model="selectedDeviceMac" :disabled="!deviceOptions.length">
              <option v-for="mac in deviceOptions" :key="mac" :value="mac">{{ mac }}</option>
            </select>
          </label>
          <label>
            <span>天气位置（可选）</span>
            <input v-model="locationHint" placeholder="留空使用后端已配置位置" />
          </label>
        </div>

        <div class="source-list">
          <div>
            <HeartPulse :size="18" />
            <span><small>健康数据</small><strong>{{ healthMetrics?.available ? "实时数据已获取" : "等待场景运行" }}</strong></span>
            <Check v-if="healthMetrics?.available" :size="16" />
          </div>
          <div>
            <CloudSun :size="18" />
            <span><small>环境数据</small><strong>{{ context ? (context.environment.provider === "qweather" ? "QWeather 已获取" : "天气 Mock") : "等待场景运行" }}</strong></span>
            <Check v-if="context" :size="16" />
          </div>
          <div>
            <MapPin :size="18" />
            <span><small>天气位置</small><strong>{{ context ? `${context.location.city} ${context.location.area}` : "由天气配置解析" }}</strong></span>
          </div>
        </div>

        <div v-if="context && healthMetrics" class="evidence-panel">
          <div class="evidence-panel__heading">
            <span>本次联动证据</span>
            <time>{{ formatObservedAt(healthMetrics.observed_at) }}</time>
          </div>
          <dl>
            <div><dt>心率</dt><dd>{{ healthMetrics.heart_rate ?? "--" }}<small>bpm</small></dd></div>
            <div><dt>血氧</dt><dd>{{ healthMetrics.blood_oxygen ?? "--" }}<small>%</small></dd></div>
            <div><dt>健康评分</dt><dd>{{ healthMetrics.health_score ?? "--" }}<small>/ 100</small></dd></div>
            <div><dt>健康风险</dt><dd class="risk-value" :class="`is-${healthMetrics.risk_level}`">{{ riskLabel }}</dd></div>
            <div><dt>天气</dt><dd>{{ weatherLabel }}<small>{{ context.environment.temperature ?? "--" }}℃</small></dd></div>
            <div><dt>湿度</dt><dd>{{ context.environment.humidity ?? "--" }}<small>%</small></dd></div>
          </dl>
          <p>{{ context.environment.description }}{{ context.environment.suggestion ? `；${context.environment.suggestion}` : "" }}</p>
        </div>
        <div v-else class="evidence-empty">
          <Activity :size="22" />
          <p>运行一个场景后，这里会显示智能体实际读取到的健康指标和天气数据。</p>
        </div>
      </aside>

      <main class="dialogue-stage">
        <div class="dialogue-stage__header">
          <div>
            <small>LIVE SCENARIO</small>
            <h2>对话联动测试</h2>
          </div>
          <div class="mode-switch" role="tablist" aria-label="输入方式">
            <button type="button" :class="{ active: mode === 'text' }" role="tab" :aria-selected="mode === 'text'" @click="mode = 'text'">
              <MessageCircleMore :size="16" /> 文本
            </button>
            <button type="button" :class="{ active: mode === 'voice' }" role="tab" :aria-selected="mode === 'voice'" @click="mode = 'voice'">
              <Volume2 :size="16" /> 语音文件
            </button>
          </div>
        </div>

        <div class="scenario-row" aria-label="快速测试场景">
          <span>快速场景</span>
          <button v-for="prompt in scenarioPrompts" :key="prompt" type="button" @click="selectScenario(prompt)">
            {{ prompt }}
          </button>
        </div>

        <div class="conversation" aria-live="polite">
          <div v-if="!reply && !submitting" class="conversation-empty">
            <div class="companion-mark"><Bot :size="28" /></div>
            <h3>让小康基于真实上下文回答</h3>
            <p>选择老人和设备，输入问题或上传语音。回答产生后可直接核对健康指标、天气来源和模型链路。</p>
          </div>

          <template v-else>
            <div v-if="transcript" class="message message--user">
              <span>老人</span>
              <p>{{ transcript }}</p>
            </div>
            <div v-if="submitting" class="message message--agent is-thinking">
              <span><LoaderCircle :size="15" class="is-spinning" /> 小康正在联动数据</span>
              <p>正在获取健康数据和天气，并生成适合老人聆听的简短回答…</p>
            </div>
            <div v-else-if="reply" class="message message--agent">
              <span><Bot :size="15" /> 小康</span>
              <p>{{ reply }}</p>
              <audio v-if="responseAudioUrl" :src="responseAudioUrl" controls preload="metadata">
                当前浏览器不支持音频播放。
              </audio>
            </div>
          </template>
        </div>

        <div v-if="providerTrace.length" class="trace-line">
          <span v-for="(item, index) in providerTrace" :key="`${item}-${index}`">
            <Check :size="13" /> {{ item }}
          </span>
        </div>

        <div v-if="mode === 'text'" class="composer">
          <label for="companion-question">输入老人问题</label>
          <div class="composer__input">
            <textarea id="companion-question" v-model="question" rows="3" maxlength="1000" placeholder="例如：我现在想出去散步，可以吗？" @keydown.ctrl.enter="runTextTurn"></textarea>
            <button type="button" :disabled="!canSubmitText" @click="runTextTurn">
              <LoaderCircle v-if="submitting" :size="18" class="is-spinning" />
              <Send v-else :size="18" />
              {{ submitting ? "联动中" : "运行测试" }}
            </button>
          </div>
          <small>Ctrl + Enter 运行；本次请求会同时携带老人 ID、健康设备和天气位置。</small>
        </div>

        <div v-else class="voice-composer">
          <label class="upload-zone" :class="{ 'has-file': audioFile }">
            <input type="file" accept=".wav,.wave,.mp3,.pcm,audio/wav,audio/mpeg" @change="handleFile" />
            <Upload :size="22" />
            <span><strong>{{ audioFile?.name ?? "选择 WAV、MP3 或 PCM 语音文件" }}</strong><small>{{ audioFile ? `${(audioFile.size / 1024).toFixed(1)} KB` : "文件不超过 10 MiB" }}</small></span>
          </label>
          <button type="button" class="voice-run" :disabled="!canSubmitVoice" @click="runVoiceTurn">
            <LoaderCircle v-if="submitting" :size="18" class="is-spinning" />
            <Play v-else :size="18" />
            {{ submitting ? "ASR → Qwen → TTS 运行中" : "运行完整语音闭环" }}
          </button>
        </div>
      </main>
    </div>
  </section>
</template>

<style scoped>
.companion-page {
  --companion-ink: #132c3f;
  --companion-blue: #175f9d;
  --companion-cyan: #0f7c81;
  padding-bottom: 24px;
}

.readiness { display: inline-flex; align-items: center; gap: 8px; min-height: 40px; padding: 9px 13px; border: 1px solid #e4c789; border-radius: 10px; background: #fff9eb; color: #865807; font-size: .78rem; font-weight: 760; }
.readiness.is-ready { border-color: #a9dac5; background: #eef9f4; color: #087653; }
.readiness__dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; box-shadow: 0 0 0 4px color-mix(in srgb, currentColor 14%, transparent); }

.pipeline-strip { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); overflow: hidden; border: 1px solid #dbe6ee; border-radius: 16px; background: #f9fbfc; }
.pipeline-strip > div { min-width: 0; display: flex; align-items: center; gap: 10px; padding: 13px 15px; border-right: 1px solid #e2eaf0; color: #8494a1; }
.pipeline-strip > div:last-child { border-right: 0; }
.pipeline-strip > div.is-ready { color: #14725d; background: #f1faf6; }
.pipeline-strip > div.is-boundary { color: #976112; background: #fff9ed; }
.pipeline-strip span { min-width: 0; display: grid; gap: 2px; }
.pipeline-strip small { font-size: .61rem; font-weight: 760; letter-spacing: .07em; text-transform: uppercase; }
.pipeline-strip strong { overflow: hidden; color: currentColor; font-size: .75rem; text-overflow: ellipsis; white-space: nowrap; }

.companion-alert { display: grid; grid-template-columns: auto 1fr; gap: 10px; padding: 13px 15px; border: 1px solid #edc3be; border-left: 4px solid #c4483f; border-radius: 12px; background: #fff5f3; color: #a43a33; }
.companion-alert strong { font-size: .82rem; }
.companion-alert p { margin: 3px 0 0; font-size: .75rem; line-height: 1.5; }

.companion-workspace { display: grid; grid-template-columns: minmax(280px, .78fr) minmax(0, 1.7fr); min-height: 620px; overflow: hidden; border: 1px solid #dbe4eb; border-radius: 20px; background: #fff; box-shadow: 0 12px 36px rgba(27, 65, 91, .07); }
.context-rail { min-width: 0; display: flex; flex-direction: column; gap: 18px; padding: 22px; border-right: 1px solid #dfe7ed; background: linear-gradient(180deg, #f9fcfd 0%, #f5f9fb 100%); }
.section-heading, .dialogue-stage__header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.section-heading { justify-content: flex-start; }
.section-heading > span { width: 38px; height: 38px; display: grid; place-items: center; flex: 0 0 auto; border-radius: 11px; background: #e8f3f8; color: #1d668f; }
.section-heading div, .dialogue-stage__header > div:first-child { display: grid; gap: 3px; }
.section-heading small, .dialogue-stage__header small { color: #57809a; font-size: .62rem; font-weight: 800; letter-spacing: .1em; }
.section-heading h2, .dialogue-stage__header h2 { margin: 0; color: var(--companion-ink); font-size: 1rem; }

.inline-loading { display: flex; align-items: center; gap: 8px; min-height: 100px; justify-content: center; color: #6d8291; font-size: .78rem; }
.subject-form { display: grid; gap: 11px; }
.subject-form label { display: grid; gap: 6px; color: #5e7485; font-size: .72rem; font-weight: 700; }
.subject-form select, .subject-form input { width: 100%; min-height: 42px; padding: 9px 11px; border: 1px solid #cfdae2; border-radius: 9px; outline: 0; background: #fff; color: #244257; font: inherit; font-size: .78rem; }
.subject-form select:focus, .subject-form input:focus { border-color: #3b84bb; box-shadow: 0 0 0 3px rgba(59, 132, 187, .14); }

.source-list { display: grid; border-top: 1px solid #dfe7ed; border-bottom: 1px solid #dfe7ed; }
.source-list > div { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 10px; min-height: 58px; padding: 9px 2px; border-bottom: 1px solid #e6edf2; color: #48718e; }
.source-list > div:last-child { border-bottom: 0; }
.source-list span { display: grid; gap: 2px; }
.source-list small { color: #80909c; font-size: .65rem; }
.source-list strong { color: #334f63; font-size: .75rem; }
.source-list > div > svg:last-child { color: #14916d; }

.evidence-panel { display: grid; gap: 12px; }
.evidence-panel__heading { display: flex; justify-content: space-between; gap: 8px; color: #607b8e; font-size: .68rem; font-weight: 760; }
.evidence-panel__heading time { color: #8a9ba7; font-family: var(--font-mono); font-size: .58rem; font-weight: 500; }
.evidence-panel dl { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); margin: 0; border: 1px solid #dfe7ed; border-radius: 12px; background: #fff; }
.evidence-panel dl > div { min-width: 0; padding: 12px; border-right: 1px solid #e5edf2; border-bottom: 1px solid #e5edf2; }
.evidence-panel dl > div:nth-child(2n) { border-right: 0; }
.evidence-panel dl > div:nth-last-child(-n + 2) { border-bottom: 0; }
.evidence-panel dt { color: #80909c; font-size: .63rem; }
.evidence-panel dd { margin: 4px 0 0; color: #1b3c53; font-size: 1.02rem; font-weight: 800; font-variant-numeric: tabular-nums; }
.evidence-panel dd small { margin-left: 4px; color: #778c9a; font-size: .58rem; font-weight: 600; }
.risk-value.is-low { color: #087653; }
.risk-value.is-medium { color: #9a630b; }
.risk-value.is-high { color: #b33d36; }
.evidence-panel > p { margin: 0; padding: 10px 12px; border-left: 3px solid #6aa3c8; background: #edf6fb; color: #4a6e86; font-size: .69rem; line-height: 1.55; }
.evidence-empty { min-height: 160px; display: grid; place-content: center; justify-items: center; gap: 10px; margin-top: auto; padding: 18px; border: 1px dashed #cad8e2; border-radius: 13px; color: #7d919f; text-align: center; }
.evidence-empty p { max-width: 250px; margin: 0; font-size: .72rem; line-height: 1.6; }

.dialogue-stage { min-width: 0; display: grid; grid-template-rows: auto auto minmax(250px, 1fr) auto auto; gap: 16px; padding: 24px; background: radial-gradient(circle at 92% 4%, rgba(35, 122, 162, .08), transparent 25%), #fff; }
.mode-switch { display: flex; gap: 4px; margin: 0; padding: 4px; border: 1px solid #d8e2e9; border-radius: 10px; background: #f2f6f8; }
.mode-switch button { min-height: 36px; display: inline-flex; align-items: center; gap: 6px; padding: 7px 11px; border: 0; border-radius: 7px; background: transparent; color: #6a8192; font-size: .72rem; font-weight: 750; cursor: pointer; }
.mode-switch button.active { background: #fff; color: #175f9d; box-shadow: 0 2px 8px rgba(36, 78, 108, .11); }
.mode-switch button:focus-visible, .scenario-row button:focus-visible, .composer button:focus-visible, .voice-run:focus-visible { outline: 3px solid rgba(43, 124, 181, .25); outline-offset: 2px; }

.scenario-row { display: flex; align-items: center; gap: 7px; overflow-x: auto; padding-bottom: 2px; }
.scenario-row > span { flex: 0 0 auto; color: #7d8d99; font-size: .66rem; font-weight: 750; }
.scenario-row button { flex: 0 0 auto; min-height: 32px; padding: 6px 10px; border: 1px solid #d9e3ea; border-radius: 8px; background: #fafcfd; color: #49667b; font-size: .69rem; cursor: pointer; }
.scenario-row button:hover { border-color: #9fbfd4; background: #f2f8fb; color: #1d628f; }

.conversation { min-height: 250px; display: flex; flex-direction: column; justify-content: center; gap: 15px; padding: 20px; overflow-y: auto; border: 1px solid #e0e7ec; border-radius: 16px; background: rgba(248, 251, 252, .72); }
.conversation-empty { display: grid; justify-items: center; gap: 8px; padding: 24px; text-align: center; }
.companion-mark { width: 60px; height: 60px; display: grid; place-items: center; margin-bottom: 4px; border: 1px solid #bcd5e5; border-radius: 18px; background: linear-gradient(145deg, #e9f5fa, #fff); color: #196394; box-shadow: 0 10px 24px rgba(37, 103, 145, .11); }
.conversation-empty h3 { margin: 0; color: #203f54; font-size: 1rem; }
.conversation-empty p { max-width: 520px; margin: 0; color: #748795; font-size: .75rem; line-height: 1.65; }
.message { max-width: min(78%, 640px); display: grid; gap: 6px; }
.message > span { display: flex; align-items: center; gap: 5px; color: #718493; font-size: .66rem; font-weight: 760; }
.message p { margin: 0; padding: 13px 15px; border-radius: 14px; font-size: .84rem; line-height: 1.75; white-space: pre-wrap; }
.message--user { align-self: flex-end; justify-items: end; }
.message--user p { border: 1px solid #b8d7ea; border-bottom-right-radius: 4px; background: #eaf5fb; color: #24546f; }
.message--agent { align-self: flex-start; }
.message--agent p { border: 1px solid #d8e4db; border-bottom-left-radius: 4px; background: #f3f8f4; color: #294a3a; }
.message--agent audio { width: min(420px, 100%); height: 38px; }
.message.is-thinking p { color: #6c8190; }

.trace-line { display: flex; flex-wrap: wrap; gap: 6px; }
.trace-line span { display: inline-flex; align-items: center; gap: 4px; padding: 5px 8px; border: 1px solid #cde0d7; border-radius: 7px; background: #f3faf6; color: #24705a; font-family: var(--font-mono); font-size: .58rem; }

.composer { display: grid; gap: 8px; padding-top: 15px; border-top: 1px solid #e1e8ed; }
.composer > label { color: #526f83; font-size: .7rem; font-weight: 760; }
.composer__input { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; align-items: end; }
.composer textarea { width: 100%; min-height: 86px; resize: vertical; padding: 12px 13px; border: 1px solid #cad8e2; border-radius: 11px; outline: none; background: #fff; color: #233f52; font: inherit; font-size: .8rem; line-height: 1.55; }
.composer textarea:focus { border-color: #4388ba; box-shadow: 0 0 0 3px rgba(67, 136, 186, .13); }
.composer button, .voice-run { min-height: 44px; display: inline-flex; align-items: center; justify-content: center; gap: 7px; padding: 10px 15px; border: 1px solid #185e9a; border-radius: 10px; background: #175f9d; color: #fff; font: inherit; font-size: .76rem; font-weight: 760; cursor: pointer; }
.composer button:disabled, .voice-run:disabled { cursor: not-allowed; opacity: .48; }
.composer > small { color: #8796a1; font-size: .62rem; }

.voice-composer { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 10px; align-items: stretch; padding-top: 15px; border-top: 1px solid #e1e8ed; }
.upload-zone { min-height: 76px; display: flex; align-items: center; gap: 12px; padding: 13px 15px; border: 1px dashed #aec3d1; border-radius: 11px; background: #f8fbfc; color: #56758a; cursor: pointer; }
.upload-zone.has-file { border-style: solid; border-color: #83b8a4; background: #f1faf6; color: #1c7559; }
.upload-zone input { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
.upload-zone span { display: grid; gap: 3px; }
.upload-zone strong { font-size: .76rem; }
.upload-zone small { color: #8395a2; font-size: .64rem; }
.voice-run { align-self: center; }

.is-spinning { animation: companion-spin .9s linear infinite; }
@keyframes companion-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .is-spinning { animation: none; } }
@media (max-width: 1180px) { .pipeline-strip { grid-template-columns: repeat(3, minmax(0, 1fr)); } .pipeline-strip > div:nth-child(3) { border-right: 0; } .pipeline-strip > div:nth-child(-n + 3) { border-bottom: 1px solid #e2eaf0; } .companion-workspace { grid-template-columns: minmax(260px, .72fr) minmax(0, 1.35fr); } }
@media (max-width: 860px) { .companion-workspace { grid-template-columns: 1fr; } .context-rail { border-right: 0; border-bottom: 1px solid #dfe7ed; } .evidence-panel dl { grid-template-columns: repeat(3, minmax(0, 1fr)); } .evidence-panel dl > div, .evidence-panel dl > div:nth-child(2n), .evidence-panel dl > div:nth-last-child(-n + 2) { border-right: 1px solid #e5edf2; border-bottom: 1px solid #e5edf2; } .evidence-panel dl > div:nth-child(3n) { border-right: 0; } .evidence-panel dl > div:nth-last-child(-n + 3) { border-bottom: 0; } }
@media (max-width: 640px) { .pipeline-strip { grid-template-columns: 1fr; } .pipeline-strip > div, .pipeline-strip > div:nth-child(3) { border-right: 0; border-bottom: 1px solid #e2eaf0; } .pipeline-strip > div:last-child { border-bottom: 0; } .context-rail, .dialogue-stage { padding: 18px; } .dialogue-stage__header { align-items: flex-start; flex-direction: column; } .mode-switch { width: 100%; } .mode-switch button { flex: 1; justify-content: center; } .evidence-panel dl { grid-template-columns: repeat(2, minmax(0, 1fr)); } .evidence-panel dl > div:nth-child(3n) { border-right: 1px solid #e5edf2; } .evidence-panel dl > div:nth-child(2n) { border-right: 0; } .evidence-panel dl > div:nth-last-child(-n + 3) { border-bottom: 1px solid #e5edf2; } .evidence-panel dl > div:nth-last-child(-n + 2) { border-bottom: 0; } .message { max-width: 92%; } .composer__input, .voice-composer { grid-template-columns: 1fr; } .composer button, .voice-run { width: 100%; } }
</style>
