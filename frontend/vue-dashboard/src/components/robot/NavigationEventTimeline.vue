<script setup lang="ts">
import { Clock3 } from "lucide-vue-next";
import type { RobotTimelineItem } from "../../types/robot";

defineProps<{ items: RobotTimelineItem[] }>();

function formatTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleTimeString("zh-CN", { hour12: false });
}
</script>

<template>
  <section class="timeline-card">
    <header>
      <span class="icon"><Clock3 :size="18" /></span>
      <div>
        <h3>导航事件</h3>
        <p>保留本页最近 30 条 Mock WebSocket 事件。</p>
      </div>
    </header>
    <ol v-if="items.length">
      <li v-for="item in items" :key="item.id" :class="`item--${item.severity}`">
        <i></i>
        <div>
          <strong>{{ item.title }}</strong>
          <span>{{ item.message }}</span>
          <code v-if="item.code">{{ item.code }}</code>
        </div>
        <time>{{ formatTime(item.timestamp) }}</time>
      </li>
    </ol>
    <div v-else class="empty">等待导航状态事件</div>
  </section>
</template>

<style scoped>
.timeline-card { display: grid; gap: 14px; padding: 20px; border: 1px solid #dbe4ee; border-radius: 18px; background: #fff; }
header { display: grid; grid-template-columns: auto 1fr; gap: 11px; }
.icon { display: grid; width: 36px; height: 36px; place-items: center; border-radius: 10px; background: #f1f5f9; color: #475569; }
h3 { margin: 0 0 3px; color: #0f172a; font-size: .98rem; }
p { margin: 0; color: #64748b; font-size: .74rem; }
ol { position: relative; display: grid; gap: 12px; max-height: 360px; overflow: auto; padding: 1px 3px 1px 0; margin: 0; list-style: none; }
li { display: grid; grid-template-columns: auto 1fr auto; gap: 9px; align-items: start; }
li > i { width: 8px; height: 8px; margin-top: 5px; border-radius: 50%; background: #64748b; box-shadow: 0 0 0 4px #f1f5f9; }
.item--success > i { background: #16a34a; box-shadow: 0 0 0 4px #dcfce7; }
.item--warning > i { background: #d97706; box-shadow: 0 0 0 4px #fef3c7; }
.item--error > i { background: #dc2626; box-shadow: 0 0 0 4px #fee2e2; }
li div { display: grid; gap: 2px; min-width: 0; }
li strong { color: #334155; font-size: .73rem; text-transform: capitalize; }
li span { color: #64748b; font-size: .69rem; line-height: 1.4; }
li code { width: fit-content; padding: 2px 5px; border-radius: 4px; background: #f1f5f9; color: #475569; font-size: .59rem; }
time { color: #94a3b8; font-size: .62rem; }
.empty { padding: 24px; border: 1px dashed #cbd5e1; border-radius: 10px; color: #94a3b8; text-align: center; font-size: .74rem; }
</style>
