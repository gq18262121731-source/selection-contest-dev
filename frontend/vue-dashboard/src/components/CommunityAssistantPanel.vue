<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ApiError, api, type CommunityAgentSummaryResponse, type WindowKind } from "../api/client";
import { riskLevelToChinese } from "../utils/riskLevel";

const props = defineProps<{
  elderCount: number;
  deviceCount: number;
  highRiskCount: number;
  activeAlarmCount: number;
  focusNames: string[];
  deviceMacs: string[];
}>();

const quickQuestions = [
  "今天的值守优先级怎么排？",
  "哪些对象要先电话回访？",
  "请生成一段适合交接班的摘要。",
];

const question = ref("");
const selectedWindow = ref<WindowKind>("day");
const loading = ref(false);
const errorText = ref("");
const resultMeta = ref<CommunityAgentSummaryResponse | null>(null);

function formatError(error: unknown): string {
  if (error instanceof ApiError) return error.detail;
  if (error instanceof Error) return error.message;
  return String(error);
}

function cleanText(value: unknown): string {
  return String(value ?? "")
    .replace(/\r\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

const analysis = computed(() => resultMeta.value?.analysis ?? null);

const answer = computed(() =>
  cleanText(resultMeta.value?.summary_text || "智能体会基于当前设备状态和风险分布，生成一份面向值守人员的交接结论。"),
);
const references = computed(() =>
  (resultMeta.value?.sources ?? []).map((item) => {
    const snippet = cleanText(item.snippet);
    return snippet ? `${item.title}：${snippet}` : item.title;
  }),
);
const recommendations = computed(() => resultMeta.value?.advice ?? []);
const degradedNotes = computed(() => resultMeta.value?.agent_meta.degraded_notes ?? []);
const priorityDevices = computed(() => analysis.value?.high_risk_entities ?? []);

const riskDistribution = computed<Record<string, number>>(() => {
  return analysis.value?.risk_distribution ?? {};
});

const summaryCards = computed(() => [
  { label: "监护老人", value: `${props.elderCount} 人` },
  { label: "覆盖设备", value: `${props.deviceCount} 台` },
  { label: "活跃告警", value: `${props.activeAlarmCount} 条` },
  { label: "高风险对象", value: `${props.highRiskCount} 个` },
]);

const focusQueue = computed(() => {
  if (priorityDevices.value.length) {
    return priorityDevices.value.slice(0, 4).map((item, index) => ({
      order: index + 1,
      label: item.elder_name || item.device_mac || "--",
      risk: riskLevelToChinese(item.risk_level || "待分析"),
      summary: item.reasons?.[0] ?? "建议优先核查当前对象状态与现场响应情况。",
    }));
  }

  return props.focusNames.slice(0, 4).map((name, index) => ({
    order: index + 1,
    label: name,
    risk: index === 0 && props.highRiskCount ? "高风险" : "持续关注",
    summary: "等待进一步汇总分析，建议先核对实时体征、告警和回访状态。",
  }));
});

const distributionItems = computed(() => {
  const high = riskDistribution.value.high ?? props.highRiskCount;
  const medium = riskDistribution.value.medium ?? Math.max(0, props.deviceCount - high);
  const low = riskDistribution.value.low ?? Math.max(0, props.elderCount - high - medium);
  const total = Math.max(1, high + medium + low);

  return [
    { label: "高风险", value: high, width: `${(high / total) * 100}%`, tone: "high" },
    { label: "中风险", value: medium, width: `${(medium / total) * 100}%`, tone: "medium" },
    { label: "低风险", value: low, width: `${(low / total) * 100}%`, tone: "low" },
  ];
});

watch(
  () => props.deviceMacs.join("|"),
  () => {
    resultMeta.value = null;
    errorText.value = "";
    question.value = "";
  },
);

async function analyzeCommunity() {
  if (!props.deviceMacs.length) {
    errorText.value = "当前没有可分析的设备，请先确认设备是否已绑定并正常上报。";
    return;
  }

  const finalQuestion = question.value.trim() || quickQuestions[0];
  loading.value = true;
  errorText.value = "";
  try {
    resultMeta.value = await api.getCommunityAgentSummary({
      window: selectedWindow.value,
      question: finalQuestion,
      device_macs: props.deviceMacs,
      include_web_search: true,
      include_charts: false,
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
  <section class="panel community-agent-panel">
    <div class="agent-head">
      <div>
        <p class="agent-kicker">Community Agent</p>
        <h2>社区智能体</h2>
        <p class="panel-subtitle">只输出面向值守人员的结论、风险分布和调度建议，不展示模型内部提示或执行细节。</p>
      </div>
      <div class="hero-badges">
        <span class="hero-pill">高风险 {{ highRiskCount }}</span>
        <span class="hero-pill subtle">设备 {{ deviceCount }}</span>
      </div>
    </div>

    <div class="summary-grid">
      <article v-for="item in summaryCards" :key="item.label" class="summary-card">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
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
          <p v-if="errorText" class="error-copy">{{ errorText }}</p>
        </article>

        <article class="card">
          <div class="card-head compact">
            <div>
              <p class="section-kicker">Risk Mix</p>
              <h3>风险分布</h3>
            </div>
          </div>
          <div class="distribution-list">
            <div v-for="item in distributionItems" :key="item.label" class="distribution-item">
              <div class="distribution-meta">
                <span>{{ item.label }}</span>
                <strong>{{ item.value }}</strong>
              </div>
              <div class="distribution-track">
                <div class="distribution-fill" :data-tone="item.tone" :style="{ width: item.width }"></div>
              </div>
            </div>
          </div>
        </article>

        <article class="card">
          <div class="card-head compact">
            <div>
              <p class="section-kicker">Priority Queue</p>
              <h3>推荐处理顺序</h3>
            </div>
          </div>
          <div class="priority-grid">
            <article v-for="item in focusQueue" :key="`${item.order}-${item.label}`" class="priority-card">
              <span>优先级 {{ item.order }}</span>
              <strong>{{ item.label }}</strong>
              <small>{{ item.risk }}</small>
              <p>{{ item.summary }}</p>
            </article>
          </div>
        </article>

        <article v-if="recommendations.length" class="card">
          <div class="card-head compact">
            <div>
              <p class="section-kicker">Recommendations</p>
              <h3>调度建议</h3>
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
          <div class="window-toggle">
            <button
              type="button"
              class="window-chip"
              :class="{ 'window-chip--active': selectedWindow === 'day' }"
              @click="selectedWindow = 'day'"
            >
              过去一天
            </button>
            <button
              type="button"
              class="window-chip"
              :class="{ 'window-chip--active': selectedWindow === 'week' }"
              @click="selectedWindow = 'week'"
            >
              过去一周
            </button>
          </div>
          <div class="chip-row">
            <button v-for="item in quickQuestions" :key="item" type="button" class="prompt-chip" @click="question = item">
              {{ item }}
            </button>
          </div>
          <label class="composer">
            <span>你的问题</span>
            <textarea v-model="question" rows="4" placeholder="例如：请生成一段适合交接班的摘要。"></textarea>
          </label>
          <div class="action-row">
            <button type="button" class="primary-btn" :disabled="loading" @click="analyzeCommunity">
              {{ loading ? "生成中..." : "生成结论" }}
            </button>
            <small class="helper-copy">这里仅展示建议性解读，处理优先级不是后台持久化状态，最终以业务状态和现场判断为准。</small>
          </div>
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

        <article v-if="degradedNotes.length" class="card">
          <div class="card-head compact">
            <div>
              <p class="section-kicker">Runtime</p>
              <h3>降级说明</h3>
            </div>
          </div>
          <ul class="list-copy">
            <li v-for="item in degradedNotes" :key="item">{{ item }}</li>
          </ul>
        </article>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.community-agent-panel {
  display: grid;
  gap: 18px;
  color: var(--text-main);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(244, 251, 250, 0.9));
}

.agent-head,
.card-head,
.action-row {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: flex-start;
}

.summary-grid,
.priority-grid,
.agent-layout,
.agent-main,
.agent-side {
  display: grid;
  gap: 16px;
}

.summary-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.agent-layout {
  grid-template-columns: minmax(0, 1.35fr) minmax(320px, 0.95fr);
}

.card,
.summary-card,
.priority-card {
  border: 1px solid rgba(15, 118, 110, 0.12);
  border-radius: 22px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(248, 250, 252, 0.9));
  transition: box-shadow 200ms ease;
}

.card:hover,
.priority-card:hover {
  box-shadow: 0 20px 36px rgba(15, 23, 42, 0.08);
}

.card,
.priority-card {
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

.priority-card strong {
  color: var(--text-main);
  font-size: 0.98rem;
  font-weight: 600;
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

.agent-head h2,
.card-head h3 {
  margin: 0;
  font-family: var(--font-display);
}

.hero-badges,
.chip-row,
.window-toggle {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.hero-pill {
  border-radius: 999px;
  padding: 7px 13px;
  font-size: 0.8rem;
  font-weight: 600;
  background: rgba(236, 253, 245, 0.9);
  border: 1px solid rgba(15, 118, 110, 0.16);
  color: var(--brand);
}

.hero-pill.subtle,
.summary-card span,
.summary-card small,
.priority-card span,
.priority-card small,
.helper-copy,
.answer-copy {
  color: var(--text-sub);
}

.summary-card span,
.priority-card span {
  font-size: 0.78rem;
  font-weight: 500;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.answer-copy {
  margin: 12px 0 0;
  line-height: 1.9;
  white-space: pre-wrap;
  font-size: 0.93rem;
}

.error-copy {
  margin: 12px 0 0;
  color: #dc2626;
}

.distribution-list {
  display: grid;
  gap: 14px;
}

.distribution-item {
  display: grid;
  gap: 8px;
}

.distribution-meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  font-size: 0.88rem;
}

.distribution-meta strong {
  font-weight: 700;
  color: var(--text-main);
}

.distribution-track {
  height: 10px;
  border-radius: 999px;
  background: rgba(15, 118, 110, 0.08);
  overflow: hidden;
}

.distribution-fill {
  height: 100%;
  border-radius: inherit;
  transition: width 600ms cubic-bezier(0.32, 0, 0.18, 1);
}

.distribution-fill[data-tone="high"] {
  background: linear-gradient(90deg, #dc2626, #f87171);
}

.distribution-fill[data-tone="medium"] {
  background: linear-gradient(90deg, #f59e0b, #fbbf24);
}

.distribution-fill[data-tone="low"] {
  background: linear-gradient(90deg, #0f766e, #34d399);
}

.priority-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.priority-card p,
.helper-copy {
  line-height: 1.7;
  font-size: 0.84rem;
}

.list-copy {
  margin: 0;
  padding-left: 18px;
  line-height: 1.85;
  color: var(--text-main);
  font-size: 0.91rem;
}

.prompt-chip {
  border: 1.5px solid rgba(15, 118, 110, 0.16);
  border-radius: 999px;
  padding: 8px 14px;
  background: rgba(240, 253, 250, 0.94);
  color: var(--brand);
  cursor: pointer;
  font-size: 0.84rem;
  font-weight: 500;
  transition: background 150ms ease, border-color 150ms ease;
}

.window-chip {
  border: 1.5px solid rgba(15, 118, 110, 0.14);
  border-radius: 999px;
  padding: 8px 14px;
  background: rgba(255, 255, 255, 0.92);
  color: var(--text-sub);
  cursor: pointer;
  font-size: 0.84rem;
  font-weight: 600;
}

.window-chip--active {
  border-color: rgba(15, 118, 110, 0.28);
  background: rgba(15, 118, 110, 0.1);
  color: var(--brand);
}

.prompt-chip:hover {
  background: rgba(15, 118, 110, 0.12);
  border-color: rgba(14, 165, 233, 0.22);
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
  border: 1.5px solid rgba(15, 118, 110, 0.16);
  background: rgba(255, 255, 255, 0.98);
  color: var(--text-main);
  padding: 14px;
  transition: border-color 200ms ease, box-shadow 200ms ease;
}

.composer textarea:focus {
  outline: none;
  border-color: rgba(14, 165, 233, 0.28);
  box-shadow: 0 0 0 4px rgba(14, 165, 233, 0.12);
}

.compact {
  align-items: center;
}

@media (max-width: 1180px) {
  .summary-grid,
  .priority-grid,
  .agent-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 960px) {
  .agent-head,
  .card-head,
  .action-row {
    flex-direction: column;
  }
}
</style>
