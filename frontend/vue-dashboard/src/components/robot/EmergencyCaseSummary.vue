<script setup lang="ts">
import { computed } from "vue";
import { AlertTriangle, MapPin } from "lucide-vue-next";
import type { RobotAlarmExtension, RobotEmergencyCase } from "../../types/robot";

const props = defineProps<{
  emergencyCase: RobotEmergencyCase | null;
  bootstrapAlarm: RobotAlarmExtension | null;
}>();

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function display(value: unknown): string {
  return typeof value === "string" && value.trim() ? value : "未提供";
}

const eventMetadata = computed(() => {
  const metadata = asRecord(props.emergencyCase?.metadata);
  return asRecord(metadata?.event) ?? metadata;
});

const rows = computed<Array<[string, unknown]>>(() => {
  const current = props.emergencyCase;
  const bootstrap = props.bootstrapAlarm;
  const probability = current?.fall_probability ?? bootstrap?.fall_probability;
  return [
    ["incident_id", current?.incident_id ?? bootstrap?.incident_id],
    ["camera_id", current?.camera_id ?? bootstrap?.camera_id],
    ["area_id", current?.area_id ?? bootstrap?.area_id],
    ["区域", current?.area_name ?? bootstrap?.area_name],
    ["event_type", eventMetadata.value?.event_type ?? bootstrap?.event_type ?? "fall_confirmed"],
    ["发生时间", eventMetadata.value?.occurred_at ?? eventMetadata.value?.timestamp ?? bootstrap?.occurred_at],
    ["风险等级", current?.risk_level ?? bootstrap?.risk_level],
    ["跌倒概率", typeof probability === "number" ? `${(probability * 100).toFixed(1)}%` : null],
    ["alarm_id", current?.alarm_id ?? bootstrap?.alarm_id],
    ["robot_task_id", current?.robot_task_id ?? bootstrap?.robot_task_id],
  ];
});
</script>

<template>
  <article class="emergency-card">
    <header>
      <span><AlertTriangle :size="18" /></span>
      <div><p>INCIDENT SUMMARY</p><h2>跌倒事件摘要</h2></div>
    </header>
    <dl>
      <div v-for="[label, value] in rows" :key="label">
        <dt>{{ label }}</dt>
        <dd>{{ display(value) }}</dd>
      </div>
    </dl>
    <p class="privacy-note">
      <MapPin :size="14" />
      仅展示事件文字信息，不加载固定摄像头视频、快照或边界框。
    </p>
  </article>
</template>

<style scoped>
.emergency-card { padding: 18px; border: 1px solid #dce6f0; border-radius: 18px; background: #fff; box-shadow: 0 8px 24px rgba(35, 78, 112, .055); }
header { display: flex; align-items: center; gap: 10px; }
header > span { display: grid; width: 36px; height: 36px; place-items: center; border-radius: 10px; background: #fff1e8; color: #b45309; }
header p { margin: 0; color: #9a5a20; font-size: .62rem; font-weight: 850; letter-spacing: .09em; }
h2 { margin: 3px 0 0; color: #102a43; font-size: .98rem; }
dl { display: grid; margin: 14px 0 0; }
dl > div { display: grid; grid-template-columns: 92px minmax(0, 1fr); gap: 9px; padding: 9px 0; border-top: 1px solid #e7edf2; }
dt { color: #74899b; font-size: .67rem; }
dd { margin: 0; color: #34566f; font-family: var(--font-mono); font-size: .68rem; font-weight: 700; overflow-wrap: anywhere; }
.privacy-note { display: flex; align-items: flex-start; gap: 7px; margin: 12px 0 0; padding: 10px; border-radius: 9px; background: #f5f8fb; color: #6a8194; font-size: .65rem; line-height: 1.45; }
.privacy-note svg { flex: 0 0 auto; margin-top: 1px; }
</style>
