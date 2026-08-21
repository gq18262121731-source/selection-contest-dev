<script setup lang="ts">
import { computed } from "vue";
import type { CommunityDashboardAlertItem } from "../../api/client";

const props = defineProps<{
  events: CommunityDashboardAlertItem[];
}>();

function toneFromLevel(level: number) {
  if (level >= 3) return "high";
  if (level === 2) return "medium";
  return "low";
}

const orderedEvents = computed(() =>
  [...props.events].sort(
    (left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime(),
  ),
);
</script>

<template>
  <section class="event-timeline">
    <header class="event-timeline__head">
      <div>
        <p class="event-timeline__eyebrow">Incident Timeline</p>
        <h3>异常事件时间线</h3>
        <p>按时间排序查看告警热点、对象和现场说明，便于交接班快速复述。</p>
      </div>
      <span class="event-timeline__count">{{ orderedEvents.length }} 条事件</span>
    </header>

    <div v-if="orderedEvents.length" class="event-timeline__list">
      <article
        v-for="event in orderedEvents"
        :key="event.alarm_id"
        class="timeline-item"
        :data-tone="toneFromLevel(event.alarm_level)"
      >
        <div class="timeline-item__rail">
          <span class="timeline-item__dot"></span>
          <span class="timeline-item__line"></span>
        </div>
        <div class="timeline-item__body">
          <div class="timeline-item__head">
            <strong>{{ event.elder_name ?? event.device_mac }}</strong>
            <time>{{ new Date(event.created_at).toLocaleString("zh-CN", { hour12: false }) }}</time>
          </div>
          <div class="timeline-item__meta">
            <span>{{ event.alarm_type }}</span>
            <span>{{ event.alarm_layer }}</span>
            <span>等级 {{ event.alarm_level }}</span>
          </div>
          <p>{{ event.message }}</p>
        </div>
      </article>
    </div>

    <div v-else class="event-timeline__empty">
      当前时间窗口没有异常事件，可继续按常规巡检与风险分层结果交接。
    </div>
  </section>
</template>

<style scoped>
.event-timeline,
.event-timeline__list {
  display: grid;
  gap: 18px;
}

.event-timeline {
  padding: 22px;
  border-radius: 26px;
  border: 1px solid var(--line-medium);
  background: #ffffff;
  box-shadow: 0 12px 26px rgba(15, 23, 42, 0.05);
}

.event-timeline__head {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: flex-start;
}

.event-timeline__eyebrow {
  margin: 0 0 8px;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  font-size: 0.72rem;
  font-weight: 800;
  color: var(--brand);
}

.event-timeline h3 {
  margin: 0;
  color: var(--text-main);
  font-family: var(--font-display);
  font-size: 1.35rem;
}

.event-timeline p {
  margin: 8px 0 0;
  color: var(--text-sub);
  line-height: 1.72;
}

.event-timeline__count {
  padding: 9px 14px;
  border-radius: 999px;
  background: #eef2ff;
  color: #1d4ed8;
  font-size: 0.8rem;
  font-weight: 800;
}

.timeline-item {
  display: grid;
  grid-template-columns: 24px 1fr;
  gap: 16px;
}

.timeline-item__rail {
  display: grid;
  justify-items: center;
  grid-template-rows: auto 1fr;
}

.timeline-item__dot {
  width: 14px;
  height: 14px;
  border-radius: 999px;
  border: 3px solid #ffffff;
  box-shadow: 0 0 0 1px rgba(15, 23, 42, 0.08);
}

.timeline-item__line {
  width: 2px;
  min-height: 100%;
  margin-top: 6px;
  background: linear-gradient(180deg, rgba(148, 163, 184, 0.35), rgba(148, 163, 184, 0.06));
}

.timeline-item:last-child .timeline-item__line {
  display: none;
}

.timeline-item__body {
  display: grid;
  gap: 10px;
  padding: 16px 18px;
  border-radius: 20px;
  background: #fbfbfa;
  border: 1px solid rgba(15, 23, 42, 0.08);
}

.timeline-item__head,
.timeline-item__meta {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 12px;
}

.timeline-item__head strong {
  color: var(--text-main);
}

.timeline-item__head time,
.timeline-item__meta {
  color: var(--text-sub);
  font-size: 0.82rem;
}

.timeline-item__meta span {
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.05);
}

.timeline-item__body p {
  margin: 0;
  color: var(--text-main);
}

.timeline-item[data-tone="high"] .timeline-item__dot {
  background: #dc2626;
}

.timeline-item[data-tone="medium"] .timeline-item__dot {
  background: #f59e0b;
}

.timeline-item[data-tone="low"] .timeline-item__dot {
  background: #16a34a;
}

.event-timeline__empty {
  padding: 18px;
  border-radius: 18px;
  background: #f8fafc;
  color: var(--text-sub);
}

@media (max-width: 760px) {
  .event-timeline__head {
    flex-direction: column;
  }
}
</style>
