<script setup lang="ts">
type RiskCardItem = {
  id: string;
  name: string;
  code: string;
  reason: string;
  action: string;
  confidence: string;
  healthScore: string;
  activeAlertCount: number;
};

type Tone = "high" | "medium" | "low";

const props = defineProps<{
  title: string;
  tone: Tone;
  description: string;
  items: RiskCardItem[];
}>();

const toneMeta = {
  high: { label: "高风险", pill: "优先处置" },
  medium: { label: "中风险", pill: "24h 跟进" },
  low: { label: "低风险", pill: "持续观察" },
}[props.tone];
</script>

<template>
  <section class="risk-card-group" :data-tone="tone">
    <header class="risk-card-group__head">
      <div>
        <p class="risk-card-group__eyebrow">{{ toneMeta.label }}</p>
        <h3>{{ title }}</h3>
        <p>{{ description }}</p>
      </div>
      <span class="risk-card-group__count">{{ items.length }} 项 · {{ toneMeta.pill }}</span>
    </header>

    <div v-if="items.length" class="risk-card-group__grid">
      <article v-for="item in items" :key="item.id" class="risk-card">
        <div class="risk-card__head">
          <div>
            <small>{{ item.code }}</small>
            <strong>{{ item.name }}</strong>
          </div>
          <span>{{ item.confidence }}</span>
        </div>
        <dl class="risk-card__meta">
          <div>
            <dt>风险原因</dt>
            <dd>{{ item.reason }}</dd>
          </div>
          <div>
            <dt>建议动作</dt>
            <dd>{{ item.action }}</dd>
          </div>
        </dl>
        <div class="risk-card__footer">
          <span>健康分 {{ item.healthScore }}</span>
          <span>活动告警 {{ item.activeAlertCount }}</span>
        </div>
      </article>
    </div>

    <div v-else class="risk-card-group__empty">
      当前分层下没有对象，保持现有巡检节奏即可。
    </div>
  </section>
</template>

<style scoped>
.risk-card-group,
.risk-card-group__grid {
  display: grid;
  gap: 16px;
}

.risk-card-group {
  padding: 22px;
  border-radius: 26px;
  border: 1px solid var(--line-medium);
  background: #ffffff;
  box-shadow: 0 12px 26px rgba(15, 23, 42, 0.05);
}

.risk-card-group__head {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: flex-start;
}

.risk-card-group__eyebrow {
  margin: 0 0 8px;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  font-size: 0.72rem;
  font-weight: 800;
}

.risk-card-group h3 {
  margin: 0;
  color: var(--text-main);
  font-family: var(--font-display);
  font-size: 1.35rem;
}

.risk-card-group p {
  margin: 8px 0 0;
  color: var(--text-sub);
  line-height: 1.72;
}

.risk-card-group__count {
  flex-shrink: 0;
  padding: 9px 14px;
  border-radius: 999px;
  font-size: 0.8rem;
  font-weight: 800;
}

.risk-card-group__grid {
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
}

.risk-card {
  display: grid;
  gap: 14px;
  padding: 18px;
  border-radius: 22px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: #fbfbfa;
}

.risk-card__head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.risk-card__head small {
  display: block;
  margin-bottom: 6px;
  color: var(--text-sub);
  font-size: 0.76rem;
  letter-spacing: 0.06em;
}

.risk-card__head strong {
  color: var(--text-main);
  font-size: 1.02rem;
}

.risk-card__head span {
  padding: 7px 10px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.06);
  color: var(--text-main);
  font-size: 0.75rem;
  font-weight: 700;
}

.risk-card__meta,
.risk-card__meta div {
  display: grid;
  gap: 6px;
}

.risk-card__meta dt,
.risk-card__footer {
  color: var(--text-sub);
  font-size: 0.8rem;
}

.risk-card__meta dd {
  margin: 0;
  color: var(--text-main);
  line-height: 1.65;
}

.risk-card__footer {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding-top: 12px;
  border-top: 1px solid rgba(15, 23, 42, 0.08);
}

.risk-card-group__empty {
  padding: 20px;
  border-radius: 20px;
  background: #f8fafc;
  color: var(--text-sub);
  line-height: 1.7;
}

.risk-card-group[data-tone="high"] {
  background: linear-gradient(180deg, #fff7f7 0%, #ffffff 32%);
}

.risk-card-group[data-tone="high"] .risk-card-group__eyebrow,
.risk-card-group[data-tone="high"] .risk-card__head strong {
  color: #b91c1c;
}

.risk-card-group[data-tone="high"] .risk-card-group__count {
  background: #fee2e2;
  color: #b91c1c;
}

.risk-card-group[data-tone="medium"] {
  background: linear-gradient(180deg, #fffaf0 0%, #ffffff 32%);
}

.risk-card-group[data-tone="medium"] .risk-card-group__eyebrow,
.risk-card-group[data-tone="medium"] .risk-card__head strong {
  color: #b45309;
}

.risk-card-group[data-tone="medium"] .risk-card-group__count {
  background: #fef3c7;
  color: #b45309;
}

.risk-card-group[data-tone="low"] {
  background: linear-gradient(180deg, #f3fbf7 0%, #ffffff 32%);
}

.risk-card-group[data-tone="low"] .risk-card-group__eyebrow,
.risk-card-group[data-tone="low"] .risk-card__head strong {
  color: #047857;
}

.risk-card-group[data-tone="low"] .risk-card-group__count {
  background: #dcfce7;
  color: #047857;
}

@media (max-width: 760px) {
  .risk-card-group__head,
  .risk-card__footer {
    flex-direction: column;
  }
}
</style>
