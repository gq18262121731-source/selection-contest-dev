<script setup lang="ts">
import { Clock3, Radio } from "lucide-vue-next";
import type { RobotTimelineItem } from "../../types/robot";

defineProps<{ events: RobotTimelineItem[] }>();

function formatTime(value: string) {
  return new Date(value).toLocaleTimeString("zh-CN", { hour12: false });
}
</script>

<template>
  <article class="robot-status-card robot-status-timeline">
    <header>
      <div><p>LIVE EVENTS</p><h2>最近状态事件</h2></div>
      <span>{{ events.length }} / 20</span>
    </header>
    <ol v-if="events.length">
      <li v-for="event in events" :key="event.id" :class="`is-${event.severity}`">
        <span class="robot-status-timeline__dot"><Radio :size="13" /></span>
        <div>
          <strong>{{ event.title }}</strong>
          <p>{{ event.message }}</p>
          <code v-if="event.code">{{ event.code }}</code>
        </div>
        <time><Clock3 :size="12" />{{ formatTime(event.timestamp) }}</time>
      </li>
    </ol>
    <div v-else class="robot-status-timeline__empty">
      <Radio :size="23" />
      <p>等待 `/ws/robot/status` 初始快照或增量事件。</p>
    </div>
  </article>
</template>

<style scoped>
.robot-status-card { border: 1px solid #dce6f0; border-radius: 18px; background: #fbfdff; box-shadow: 0 8px 24px rgba(35, 78, 112, 0.06); }
.robot-status-timeline { padding: 20px; }
.robot-status-timeline header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.robot-status-timeline header p { margin: 0; color: #47779c; font-size: 0.66rem; font-weight: 800; letter-spacing: 0.08em; }
.robot-status-timeline h2 { margin: 4px 0 0; color: #102a43; font-size: 1rem; }
.robot-status-timeline header > span { color: #71869a; font-family: var(--font-mono); font-size: 0.68rem; }
.robot-status-timeline ol { display: grid; gap: 0; margin: 15px 0 0; padding: 0; list-style: none; }
.robot-status-timeline li { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 10px; padding: 11px 0; border-top: 1px solid #e4ebf1; }
.robot-status-timeline__dot { width: 28px; height: 28px; display: grid; place-items: center; border-radius: 50%; background: #e7f1fa; color: #39739f; }
.robot-status-timeline li.is-error .robot-status-timeline__dot { background: #fbe5e2; color: #a53630; }
.robot-status-timeline li.is-warning .robot-status-timeline__dot { background: #fff0d5; color: #946213; }
.robot-status-timeline li.is-success .robot-status-timeline__dot { background: #dff3ea; color: #087653; }
.robot-status-timeline li > div { min-width: 0; }
.robot-status-timeline strong { color: #294b65; font-size: 0.77rem; }
.robot-status-timeline li p { margin: 4px 0 0; color: #667e92; font-size: 0.69rem; line-height: 1.45; }
.robot-status-timeline code { display: block; margin-top: 5px; color: #8c554f; font-family: var(--font-mono); font-size: 0.62rem; }
.robot-status-timeline time { display: flex; align-items: center; gap: 4px; color: #8295a5; font-family: var(--font-mono); font-size: 0.63rem; white-space: nowrap; }
.robot-status-timeline__empty { min-height: 120px; display: grid; place-content: center; justify-items: center; gap: 8px; color: #7b90a1; text-align: center; }
.robot-status-timeline__empty p { margin: 0; font-size: 0.72rem; }
@media (max-width: 560px) { .robot-status-timeline li { grid-template-columns: auto minmax(0, 1fr); } .robot-status-timeline time { grid-column: 2; } }
</style>
