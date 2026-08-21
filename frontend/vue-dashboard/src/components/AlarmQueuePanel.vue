<script setup lang="ts">
import type { AlarmQueueItem, MobilePushRecord } from "../api/client";

defineProps<{ queue: AlarmQueueItem[]; mobilePushes: MobilePushRecord[] }>();

function priorityLabel(level: number) {
  if (level <= 1) return "紧急";
  if (level === 2) return "高优先";
  if (level === 3) return "关注";
  return "通知";
}
</script>

<template>
  <section class="surface local-panel">
    <div class="local-head">
      <div>
        <p class="label">Queue</p>
        <h2>告警优先队列</h2>
        <p>谁需要先处理、先联系，这里给出推荐排序，减少值班人员手动判断负担。</p>
      </div>
      <span class="tag">{{ queue.length }} 条待处理</span>
    </div>
    <div class="stack">
      <article v-for="item in queue.slice(0, 5)" :key="item.alarm.id" class="card">
        <div class="row"><strong>{{ item.alarm.device_mac }}</strong><span class="chip">{{ priorityLabel(item.alarm.alarm_level) }}</span></div>
        <p>{{ item.alarm.message }}</p>
        <small>{{ item.alarm.alarm_layer }} / 概率 {{ ((item.alarm.anomaly_probability ?? 0) * 100).toFixed(0) }}%</small>
      </article>
      <div v-if="!queue.length" class="empty">当前没有待处理告警，值守压力较低。</div>
    </div>
    <div class="subhead">
      <h3>移动端推送回执</h3>
      <span>{{ mobilePushes.length }} 条</span>
    </div>
    <div class="stack">
      <article v-for="push in mobilePushes.slice(0, 4)" :key="push.id" class="card">
        <strong>{{ push.title }}</strong>
        <p>{{ push.body }}</p>
        <small>{{ push.device_mac }} / {{ new Date(push.created_at).toLocaleString("zh-CN", { hour12: false }) }}</small>
      </article>
      <div v-if="!mobilePushes.length" class="empty">当前没有推送记录，说明最近没有需要额外通知的告警。</div>
    </div>
  </section>
</template>

<style scoped>
.local-panel, .stack { display: grid; gap: 12px; }
.local-head, .row, .subhead { display: flex; justify-content: space-between; gap: 12px; align-items: start; }
.label { margin: 0 0 6px; text-transform: uppercase; letter-spacing: .16em; font-size: .76rem; color: var(--brand); font-weight: 700; }
.local-head p:last-child, .card p, .card small, .empty { color: var(--text-sub); }
.tag, .chip { border-radius: 999px; padding: 7px 11px; font-size: .8rem; font-weight: 700; }
.tag { background: rgba(33,108,102,.1); color: var(--brand); }
.chip { background: rgba(201,141,43,.14); color: #a16207; }
.card { border: 1px solid rgba(33,108,102,.12); border-radius: 14px; background: rgba(255,255,255,.9); padding: 14px; }
.card p { margin: 8px 0 6px; line-height: 1.65; }
.subhead h3 { margin: 0; font-size: 1rem; }
.empty { border: 1px dashed rgba(33,108,102,.22); border-radius: 14px; padding: 14px; }
</style>
