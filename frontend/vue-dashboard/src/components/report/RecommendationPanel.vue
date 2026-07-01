<script setup lang="ts">
type RecommendationGroup = {
  title: string;
  tone: "p0" | "p1" | "p2";
  items: string[];
};

defineProps<{
  groups: RecommendationGroup[];
}>();
</script>

<template>
  <section class="recommendation-panel">
    <header class="recommendation-panel__head">
      <div>
        <p class="recommendation-panel__eyebrow">Action Queue</p>
        <h3>处置建议分级</h3>
        <p>把建议动作拆成 P0 / P1 / P2，便于值守人员按时效分发和确认。</p>
      </div>
    </header>

    <div class="recommendation-panel__grid">
      <article
        v-for="group in groups"
        :key="group.title"
        class="recommendation-card"
        :data-tone="group.tone"
      >
        <div class="recommendation-card__head">
          <strong>{{ group.title }}</strong>
          <span>{{ group.items.length }} 条</span>
        </div>
        <ul v-if="group.items.length">
          <li v-for="item in group.items" :key="item">{{ item }}</li>
        </ul>
        <p v-else class="recommendation-card__empty">当前无新增动作，保持现有节奏即可。</p>
      </article>
    </div>
  </section>
</template>

<style scoped>
.recommendation-panel,
.recommendation-panel__grid {
  display: grid;
  gap: 18px;
}

.recommendation-panel {
  padding: 22px;
  border-radius: 26px;
  border: 1px solid var(--line-medium);
  background: #ffffff;
  box-shadow: 0 12px 26px rgba(15, 23, 42, 0.05);
}

.recommendation-panel__eyebrow {
  margin: 0 0 8px;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  font-size: 0.72rem;
  font-weight: 800;
  color: var(--brand);
}

.recommendation-panel h3 {
  margin: 0;
  color: var(--text-main);
  font-family: var(--font-display);
  font-size: 1.35rem;
}

.recommendation-panel p {
  margin: 8px 0 0;
  color: var(--text-sub);
  line-height: 1.72;
}

.recommendation-panel__grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.recommendation-card {
  display: grid;
  gap: 14px;
  padding: 18px;
  border-radius: 22px;
  background: #fbfbfa;
  border: 1px solid rgba(15, 23, 42, 0.08);
}

.recommendation-card__head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.recommendation-card__head strong {
  color: var(--text-main);
  font-size: 1rem;
}

.recommendation-card__head span {
  padding: 6px 10px;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 700;
}

.recommendation-card ul {
  margin: 0;
  padding-left: 18px;
  display: grid;
  gap: 10px;
  line-height: 1.7;
  color: var(--text-main);
}

.recommendation-card__empty {
  margin: 0;
}

.recommendation-card[data-tone="p0"] {
  background: linear-gradient(180deg, #fff5f5 0%, #ffffff 100%);
}

.recommendation-card[data-tone="p0"] .recommendation-card__head span {
  background: #fee2e2;
  color: #b91c1c;
}

.recommendation-card[data-tone="p1"] {
  background: linear-gradient(180deg, #fffaf0 0%, #ffffff 100%);
}

.recommendation-card[data-tone="p1"] .recommendation-card__head span {
  background: #fef3c7;
  color: #b45309;
}

.recommendation-card[data-tone="p2"] {
  background: linear-gradient(180deg, #f3fbf7 0%, #ffffff 100%);
}

.recommendation-card[data-tone="p2"] .recommendation-card__head span {
  background: #dcfce7;
  color: #047857;
}

@media (max-width: 980px) {
  .recommendation-panel__grid {
    grid-template-columns: 1fr;
  }
}
</style>
