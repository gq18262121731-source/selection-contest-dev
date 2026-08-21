<script setup lang="ts">
import { computed } from "vue";
import type {
  AgentDeviceHealthReport,
  CareHealthEvaluationSummary,
  CareHealthReportSummary,
} from "../api/client";

type RiskTone = "stable" | "warning" | "critical" | "neutral";

const props = defineProps<{
  isBound: boolean;
  subjectName: string;
  deviceMac: string;
  evaluation: CareHealthEvaluationSummary | null;
  reportSummary: CareHealthReportSummary | null;
  generatedReport: AgentDeviceHealthReport | null;
  reportLoading: boolean;
  reportError: string;
}>();

const metricLabelMap: Record<string, { label: string; unit?: string; digits?: number }> = {
  heart_rate: { label: "心率", unit: "bpm" },
  blood_oxygen: { label: "血氧", unit: "%" },
  temperature: { label: "体温", unit: "°C", digits: 1 },
  health_score: { label: "健康评分", unit: "分" },
  battery: { label: "设备电量", unit: "%" },
  steps: { label: "步数", unit: "步" },
  ambient_temperature: { label: "环境温度", unit: "°C", digits: 1 },
  surface_temperature: { label: "表面温度", unit: "°C", digits: 1 },
};

function normalizeRisk(level?: string | null): { label: string; tone: RiskTone; note: string } {
  const source = (level ?? "").toLowerCase();
  if (source.includes("high") || source.includes("高")) {
    return { label: "高风险", tone: "critical", note: "建议优先查看建议动作和异常升级阶段。" };
  }
  if (source.includes("medium") || source.includes("mid") || source.includes("中")) {
    return { label: "中风险", tone: "warning", note: "当前存在波动，建议结合趋势和报告继续观察。" };
  }
  if (source.includes("low") || source.includes("低")) {
    return { label: "低风险", tone: "stable", note: "当前整体平稳，可维持常规关注。" };
  }
  return { label: level || "待评估", tone: "neutral", note: "等待更多结构化评估或报告结果。" };
}

function formatMetric(value?: number | null, digits = 0) {
  if (value === null || value === undefined) return "--";
  return digits > 0 ? value.toFixed(digits) : String(Math.round(value * 10) / 10);
}

const scoreValue = computed(() => {
  const generated = props.generatedReport?.metrics?.health_score?.latest;
  if (generated !== undefined && generated !== null) return generated;
  return props.evaluation?.latest_health_score ?? props.reportSummary?.latest_health_score ?? null;
});

const activeRiskLevel = computed(
  () => props.generatedReport?.risk_level || props.evaluation?.risk_level || props.reportSummary?.risk_level || "",
);

const riskState = computed(() => normalizeRisk(activeRiskLevel.value));

const reportRecommendations = computed(() => {
  if (props.generatedReport?.recommendations?.length) return props.generatedReport.recommendations;
  return props.reportSummary?.recommendations ?? [];
});

const notableEvents = computed(() => {
  if (props.generatedReport?.key_findings?.length) return props.generatedReport.key_findings;
  return props.reportSummary?.notable_events ?? [];
});

const riskFlags = computed(() => props.generatedReport?.risk_flags ?? props.evaluation?.risk_flags ?? []);

const reportMeta = computed(() => {
  if (!props.generatedReport) return [];
  return [
    { label: "时间窗口", value: `${props.generatedReport.period.duration_minutes} 分钟` },
    { label: "样本数量", value: String(props.generatedReport.period.sample_count) },
    { label: "生成时间", value: new Date(props.generatedReport.generated_at).toLocaleString("zh-CN", { hour12: false }) },
  ];
});

const reportSummaryText = computed(() => {
  if (props.generatedReport?.summary) return props.generatedReport.summary;
  if (props.reportSummary) {
    return `当前已有 ${props.reportSummary.sample_count} 条样本的历史结构化报告，风险等级为 ${normalizeRisk(props.reportSummary.risk_level).label}。建议继续生成最新 24 小时报告补充摘要。`;
  }
  if (props.evaluation) {
    return `当前已有结构化健康评估，风险等级为 ${normalizeRisk(props.evaluation.risk_level).label}。建议继续生成最新 24 小时结构化报告，补齐摘要、建议动作和指标汇总。`;
  }
  return "当前还没有结构化报告摘要。";
});

const reportCtaCopy = computed(() => {
  if (props.reportLoading) return "正在基于最近 24 小时的结构化样本生成报告，请稍候。";
  if (props.generatedReport) return "已经生成最新结构化报告，可根据演示需要再次刷新时间窗口。";
  if (props.reportSummary) return "已有历史报告摘要，可继续生成新的时间窗口报告，展示最新结论。";
  return "点击“生成报告”后，这里会展示时间窗口、样本量和生成时间。";
});

