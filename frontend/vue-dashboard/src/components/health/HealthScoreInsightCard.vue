<script setup lang="ts">
import { computed, watch } from "vue";
import { RefreshCw, Sparkles } from "lucide-vue-next";

import type { CommunityDashboardDeviceItem, CommunityDashboardElderItem } from "../../api/client";
import { useHealthScoreInsight } from "../../composables/useHealthScoreInsight";

const props = defineProps<{
  elder: CommunityDashboardElderItem | null;
  device: CommunityDashboardDeviceItem | null;
}>();

const { insight, loading, error, analyze } = useHealthScoreInsight();

const deviceMac = computed(() => props.device?.device_mac ?? props.elder?.device_mac ?? "");
const elderId = computed(() => props.elder?.elder_id ?? props.device?.elder_id ?? null);
const structured = computed(() => props.device?.structured_health ?? props.elder?.structured_health ?? null);
const technicalTextPattern = /(Missing model artifacts|static_health_model\.pt|feature_scaler\.joblib|feature_columns\.json|Traceback|Exception|[A-Za-z]:\\|\/(?:home|usr|var|tmp|opt|mnt|data|Users|workspace)\/[^\s]+|\.pt|\.joblib|\.json)/i;
const weakScoreExplanationPattern = /当前健康评分数据暂缺|健康评分数据暂缺|分析可信度受限/;
const technicalFallbackText = "结构化健康评分模型未完整加载，当前解释主要依据规则评分、实时体征和趋势结果生成。";

function safeDisplayText(value: string | null | undefined, fallback = technicalFallbackText) {
  const text = String(value ?? "").trim();
  if (!text) return fallback;
  return technicalTextPattern.test(text) ? fallback : text;
}

function safeDisplayList(items: string[] | null | undefined) {
  return (items ?? []).map((item) => safeDisplayText(item)).filter(Boolean);
}

function firstFiniteNumber(...values: Array<number | null | undefined>) {
  return values.find((value): value is number => typeof value === "number" && Number.isFinite(value)) ?? null;
}

const localScoreExplanation = computed(() => {
  const finalScore = firstFiniteNumber(
    structured.value?.health_score,
    props.device?.latest_health_score,
    props.elder?.latest_health_score,
  );
  const ruleScore = firstFiniteNumber(structured.value?.rule_health_score);
  const modelScore = firstFiniteNumber(structured.value?.model_health_score);
  const scoreParts = [
    finalScore == null ? null : `最终分 ${finalScore.toFixed(1)}`,
    ruleScore == null ? null : `规则分 ${ruleScore.toFixed(1)}`,
    modelScore == null ? null : `模型分 ${modelScore.toFixed(1)}`,
  ].filter(Boolean);
  const scoreText = scoreParts.length
    ? `本次健康评分已由实时手环数据计算生成：${scoreParts.join("，")}。`
    : "本次健康评分基于设备实时体征、规则阈值和近段趋势综合生成。";
  return `${scoreText}评分过程会参考心率、血氧、血压、体温等连续体征，结合最近告警和异常模型输出动态更新，用于值守判断和风险分层。`;
});

function scoreExplanationText(value: string | null | undefined) {
  const text = safeDisplayText(value, localScoreExplanation.value);
  return weakScoreExplanationPattern.test(text) ? localScoreExplanation.value : text;
}

const displayInsight = computed(() => {
  if (!insight.value) return null;
  return {
    ...insight.value,
    summary: safeDisplayText(insight.value.summary, "当前健康分析暂不可用，请稍后重新分析。"),
    score_explanation: scoreExplanationText(insight.value.score_explanation),
    trend_analysis: safeDisplayText(insight.value.trend_analysis, "近段时间趋势数据暂缺，分析可信度受限。"),
    model_assessment: safeDisplayText(insight.value.model_assessment),
    suggested_actions: safeDisplayList(insight.value.suggested_actions),
    watch_items: safeDisplayList(insight.value.watch_items),
  };
});

const riskLabel = computed(() => {
  const risk = displayInsight.value?.risk_level ?? "medium";
  return {
    low: "低风险",
    medium: "关注",
    high: "高风险",
    critical: "紧急",
  }[risk];
});

const freshnessLabel = computed(() => {
  const value = displayInsight.value?.data_freshness ?? "missing";
  return {
    fresh: "数据新鲜",
    stale: "数据偏旧",
    missing: "数据暂缺",
  }[value];
});

function refreshInsight() {
  if (!deviceMac.value) return;
  void analyze({
    device_mac: deviceMac.value,
    elder_id: elderId.value,
    window_minutes: 5,
    use_llm: true,
  });
}

watch(
  () => deviceMac.value,
  (mac) => {
    if (mac) refreshInsight();
  },
  { immediate: true },
);
</script>

