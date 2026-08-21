<script setup lang="ts">
import { computed } from "vue";
import type { CommunityOverview } from "../api/client";

const props = defineProps<{ overview: CommunityOverview | null; avgScore: number; avgSpo2: number; sosCount: number }>();
const clusters = computed(() => ({
  healthy: props.overview?.clusters.healthy?.length ?? 0,
  attention: props.overview?.clusters.attention?.length ?? 0,
  danger: props.overview?.clusters.danger?.length ?? 0,
}));
</script>

<template>
  <section class="surface local-panel">
    <div class="local-head">
      <div>
        <p class="label">状态概览</p>
        <h2>群体态势补充信息</h2>
        <p>用于解释社区整体分层情况，作为总览页的补充说明，而不是替代首屏风险焦点。</p>
      </div>
      <span class="tag">异常分 {{ overview?.intelligent_anomaly_score?.toFixed(2) ?? "0.00" }}</span>
    </div>
    <div class="kpi-grid">
      <article><span>平均健康分</span><strong>{{ avgScore }}</strong></article>
      <article><span>平均血氧</span><strong>{{ avgSpo2 }}%</strong></article>
      <article><span>SOS 数量</span><strong>{{ sosCount }}</strong></article>
      <article><span>在线设备</span><strong>{{ overview?.device_count ?? 0 }}</strong></article>
    </div>
    <div class="cluster-grid">
      <article class="tone-ok"><span>稳定</span><strong>{{ clusters.healthy }}</strong></article>
      <article class="tone-attention"><span>关注</span><strong>{{ clusters.attention }}</strong></article>
      <article class="tone-risk"><span>风险</span><strong>{{ clusters.danger }}</strong></article>
    </div>
  </section>
</template>

<style scoped>
.local-panel { display: grid; gap: 14px; }
.local-head { display: flex; justify-content: space-between; gap: 14px; align-items: start; }
.label { margin: 0 0 6px; text-transform: uppercase; letter-spacing: .16em; font-size: .76rem; color: var(--brand); font-weight: 700; }
.local-head p:last-child, .kpi-grid span, .cluster-grid span { color: var(--text-sub); }
.tag { padding: 8px 12px; border-radius: 999px; background: rgba(33,108,102,.1); color: var(--brand); font-size: .82rem; font-weight: 700; }
.kpi-grid, .cluster-grid { display: grid; gap: 12px; grid-template-columns: repeat(4, minmax(0,1fr)); }
.cluster-grid { grid-template-columns: repeat(3, minmax(0,1fr)); }
.kpi-grid article, .cluster-grid article { border: 1px solid rgba(33,108,102,.12); border-radius: 14px; background: rgba(255,255,255,.9); padding: 14px; }
.kpi-grid strong, .cluster-grid strong { display: block; margin-top: 8px; font-size: 1.5rem; }
.tone-ok { box-shadow: inset 0 0 0 1px rgba(47,139,104,.16); }
.tone-attention { box-shadow: inset 0 0 0 1px rgba(201,141,43,.18); }
.tone-risk { box-shadow: inset 0 0 0 1px rgba(211,95,95,.18); }
@media (max-width: 900px) { .local-head, .kpi-grid, .cluster-grid { grid-template-columns: 1fr; flex-direction: column; } }
</style>
