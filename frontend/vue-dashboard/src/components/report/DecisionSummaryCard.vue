<script setup lang="ts">
import { computed } from "vue";

type SummaryMetric = {
  label: string;
  value: string;
  note: string;
};

type SummaryStatus = "stable" | "attention" | "high";

const props = defineProps<{
  title: string;
  summaryLine: string;
  spokenConclusion: string;
  generatedAt: string;
  status: SummaryStatus;
  urgentMatters: string[];
  metrics: SummaryMetric[];
}>();

function statusCopy(status: SummaryStatus) {
  if (status === "high") {
    return { badge: "高风险", headline: "当前交接优先处理高风险对象与异常链路" };
  }
  if (status === "attention") {
    return { badge: "注意", headline: "整体可控，但需要跟进重点对象与告警波动" };
  }
  return { badge: "稳定", headline: "整体运行平稳，按常规巡检与观察节奏推进" };
}

const statusMeta = computed(() => statusCopy(props.status));
</script>

<template>
  <section class="decision-summary-card" :data-status="status">
    <div class="decision-summary-card__surface">
      <div class="decision-summary-card__header">
        <div>
          <p class="decision-summary-card__eyebrow">Shift Command Brief</p>
          <h2>{{ title }}</h2>
          <p class="decision-summary-card__headline">{{ statusMeta.headline }}</p>
        </div>
        <div class="decision-summary-card__status">
          <span class="decision-summary-card__badge">{{ statusMeta.badge }}</span>
          <small>生成于 {{ generatedAt }}</small>
        </div>
      </div>

      <div class="decision-summary-card__grid">
        <div class="decision-summary-card__summary">
          <p class="decision-summary-card__label">一句话结论</p>
          <strong>{{ spokenConclusion }}</strong>
          <p>{{ summaryLine }}</p>
        </div>

        <div class="decision-summary-card__metrics">
          <article v-for="item in metrics" :key="item.label" class="decision-metric">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
            <small>{{ item.note }}</small>
          </article>
        </div>
      </div>

      <div class="decision-summary-card__urgent">
        <p class="decision-summary-card__label">当前最紧急事项</p>
        <ol>
          <li v-for="item in urgentMatters" :key="item">{{ item }}</li>
        </ol>
      </div>
    </div>
  </section>
</template>

<style scoped>
.decision-summary-card {
  position: relative;
  overflow: hidden;
  border-radius: 30px;
  background:
    radial-gradient(circle at top right, rgba(248, 113, 113, 0.18), transparent 28%),
    radial-gradient(circle at left center, rgba(245, 158, 11, 0.12), transparent 36%),
    linear-gradient(135deg, #13233a 0%, #0d1628 58%, #111d32 100%);
  color: #eff4ff;
  box-shadow: 0 24px 50px rgba(15, 23, 42, 0.18);
}

.decision-summary-card__surface,
.decision-summary-card__grid,
.decision-summary-card__metrics {
  display: grid;
  gap: 20px;
}

.decision-summary-card__surface {
  padding: clamp(24px, 3vw, 34px);
}

.decision-summary-card__header {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  align-items: flex-start;
}

.decision-summary-card__eyebrow,
.decision-summary-card__label {
  margin: 0 0 8px;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  font-size: 0.72rem;
  font-weight: 800;
  color: rgba(191, 219, 254, 0.92);
}

.decision-summary-card h2 {
  margin: 0;
  font-family: var(--font-display);
  font-size: clamp(1.8rem, 3vw, 2.5rem);
  letter-spacing: -0.04em;
}

.decision-summary-card__headline {
  margin: 10px 0 0;
  color: rgba(226, 232, 240, 0.84);
  font-size: 1rem;
  line-height: 1.75;
}

.decision-summary-card__status {
  display: grid;
  justify-items: end;
  gap: 8px;
  text-align: right;
}

.decision-summary-card__badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.08);
  font-size: 0.95rem;
  font-weight: 800;
  backdrop-filter: blur(10px);
}

.decision-summary-card__status small {
  color: rgba(191, 219, 254, 0.76);
}

.decision-summary-card__grid {
  grid-template-columns: minmax(0, 1.25fr) minmax(340px, 0.95fr);
  align-items: start;
}

.decision-summary-card__summary strong {
  display: block;
  margin-bottom: 12px;
  font-size: clamp(1.1rem, 1.8vw, 1.45rem);
  line-height: 1.55;
  letter-spacing: -0.02em;
}

.decision-summary-card__summary p:last-child {
  margin: 0;
  color: rgba(226, 232, 240, 0.78);
  line-height: 1.8;
}

.decision-summary-card__metrics {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.decision-metric {
  display: grid;
  gap: 8px;
  padding: 18px;
  border-radius: 22px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.decision-metric span,
.decision-metric small {
  color: rgba(191, 219, 254, 0.82);
}

.decision-metric strong {
  font-size: 1.55rem;
  font-weight: 800;
  letter-spacing: -0.03em;
}

.decision-summary-card__urgent {
  padding-top: 6px;
  border-top: 1px solid rgba(148, 163, 184, 0.2);
}

.decision-summary-card__urgent ol {
  margin: 0;
  padding-left: 22px;
  display: grid;
  gap: 10px;
  line-height: 1.75;
  color: #f8fafc;
}

@media (max-width: 1080px) {
  .decision-summary-card__grid {
    grid-template-columns: 1fr;
  }

  .decision-summary-card__metrics {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .decision-summary-card__header {
    flex-direction: column;
  }

  .decision-summary-card__status {
    justify-items: start;
    text-align: left;
  }
}
</style>