<template>
  <article class="panel insight-panel" :data-risk="displayInsight?.risk_level ?? 'medium'">
    <div class="insight-panel__head">
      <div>
        <p class="section-eyebrow">AI健康分析</p>
        <h2>智能解读</h2>
        <p class="panel-subtitle">基于实时体征、健康评分、趋势模型和最近告警生成。</p>
      </div>
      <button type="button" class="insight-refresh" :disabled="loading || !deviceMac" @click="refreshInsight">
        <RefreshCw :size="16" :class="{ spinning: loading }" />
        重新分析
      </button>
    </div>

    <div v-if="!deviceMac" class="insight-empty">
      当前老人未绑定设备，暂不能生成智能解读。
    </div>

    <div v-else-if="loading && !insight" class="insight-loading">
      <Sparkles :size="18" />
      正在生成健康分析...
    </div>

    <div v-else class="insight-body">
      <p v-if="error" class="insight-error">{{ error }}</p>

      <div v-if="displayInsight" class="insight-tags">
        <span class="insight-risk">{{ riskLabel }}</span>
        <span>{{ freshnessLabel }}</span>
        <span v-if="displayInsight.fallback_used">规则模板</span>
        <span v-else>LLM解读</span>
      </div>

      <template v-if="displayInsight">
        <p class="insight-summary">{{ displayInsight.summary }}</p>

        <div class="insight-sections">
          <section>
            <span>评分说明</span>
            <p>{{ displayInsight.score_explanation }}</p>
          </section>
          <section>
            <span>趋势观察</span>
            <p>{{ displayInsight.trend_analysis }}</p>
          </section>
          <section>
            <span>模型评估</span>
            <p>{{ displayInsight.model_assessment }}</p>
          </section>
        </div>

        <div class="insight-lists">
          <section>
            <h3>建议动作</h3>
            <ul>
              <li v-for="item in displayInsight.suggested_actions" :key="item">{{ item }}</li>
            </ul>
          </section>
          <section>
            <h3>关注项</h3>
            <ul>
              <li v-for="item in displayInsight.watch_items" :key="item">{{ item }}</li>
            </ul>
          </section>
        </div>
      </template>
    </div>
  </article>
</template>

<style scoped>
.insight-panel {
  display: grid;
  gap: 18px;
  padding: 28px;
  background: #ffffff;
  border: 2px solid #e2e8f0;
  border-radius: 20px;
  box-shadow: 0 4px 16px rgba(15, 23, 42, 0.06);
}

.insight-panel[data-risk="high"],
.insight-panel[data-risk="critical"] {
  border-color: #fca5a5;
}

.insight-panel__head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.insight-panel__head h2 {
  margin: 0;
  color: var(--text-main);
  font-family: var(--font-display);
}

.panel-subtitle {
  margin: 8px 0 0;
  color: #64748b;
  line-height: 1.6;
}

.insight-refresh {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 38px;
  padding: 0 14px;
  border: 1px solid #cbd5e1;
  border-radius: 999px;
  background: #f8fafc;
  color: #0f172a;
  font-weight: 700;
  cursor: pointer;
}

.insight-refresh:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.spinning {
  animation: spin 900ms linear infinite;
}

.insight-empty,
.insight-loading,
.insight-error {
  padding: 16px 18px;
  border-radius: 14px;
  background: #f8fafc;
  color: #64748b;
  border: 1px solid #e2e8f0;
}

.insight-loading {
  display: flex;
  align-items: center;
  gap: 10px;
}

.insight-error {
  color: #b91c1c;
  background: #fef2f2;
  border-color: #fecaca;
}

.insight-body,
.insight-sections,
.insight-lists {
  display: grid;
  gap: 16px;
}

.insight-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.insight-tags span {
  padding: 7px 11px;
  border-radius: 999px;
  background: #f1f5f9;
  color: #475569;
  font-size: 0.84rem;
  font-weight: 700;
}

.insight-tags .insight-risk {
  background: #dbeafe;
  color: #1d4ed8;
}

.insight-panel[data-risk="high"] .insight-risk,
.insight-panel[data-risk="critical"] .insight-risk {
  background: #fee2e2;
  color: #dc2626;
}

.insight-summary {
  margin: 0;
  color: #0f172a;
  font-size: 1rem;
  line-height: 1.8;
  font-weight: 700;
}

.insight-sections section,
.insight-lists section {
  padding: 16px 18px;
  border-radius: 16px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
}

.insight-sections span,
.insight-lists h3 {
  display: block;
  margin: 0 0 8px;
  color: #334155;
  font-size: 0.9rem;
  font-weight: 800;
}

.insight-sections p {
  margin: 0;
  color: #475569;
  line-height: 1.75;
}

.insight-lists {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.insight-lists ul {
  margin: 0;
  padding-left: 18px;
  color: #475569;
  line-height: 1.75;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (max-width: 760px) {
  .insight-panel {
    padding: 20px;
  }

  .insight-panel__head,
  .insight-lists {
    grid-template-columns: 1fr;
  }

  .insight-panel__head {
    display: grid;
  }
}
</style>