const overviewCards = computed(() => [
  {
    label: "健康评分",
    value: scoreValue.value !== null && scoreValue.value !== undefined ? String(Math.round(scoreValue.value)) : "--",
    note: "来自最新结构化评估或报告",
    emphasis: true,
  },
  {
    label: "风险等级",
    value: riskState.value.label,
    note: riskState.value.note,
    emphasis: false,
  },
  {
    label: "样本数量",
    value: String(props.generatedReport?.period.sample_count ?? props.reportSummary?.sample_count ?? "--"),
    note: "当前报告时间窗口内的结构化样本量",
    emphasis: false,
  },
  {
    label: "建议动作",
    value: reportRecommendations.value.length ? String(reportRecommendations.value.length) : "--",
    note: "可直接转成演示讲解或后续处理动作",
    emphasis: false,
  },
]);

const metricEntries = computed(() => {
  if (!props.generatedReport?.metrics) return [];
  return Object.entries(props.generatedReport.metrics).map(([key, value]) => {
    const config = metricLabelMap[key] ?? { label: key.replace(/_/g, " "), unit: "" };
    const digits = config.digits ?? 0;
    return {
      key,
      label: config.label,
      unit: config.unit ?? "",
      latest: formatMetric(value.latest, digits),
      average: formatMetric(value.average, digits),
      min: formatMetric(value.min, digits),
      max: formatMetric(value.max, digits),
      trend: value.trend ?? "稳定",
    };
  });
});
</script>

<template>
  <section class="panel health-evaluation-panel">
    <div class="evaluation-head">
      <div>
        <h2>健康评估与报告</h2>
        <p class="panel-subtitle">只消费结构化评估和报告字段，把摘要、风险、建议动作和指标汇总拉成清晰层级。</p>
      </div>
      <div class="evaluation-head-meta">
        <span class="status-tag" :class="`tone-${riskState.tone}`">{{ riskState.label }}</span>
        <span class="meta-pill">{{ deviceMac || "未选择设备" }}</span>
      </div>
    </div>

    <div v-if="!isBound" class="state-block state-empty">
      <strong>当前未绑定设备</strong>
      <p>未绑定状态下仅提供基础建议。绑定设备后，这里会展示健康评分、风险等级、报告摘要和建议动作。</p>
    </div>

    <template v-else>
      <div class="evaluation-hero">
        <article class="evaluation-summary-card">
          <p class="section-eyebrow">评估总结</p>
          <h3>{{ subjectName || "待选择" }}</h3>
          <p class="report-summary">{{ reportSummaryText }}</p>
          <div class="evaluation-tags">
            <span class="meta-pill">对象 {{ subjectName || "待选择" }}</span>
            <span class="meta-pill">设备 {{ deviceMac || "未选择设备" }}</span>
            <span class="meta-pill">{{ generatedReport ? "已生成最新报告" : reportSummary ? "已有历史摘要" : "等待报告生成" }}</span>
          </div>
        </article>

        <article class="evaluation-risk-card" :class="`tone-${riskState.tone}`">
          <span>风险等级</span>
          <strong>{{ riskState.label }}</strong>
          <p>{{ riskState.note }}</p>
          <div v-if="riskFlags.length" class="evaluation-flags">
            <span v-for="flag in riskFlags" :key="flag" class="risk-pill risk-medium">{{ flag }}</span>
          </div>
        </article>
      </div>

      <div class="health-score-grid overview-grid">
        <article v-for="card in overviewCards" :key="card.label" class="score-card" :class="{ emphasis: card.emphasis }">
          <span>{{ card.label }}</span>
          <strong>{{ card.value }}</strong>
          <p>{{ card.note }}</p>
        </article>
      </div>

      <div class="evaluation-two-col">
        <article class="report-card report-card--action">
          <div class="report-head">
            <div>
              <h3>报告生成</h3>
              <p class="panel-subtitle">{{ reportCtaCopy }}</p>
            </div>
            <button type="button" class="primary-btn" :disabled="reportLoading || !deviceMac" @click="$emit('generate-report')">
              {{ reportLoading ? "生成中..." : "生成报告" }}
            </button>
          </div>
          <div v-if="reportLoading && !generatedReport" class="state-block state-loading">
            <strong>报告生成中</strong>
            <p>正在整理最近 24 小时的结构化样本、风险标记和建议动作。</p>
          </div>
          <div v-else-if="reportMeta.length" class="meta-grid">
            <article v-for="item in reportMeta" :key="item.label" class="meta-card">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </article>
          </div>
          <div v-else class="state-block state-empty">
            <strong>还没有最新报告</strong>
            <p>点击“生成报告”后，这里会展示时间窗口、样本量和生成时间。</p>
          </div>
          <p v-if="reportError" class="feedback-banner feedback-error">{{ reportError }}</p>
        </article>

        <article class="report-card">
          <h3>建议动作</h3>
          <ul v-if="reportRecommendations.length" class="list-copy">
            <li v-for="item in reportRecommendations" :key="item">{{ item }}</li>
          </ul>
          <div v-else class="state-block state-empty">
            <strong>当前没有结构化建议动作</strong>
            <p>生成报告后，这里会汇总可直接向用户或值守人员解释的建议动作。</p>
          </div>
        </article>
      </div>

      <article class="report-card">
        <h3>关键发现</h3>
        <ul v-if="notableEvents.length" class="list-copy">
          <li v-for="item in notableEvents" :key="item">{{ item }}</li>
        </ul>
        <div v-else class="state-block state-empty">
          <strong>当前没有结构化关键发现</strong>
          <p>生成报告后，这里会提炼异常、波动或恢复趋势，方便汇报和演示。</p>
        </div>
      </article>

      <article class="report-card">
        <div class="report-head">
          <div>
            <h3>指标摘要</h3>
            <p class="panel-subtitle">指标摘要聚焦 latest / average / min / max / trend，用于承接 demo 报告页的核心内容。</p>
          </div>
        </div>
        <div v-if="metricEntries.length" class="metric-report-grid">
          <article v-for="item in metricEntries" :key="item.key" class="metric-report-card">
            <span>{{ item.label }}</span>
            <strong>{{ item.latest }}<small v-if="item.unit">{{ item.unit }}</small></strong>
            <p>均值 {{ item.average }}{{ item.unit }}</p>
            <p>最低 {{ item.min }}{{ item.unit }} / 最高 {{ item.max }}{{ item.unit }}</p>
            <p>趋势 {{ item.trend }}</p>
          </article>
        </div>
        <div v-else class="state-block state-empty">
          <strong>等待指标汇总</strong>
          <p>生成最新报告后，这里会显示各项指标的结构化统计结果，方便前端报告页直接落地。</p>
        </div>
      </article>
    </template>
  </section>
