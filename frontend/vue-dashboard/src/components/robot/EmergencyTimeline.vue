<script setup lang="ts">
import { computed } from "vue";
import { Activity, CircleCheck, CircleX, Clock3 } from "lucide-vue-next";
import type { RobotEmergencyEvent, RobotStatusEvent } from "../../types/robot";

const props = defineProps<{
  events: RobotEmergencyEvent[];
  liveEvents: RobotStatusEvent[];
}>();

const labels: Record<string, string> = {
  emergency_case_created: "应急案例已创建",
  emergency_dispatch_blocked: "应急派发被联锁阻断",
  emergency_dispatched: "Mock 机器人任务已派发",
  task_arrived: "Mock 到达观察点",
  voice_prompting: "开始 Mock 语音询问",
  waiting_response: "等待老人回应",
  dialogue_result: "已记录对话结果",
  dialogue_result_recorded: "已同步对话判断",
  waiting_admin_confirmation: "等待管理员确认",
  alarm_escalation_required: "告警升级人工处置",
  return_home_requested: "已请求 Mock 返航",
  return_home_completed: "Mock 返航完成",
  emergency_completed: "应急闭环完成",
  task_failed: "任务失败",
  task_cancelled: "任务取消",
};

type TimelineRow = {
  id: string;
  type: string;
  title: string;
  message: string;
  timestamp: string;
  severity: "normal" | "success" | "critical";
};

const rows = computed<TimelineRow[]>(() => {
  const stored = props.events.map((event) => ({
    id: event.event_id,
    type: event.event_type,
    title: labels[event.event_type] ?? event.event_type,
    message: event.message || event.execution_state || "状态已更新",
    timestamp: event.occurred_at,
    severity: ["task_failed", "task_cancelled", "emergency_dispatch_blocked"].includes(event.event_type)
      ? "critical" as const
      : ["return_home_completed", "emergency_completed"].includes(event.event_type)
        ? "success" as const
        : "normal" as const,
  }));
  const knownTypes = new Set(stored.map((item) => `${item.type}:${item.timestamp}`));
  const live = props.liveEvents
    .filter((event) => !knownTypes.has(`${event.type}:${event.timestamp}`))
    .map((event) => ({
      id: `ws-${event.sequence}`,
      type: event.type,
      title: labels[event.type] ?? event.type,
      message: "WebSocket 增量状态已同步",
      timestamp: event.timestamp,
      severity: ["task_failed", "task_cancelled", "emergency_dispatch_blocked"].includes(event.type)
        ? "critical" as const
        : ["return_home_completed", "emergency_completed"].includes(event.type)
          ? "success" as const
          : "normal" as const,
    }));
  return [...stored, ...live]
    .sort((left, right) => new Date(right.timestamp).getTime() - new Date(left.timestamp).getTime())
    .slice(0, 50);
});

function formatTime(value: string) {
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}
</script>

<template>
  <article class="timeline-card">
    <header>
      <span><Activity :size="18" /></span>
      <div><p>EMERGENCY TIMELINE</p><h2>应急时间线</h2></div>
      <em>最多 50 条</em>
    </header>
    <div v-if="rows.length" class="timeline">
      <article v-for="row in rows" :key="row.id" :class="`is-${row.severity}`">
        <span>
          <CircleCheck v-if="row.severity === 'success'" :size="15" />
          <CircleX v-else-if="row.severity === 'critical'" :size="15" />
          <Clock3 v-else :size="15" />
        </span>
        <div>
          <strong>{{ row.title }}</strong>
          <p>{{ row.message }}</p>
          <time>{{ formatTime(row.timestamp) }} · {{ row.type }}</time>
        </div>
      </article>
    </div>
    <div v-else class="empty">暂无应急导航事件。</div>
  </article>
</template>

<style scoped>
.timeline-card { padding: 20px; border: 1px solid #dce6f0; border-radius: 18px; background: #fff; box-shadow: 0 8px 24px rgba(35, 78, 112, .055); }
header { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 10px; }
header > span { display: grid; width: 38px; height: 38px; place-items: center; border-radius: 11px; background: #edf3f7; color: #4f7088; }
header p { margin: 0; color: #47779c; font-size: .63rem; font-weight: 850; letter-spacing: .09em; }
h2 { margin: 3px 0 0; color: #102a43; font-size: 1rem; }
header em { color: #8092a0; font-size: .62rem; font-style: normal; }
.timeline { position: relative; display: grid; gap: 0; margin-top: 15px; }
.timeline::before { content: ""; position: absolute; left: 14px; top: 13px; bottom: 13px; width: 1px; background: #dbe5ec; }
.timeline article { position: relative; z-index: 1; display: grid; grid-template-columns: 29px 1fr; gap: 10px; padding: 8px 0; }
.timeline article > span { display: grid; width: 29px; height: 29px; place-items: center; border: 1px solid #cfdae3; border-radius: 50%; background: #fff; color: #5f7b90; }
.timeline article.is-success > span { border-color: #a9ddca; color: #087653; }
.timeline article.is-critical > span { border-color: #efb6b0; color: #b23d34; }
.timeline strong { color: #31546d; font-size: .7rem; }
.timeline p { margin: 3px 0; color: #607b8f; font-size: .66rem; line-height: 1.4; }
.timeline time { color: #8a9aa6; font-family: var(--font-mono); font-size: .57rem; }
.empty { margin-top: 14px; padding: 24px; border: 1px dashed #cbd9e4; border-radius: 11px; color: #758b9d; font-size: .7rem; text-align: center; }
</style>
