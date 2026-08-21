<script setup lang="ts">
import { computed } from "vue";
import type { DeviceRecord, HealthSample } from "../api/client";

const props = defineProps<{
  device: DeviceRecord | null;
  sample: HealthSample | null;
  trend: HealthSample[];
  riskLabel: string;
}>();

const metricCards = computed(() => {
  const sample = props.sample;
  return [
    { label: "当前心率", value: sample ? `${sample.heart_rate}` : "--", unit: "bpm" },
    { label: "体温", value: sample ? sample.temperature.toFixed(1) : "--", unit: "°C" },
    { label: "血氧", value: sample ? `${sample.blood_oxygen}` : "--", unit: "%" },
    { label: "健康分", value: sample?.health_score ?? "--", unit: "" },
  ];
});

const observations = computed(() => {
  const sample = props.sample;
  const trend = props.trend;
  if (!sample) {
    return ["请选择设备，查看单设备详情、趋势摘要和观察建议。"];
  }

  const notes: string[] = [];
  if (sample.sos_flag) {
    notes.push("当前设备存在 SOS 标记，应优先核查佩戴人状态并确认现场响应。");
  }
  if (sample.blood_oxygen < 90) {
    notes.push("当前血氧低于 90%，属于优先处置区间。");
  } else if (sample.blood_oxygen < 93) {
    notes.push("当前血氧轻度偏低，建议缩短复测间隔。");
  }
  if (sample.temperature > 38) {
    notes.push("体温处于发热区间，建议结合精神状态和补水情况继续观察。");
  }
  if (sample.heart_rate > 110) {
    notes.push("心率偏高，需要结合活动状态、情绪变化和近期用药进一步判断。");
  }
  if (trend.length >= 2) {
    const start = trend[0];
    const end = trend[trend.length - 1];
    const hrDelta = end.heart_rate - start.heart_rate;
    const spo2Delta = end.blood_oxygen - start.blood_oxygen;
    if (hrDelta >= 8) {
      notes.push(`过去一段时间心率累计上升 ${hrDelta} bpm，存在持续波动迹象。`);
    }
    if (spo2Delta <= -2) {
      notes.push(`血氧较窗口起点下降 ${Math.abs(spo2Delta)}%，需要重点复测。`);
    }
  }
  if (!notes.length) {
    notes.push("当前生命体征总体平稳，建议维持常规监测节奏。");
  }
  return notes.slice(0, 4);
});

const lastTimestamp = computed(() => {
  if (!props.sample) return "暂无数据";
  return new Date(props.sample.timestamp).toLocaleString("zh-CN", { hour12: false });
});
</script>

<template>
  <section class="panel focus-panel">
    <div class="panel-head">
      <div>
        <h2>单设备深描</h2>
        <p class="panel-subtitle">围绕当前选中设备，给出现象更直观的生命体征剖面和观察建议。</p>
      </div>
      <span>{{ riskLabel }}</span>
    </div>
    <div v-if="device && sample" class="focus-layout">
      <div class="focus-identity">
        <div>
          <p>{{ device.device_name }}</p>
          <strong>{{ device.mac_address }}</strong>
        </div>
        <div class="focus-meta">
          <span>最近同步</span>
          <strong>{{ lastTimestamp }}</strong>
        </div>
      </div>
      <div class="metric-grid">
        <article v-for="metric in metricCards" :key="metric.label" class="metric-card">
          <span>{{ metric.label }}</span>
          <strong>{{ metric.value }}</strong>
          <small>{{ metric.unit }}</small>
        </article>
      </div>
      <div class="focus-observations">
        <h3>观察建议</h3>
        <ul>
          <li v-for="item in observations" :key="item">{{ item }}</li>
        </ul>
      </div>
    </div>
    <p v-else class="empty-copy">当前没有可展示的设备详情数据。</p>
  </section>
</template>