</template>

<style scoped>
.health-evaluation-panel,
.evaluation-hero,
.evaluation-two-col,
.overview-grid,
.metric-report-grid {
  display: grid;
  gap: 14px;
}

.evaluation-head {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: flex-start;
}

.evaluation-head-meta,
.evaluation-tags,
.evaluation-flags,
.meta-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.evaluation-hero {
  grid-template-columns: minmax(0, 1.35fr) 280px;
}

.overview-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.evaluation-summary-card,
.evaluation-risk-card,
.score-card,
.report-card,
.meta-card,
.metric-report-card {
  border: 1px solid rgba(56, 189, 248, 0.10);
  border-radius: 22px;
  background: rgba(13, 22, 38, 0.90);
  padding: 18px;
}

.evaluation-summary-card,
.report-card {
  display: grid;
  gap: 14px;
}

.evaluation-summary-card h3 {
  margin: 0;
  font-family: var(--font-display);
  font-size: 1.34rem;
  letter-spacing: -0.03em;
}

.evaluation-risk-card {
  display: grid;
  align-content: flex-start;
  gap: 10px;
}

.evaluation-risk-card span {
  color: var(--text-sub);
  font-size: 0.76rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.evaluation-risk-card strong {
  font-size: 2rem;
  line-height: 1.06;
}

.evaluation-risk-card p,
.score-card p,
.metric-report-card p,
.report-summary {
  margin: 0;
  color: var(--text-sub);
  line-height: 1.76;
}

.evaluation-risk-card.tone-critical {
  border-color: rgba(248, 113, 113, 0.24);
  background: linear-gradient(180deg, rgba(33, 18, 30, 0.96), rgba(52, 20, 28, 0.92));
}

.evaluation-risk-card.tone-warning {
  border-color: rgba(251, 146, 60, 0.22);
  background: linear-gradient(180deg, rgba(28, 20, 30, 0.96), rgba(52, 30, 16, 0.92));
}

.evaluation-risk-card.tone-stable {
  border-color: rgba(52, 211, 153, 0.22);
  background: linear-gradient(180deg, rgba(14, 24, 34, 0.96), rgba(16, 42, 38, 0.92));
}

.score-card {
  display: grid;
  gap: 10px;
}

.score-card span,
.meta-card span,
.metric-report-card span {
  color: var(--text-sub);
  font-size: 0.8rem;
  font-weight: 700;
}

.score-card strong,
.meta-card strong,
.metric-report-card strong {
  display: block;
  color: var(--text-main);
  font-size: 1.55rem;
  line-height: 1.1;
}

.score-card.emphasis {
  border-color: rgba(34, 211, 238, 0.20);
  background: linear-gradient(180deg, rgba(12, 30, 42, 0.98), rgba(14, 22, 36, 0.92));
}

.score-card.emphasis strong {
  color: #67e8f9;
}

.report-head {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: flex-start;
}

.report-card h3 {
  margin: 0;
}

.meta-grid {
  margin-top: 2px;
}

.meta-card {
  min-width: 160px;
}

.metric-report-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.metric-report-card small {
  font-size: 0.84rem;
  color: var(--text-muted);
}

@media (max-width: 1100px) {
  .evaluation-hero,
  .evaluation-two-col,
  .overview-grid,
  .metric-report-grid {
    grid-template-columns: 1fr;
  }

  .report-head,
  .evaluation-head {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
