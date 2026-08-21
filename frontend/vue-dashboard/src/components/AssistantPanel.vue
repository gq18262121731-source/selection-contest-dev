<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ApiError, api, type AgentResponse, type AlarmRecord, type HealthSample } from "../api/client";

const props = defineProps<{
  deviceMac: string;
  subjectName: string;
  sample: HealthSample | null;
  riskLabel: string;
  focusAlarm: AlarmRecord | null;
  trendCount: number;
}>();

const quickQuestions = [
  "今晚最需要观察什么？",
  "现在哪个指标最值得复测？",
  "如果只做三件事，优先顺序是什么？",
];

const question = ref("");
const loading = ref(false);
const errorText = ref("");
const resultMeta = ref<AgentResponse | null>(null);

function asList(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)) : [];
}

function cleanText(value: unknown): string {
  return String(value ?? "")
    .replace(/\r\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function formatError(error: unknown): string {
  if (error instanceof ApiError) return error.detail;
  if (error instanceof Error) return error.message;
  return String(error);
}

const analysis = computed<Record<string, unknown>>(() => {
  const payload = resultMeta.value?.analysis;
  return payload && typeof payload === "object" ? payload : {};
});

const answer = computed(() => cleanText(resultMeta.value?.answer || "智能体会基于当前状态和趋势，生成面向家属的简洁结论。"));
const riskFlags = computed(() => asList(analysis.value.risk_flags));
const recommendations = computed(() => asList(analysis.value.recommendations));
const notableEvents = computed(() => asList(analysis.value.notable_events));
const references = computed(() => asList(resultMeta.value?.references));

const overviewCards = computed(() => [
  { label: "照护对象", value: props.subjectName || "待选择" },
  { label: "风险等级", value: props.riskLabel || "--" },
  { label: "告警状态", value: props.focusAlarm ? "需要立即关注" : "当前稳定" },
  { label: "趋势样本", value: `${props.trendCount || 0} 条` },
]);

const vitals = computed(() => [
  { label: "心率", value: props.sample?.heart_rate ?? "--", unit: "bpm" },
  { label: "血氧", value: props.sample?.blood_oxygen ?? "--", unit: "%" },
  { label: "体温", value: props.sample ? props.sample.temperature.toFixed(1) : "--", unit: "°C" },
  { label: "健康分", value: props.sample?.health_score ?? "--", unit: "分" },
]);

const displayChecklist = computed(() => {
  if (recommendations.value.length) return recommendations.value.slice(0, 3);
  if (props.focusAlarm) {
    return [
      "先确认老人当前意识和主诉。",
      "尽快复测关键指标并记录结果。",
      "若异常持续或加重，立即联系社区或医生。",
    ];
  }
  return [
    "先看实时体征，再结合趋势判断是否需要复测。",
    "把智能体结论和现场观察一起判断。",
    "若老人主诉不适，应提高关注等级。",
  ];
});

watch(
  () => props.deviceMac,
  () => {
    resultMeta.value = null;
    errorText.value = "";
    question.value = "";
  },
);

async function analyze() {
  if (!props.deviceMac) {
    errorText.value = "请先选择一位老人。";
    return;
  }

  const finalQuestion = question.value.trim() || quickQuestions[0];
  loading.value = true;
  errorText.value = "";
  try {
    resultMeta.value = await api.analyze({
      device_mac: props.deviceMac,
      question: finalQuestion,
      role: "family",
      mode: "qwen",
      history_limit: 240,
      history_minutes: 1440,
    });
  } catch (error) {
    resultMeta.value = null;
    errorText.value = formatError(error);
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <section class="panel assistant-panel">
    <div class="assistant-head">
      <div>
        <p class="agent-kicker">Family Agent</p>
        <h2>家庭智能体</h2>
        <p class="panel-subtitle">只展示面向家属的结论、风险提示和建议动作，不暴露系统提示或内部执行细节。</p>
      </div>
      <span class="hero-pill">{{ props.deviceMac || "未选择设备" }}</span>
    </div>

    <div class="summary-grid">
      <article v-for="item in overviewCards" :key="item.label" class="summary-card">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
      </article>
    </div>

    <div class="summary-grid vitals-grid">
      <article v-for="item in vitals" :key="item.label" class="summary-card">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
        <small>{{ item.unit }}</small>
      </article>
    </div>

    <div class="agent-layout">
      <div class="agent-main">
        <article class="card">
          <div class="card-head">
            <div>
              <p class="section-kicker">Summary</p>
              <h3>主结论</h3>
            </div>
          </div>
          <p class="answer-copy">{{ answer }}</p>
          <p v-if="props.focusAlarm" class="alarm-copy">当前告警：{{ props.focusAlarm.message }}</p>
          <p v-if="errorText" class="error-copy">{{ errorText }}</p>
        </article>

        <div class="two-col">
          <article v-if="riskFlags.length" class="card">
            <div class="card-head compact">
              <div>
                <p class="section-kicker">Risk Flags</p>
                <h3>风险提示</h3>
              </div>
            </div>
            <div class="chip-row">
              <span v-for="flag in riskFlags" :key="flag" class="analysis-chip">{{ flag }}</span>
            </div>
          </article>

          <article v-if="notableEvents.length" class="card">
            <div class="card-head compact">
              <div>
                <p class="section-kicker">Notable Events</p>
                <h3>关键事件</h3>
              </div>
            </div>
            <ul class="list-copy">
              <li v-for="item in notableEvents" :key="item">{{ item }}</li>
            </ul>
          </article>
        </div>

        <article v-if="recommendations.length" class="card">
          <div class="card-head compact">
            <div>
              <p class="section-kicker">Recommendations</p>
              <h3>建议动作</h3>
            </div>
          </div>
          <ul class="list-copy">
            <li v-for="item in recommendations" :key="item">{{ item }}</li>
          </ul>
        </article>
      </div>

      <aside class="agent-side">
        <article class="card">
          <div class="card-head compact">
            <div>
              <p class="section-kicker">Ask</p>
              <h3>问问智能体</h3>
            </div>
          </div>
          <div class="chip-row">
            <button v-for="item in quickQuestions" :key="item" type="button" class="prompt-chip" @click="question = item">
              {{ item }}
            </button>
          </div>
          <label class="composer">
            <span>你的问题</span>
            <textarea v-model="question" rows="4" placeholder="例如：今晚最需要观察什么？"></textarea>
          </label>
          <div class="action-row">
            <button type="button" class="primary-btn" :disabled="loading" @click="analyze">
              {{ loading ? "生成中..." : "生成结论" }}
            </button>
            <small class="helper-copy">这里仅展示建议性解读，设备状态、关系状态和告警状态仍以后端实时数据为准。</small>
          </div>
        </article>

        <article class="card">
          <div class="card-head compact">
            <div>
              <p class="section-kicker">Now</p>
              <h3>立刻可做</h3>
            </div>
          </div>
          <ul class="list-copy">
            <li v-for="item in displayChecklist" :key="item">{{ item }}</li>
          </ul>
        </article>

        <article v-if="references.length" class="card">
          <div class="card-head compact">
            <div>
              <p class="section-kicker">References</p>
              <h3>参考来源</h3>
            </div>
          </div>
          <ul class="list-copy">
            <li v-for="item in references" :key="item">{{ item }}</li>
          </ul>
        </article>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.assistant-panel {
  display: grid;
  gap: 18px;
  color: var(--text-main);
  background:
    radial-gradient(circle at top right, rgba(34, 211, 238, 0.10), transparent 30%),
    linear-gradient(180deg, rgba(15, 22, 40, 0.98), rgba(11, 18, 32, 0.96));
}

.assistant-head,
.card-head,
.action-row {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: flex-start;
}

.summary-grid,
.two-col,
.agent-layout,
.agent-main,
.agent-side {
  display: grid;
  gap: 16px;
}

.summary-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.vitals-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.agent-layout {
  grid-template-columns: minmax(0, 1.3fr) minmax(300px, 0.9fr);
}

.two-col {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.card,
.summary-card {
  border: 1px solid rgba(56, 189, 248, 0.10);
  border-radius: 22px;
  background:
    linear-gradient(180deg, rgba(16, 24, 44, 0.98), rgba(12, 18, 32, 0.94));
  transition: box-shadow 200ms ease;
}

.card:hover {
  box-shadow: 0 20px 36px rgba(0, 0, 0, 0.26);
}

.card {
  padding: 18px;
}

.summary-card {
  padding: 16px;
  display: grid;
  gap: 8px;
}

.summary-card strong {
  color: var(--text-main);
  font-size: 1.18rem;
  font-weight: 700;
}

.summary-card span,
.summary-card small,
.helper-copy,
.answer-copy,
.alarm-copy {
  color: var(--text-sub);
}

.agent-kicker,
.section-kicker {
  margin: 0 0 6px;
  color: var(--brand);
  text-transform: uppercase;
  letter-spacing: 0.16em;
  font-size: 0.72rem;
  font-weight: 700;
}

.assistant-head h2,
.card-head h3 {
  margin: 0;
  font-family: var(--font-display);
}

.hero-pill {
  border-radius: 999px;
  padding: 7px 13px;
  font-size: 0.8rem;
  font-weight: 600;
  background: rgba(34, 211, 238, 0.10);
  border: 1px solid rgba(34, 211, 238, 0.18);
  color: #67e8f9;
}

.analysis-chip {
  border-radius: 999px;
  padding: 6px 12px;
  font-size: 0.8rem;
  font-weight: 600;
  background: rgba(15, 24, 42, 0.88);
  border: 1px solid rgba(56, 189, 248, 0.16);
  color: #67e8f9;
}

.answer-copy {
  margin: 12px 0 0;
  line-height: 1.9;
  white-space: pre-wrap;
  font-size: 0.93rem;
}

.alarm-copy,
.error-copy {
  margin: 12px 0 0;
}

.error-copy {
  color: #fca5a5;
}

.list-copy {
  margin: 0;
  padding-left: 18px;
  line-height: 1.85;
  color: var(--text-main);
  font-size: 0.91rem;
}

.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.prompt-chip {
  border: 1.5px solid rgba(56, 189, 248, 0.16);
  border-radius: 999px;
  padding: 8px 14px;
  background: rgba(13, 24, 38, 0.94);
  color: #8ddff8;
  cursor: pointer;
  font-size: 0.84rem;
  font-weight: 500;
  transition: background 150ms ease, border-color 150ms ease;
}

.prompt-chip:hover {
  background: rgba(34, 211, 238, 0.12);
  border-color: rgba(34, 211, 238, 0.24);
}

.composer {
  display: grid;
  gap: 8px;
  margin-top: 14px;
  color: var(--text-sub);
  font-size: 0.9rem;
}

.composer textarea {
  resize: vertical;
  min-height: 110px;
  border-radius: 16px;
  border: 1.5px solid rgba(56, 189, 248, 0.16);
  background: rgba(10, 18, 30, 0.96);
  color: var(--text-main);
  padding: 14px;
  transition: border-color 200ms ease, box-shadow 200ms ease;
}

.composer textarea:focus {
  outline: none;
  border-color: rgba(34, 211, 238, 0.28);
  box-shadow: 0 0 0 4px rgba(34, 211, 238, 0.12);
}

.compact {
  align-items: center;
}

@media (max-width: 1180px) {
  .summary-grid,
  .vitals-grid,
  .two-col,
  .agent-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 960px) {
  .assistant-head,
  .card-head,
  .action-row {
    flex-direction: column;
  }
}
</style>
