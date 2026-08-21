<script setup lang="ts">
import type { AlarmRecord } from "../api/client";

defineProps<{ alarms: AlarmRecord[] }>();

defineEmits<{
  (event: "ack", alarmId: string): void;
}>();

function alarmTone(level: number) {
  if (level <= 1) return "sos";
  if (level === 2) return "critical";
  if (level === 3) return "warning";
  return "notice";
}

function alarmLabel(level: number) {
  if (level <= 1) return "SOS";
  if (level === 2) return "严重";
  if (level === 3) return "预警";
  return "通知";
}
</script>

<template>
  <section class="panel alarm-panel">
    <div class="panel-head">
      <div>
        <h2>活动告警</h2>
        <p class="panel-subtitle">按优先级展示当前仍需跟进的告警，帮助社区值守人员快速完成分诊、联系与闭环。</p>
      </div>
      <span>{{ alarms.length }} 条</span>
    </div>

    <div class="alarm-list">
      <article
        v-for="alarm in alarms"
        :key="alarm.id"
        class="alarm-card"
        :class="`alarm-${alarmTone(alarm.alarm_level)}`"
      >
        <div class="alarm-copy">
          <div class="alarm-title-row">
            <p>{{ alarm.device_mac }}</p>
            <span class="alarm-tag">{{ alarmLabel(alarm.alarm_level) }}</span>
          </div>
          <strong>{{ alarm.message }}</strong>
          <small>{{ new Date(alarm.created_at).toLocaleString("zh-CN", { hour12: false }) }}</small>
        </div>
        <div class="alarm-actions">
          <span>优先级 {{ alarm.alarm_level }}</span>
          <button @click="$emit('ack', alarm.id)">标记已处理</button>
        </div>
      </article>
      <p v-if="!alarms.length" class="empty-copy">当前没有活动告警，系统运行状态平稳。</p>
    </div>
  </section>
</template>
