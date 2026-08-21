<script setup lang="ts">
import type { AlarmRecord, IntelligentDeviceAnalysis } from "../api/client";

defineProps<{ analysis: IntelligentDeviceAnalysis | null; deviceName: string; focusAlarm: AlarmRecord | null }>();

function readyText(analysis: IntelligentDeviceAnalysis | null) {
  if (!analysis) return "未选择设备";
  return analysis.ready ? "分析完成" : "等待样本积累";
}
</script>

<template>
  <section class="surface local-panel">
    <div class="local-head">
      <div>
        <p class="label">Insight</p>
        <h2>AI 风险解释</h2>
        <p>把 AI 结果放在辅助层，用来解释“为什么值得关注”，而不是替代人工判断。</p>
      </div>
      <span class="tag">{{ readyText(analysis) }}</span>
    </div>
    <div class="insight-grid">
      <article>
        <span>当前对象</span>
        <strong>{{ deviceName || "尚未选择" }}</strong>
        <small>{{ analysis?.device_mac ?? "-" }}</small>
      </article>
      <article>
        <span>异常概率</span>
        <strong>{{ analysis?.ready ? `${((analysis?.probability ?? 0) * 100).toFixed(0)}%` : "--" }}</strong>
        <small>评分 {{ analysis?.score?.toFixed?.(2) ?? "--" }}</small>
      </article>
      <article>
        <span>漂移 / 重建</span>
        <strong>{{ analysis?.ready ? analysis?.drift_score?.toFixed?.(2) ?? "--" : "--" }}</strong>
        <small>{{ analysis?.ready ? analysis?.reconstruction_score?.toFixed?.(2) ?? "--" : "--" }}</small>
      </article>
    </div>
    <div class="note-grid">
      <article class="note">
        <h3>解释</h3>
        <p>{{ analysis?.reason ?? analysis?.message ?? "当前样本不足，系统暂未形成可依赖的解释。" }}</p>
      </article>
      <article class="note">
        <h3>关联告警</h3>
        <p v-if="focusAlarm">{{ focusAlarm.message }}</p>
        <p v-else>当前聚焦对象暂无活动告警，可继续观察趋势变化。</p>
      </article>
    </div>
  </section>
</template>

<style scoped>
.local-panel { display: grid; gap: 14px; }
.local-head { display: flex; justify-content: space-between; gap: 14px; align-items: start; }
.label { margin: 0 0 6px; text-transform: uppercase; letter-spacing: .16em; font-size: .76rem; color: var(--brand); font-weight: 700; }
.local-head p:last-child, .insight-grid span, .insight-grid small, .note p { color: var(--text-sub); }
.tag { border-radius: 999px; padding: 8px 12px; background: rgba(47,139,104,.12); color: var(--brand); font-size: .82rem; font-weight: 700; }
.insight-grid, .note-grid { display: grid; gap: 12px; grid-template-columns: repeat(3, minmax(0,1fr)); }
.note-grid { grid-template-columns: repeat(2, minmax(0,1fr)); }
.insight-grid article, .note { border: 1px solid rgba(33,108,102,.12); border-radius: 14px; background: rgba(255,255,255,.9); padding: 14px; }
.insight-grid strong { display: block; margin-top: 8px; font-size: 1.6rem; line-height: 1; }
.note h3 { margin: 0 0 10px; font-size: 1rem; }
.note p { margin: 0; line-height: 1.7; }
@media (max-width: 900px) { .local-head, .insight-grid, .note-grid { grid-template-columns: 1fr; flex-direction: column; } }
</style>
