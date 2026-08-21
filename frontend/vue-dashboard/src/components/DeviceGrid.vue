<script setup lang="ts">
import { computed, ref } from "vue";
import type { DeviceRecord, HealthSample } from "../api/client";

const props = defineProps<{
  devices: DeviceRecord[];
  latest: Record<string, HealthSample>;
  selectedMac: string;
}>();

defineEmits<{
  (event: "select", mac: string): void;
}>();

const search = ref("");
const filter = ref("all");

function riskTone(sample?: HealthSample) {
  if (!sample) return "idle";
  if (sample.sos_flag || sample.blood_oxygen < 90 || sample.heart_rate > 180 || sample.heart_rate < 40) {
    return "high";
  }
  if (sample.temperature > 38 || sample.heart_rate > 110 || sample.blood_oxygen < 93) {
    return "medium";
  }
  return "low";
}

function riskLabel(sample?: HealthSample) {
  return {
    idle: "待同步",
    low: "平稳",
    medium: "关注",
    high: "高风险",
  }[riskTone(sample)];
}

function statusLabel(status: string) {
  if (status === "warning") return "告警";
  if (status === "offline") return "离线";
  return "在线";
}

const filteredDevices = computed(() => {
  const keyword = search.value.trim().toLowerCase();
  return props.devices.filter((device) => {
    const sample = props.latest[device.mac_address];
    const tone = riskTone(sample);
    const matchesKeyword = !keyword || device.device_name.toLowerCase().includes(keyword) || device.mac_address.toLowerCase().includes(keyword);
    const matchesFilter =
      filter.value === "all" ||
      (filter.value === "high" && tone === "high") ||
      (filter.value === "attention" && tone === "medium") ||
      (filter.value === "sos" && Boolean(sample?.sos_flag));
    return matchesKeyword && matchesFilter;
  });
});
</script>

<template>
  <section class="panel device-panel">
    <div class="panel-head">
      <div>
        <h2>设备矩阵</h2>
        <p class="panel-subtitle">多设备实时总览，快速定位高风险对象与当前主视角设备。</p>
      </div>
      <span>{{ filteredDevices.length }} / {{ devices.length }} 台</span>
    </div>
    <div class="toolbar-stack">
      <input v-model="search" class="search-input" placeholder="搜索设备名或 MAC" />
      <div class="filter-row">
        <button class="filter-chip" :class="{ active: filter === 'all' }" @click="filter = 'all'">全部</button>
        <button class="filter-chip" :class="{ active: filter === 'high' }" @click="filter = 'high'">高风险</button>
        <button class="filter-chip" :class="{ active: filter === 'attention' }" @click="filter = 'attention'">需关注</button>
        <button class="filter-chip" :class="{ active: filter === 'sos' }" @click="filter = 'sos'">SOS</button>
      </div>
    </div>
    <div class="device-list">
      <button
        v-for="device in filteredDevices"
        :key="device.mac_address"
        class="device-card"
        :class="[
          { active: selectedMac === device.mac_address },
          `tone-${riskTone(latest[device.mac_address])}`,
        ]"
        @click="$emit('select', device.mac_address)"
      >
        <div class="device-card-top">
          <div>
            <p>{{ device.device_name }}</p>
            <strong>{{ device.mac_address }}</strong>
          </div>
          <span class="status-pill">{{ statusLabel(device.status) }}</span>
        </div>
        <div v-if="latest[device.mac_address]" class="metrics">
          <span>HR {{ latest[device.mac_address].heart_rate }}</span>
          <span>T {{ latest[device.mac_address].temperature.toFixed(1) }}℃</span>
          <span>SpO2 {{ latest[device.mac_address].blood_oxygen }}%</span>
          <span>分 {{ latest[device.mac_address].health_score ?? '--' }}</span>
        </div>
        <p v-else class="empty-copy">等待实时数据接入</p>
        <div class="device-card-footer">
          <span class="risk-chip" :class="`risk-${riskTone(latest[device.mac_address])}`">
            {{ riskLabel(latest[device.mac_address]) }}
          </span>
          <span v-if="latest[device.mac_address]?.sos_flag" class="sos-chip">SOS</span>
        </div>
      </button>
      <p v-if="!filteredDevices.length" class="empty-copy">当前筛选条件下没有匹配设备。</p>
    </div>
  </section>
</template>

<style scoped>
.device-panel {
  display: grid;
  gap: 16px;
  background:
    radial-gradient(circle at top right, rgba(34, 211, 238, 0.06), transparent 40%),
    linear-gradient(180deg, rgba(10, 16, 30, 0.99), rgba(7, 12, 22, 0.99));
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.panel-head h2 {
  margin: 0;
  color: #e2f0ff;
  font-family: var(--font-display);
}

.panel-head > span {
  color: #4d7a94;
  font-size: 0.9rem;
  flex-shrink: 0;
}

.panel-subtitle {
  margin: 6px 0 0;
  color: #6ea8c8;
  font-size: 0.9rem;
  line-height: 1.6;
}

.toolbar-stack {
  display: grid;
  gap: 10px;
}

.search-input {
  width: 100%;
  padding: 10px 14px;
  border-radius: 12px;
  background: rgba(13, 20, 38, 0.96);
  border: 1px solid rgba(56, 189, 248, 0.14);
  color: #c8e0f4;
  font-size: 0.92rem;
  outline: none;
  box-sizing: border-box;
  transition: border-color 160ms ease;
}

.search-input::placeholder {
  color: #4d7a94;
}

.search-input:focus {
  border-color: rgba(34, 211, 238, 0.40);
}

.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.filter-chip {
  padding: 6px 14px;
  border-radius: 999px;
  background: rgba(13, 20, 38, 0.96);
  border: 1px solid rgba(56, 189, 248, 0.12);
  color: #6ea8c8;
  font-size: 0.84rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 150ms ease;
}

.filter-chip:hover,
.filter-chip.active {
  background: rgba(34, 211, 238, 0.12);
  border-color: rgba(34, 211, 238, 0.36);
  color: #22d3ee;
}

.device-list {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
}

.device-card {
  display: grid;
  gap: 8px;
  padding: 14px 16px;
  border-radius: 20px;
  background: rgba(13, 20, 38, 0.96);
  border: 1px solid rgba(56, 189, 248, 0.10);
  text-align: left;
  cursor: pointer;
  transition: transform 150ms ease, border-color 150ms ease, box-shadow 150ms ease;
}

.device-card:hover,
.device-card.active {
  transform: translateY(-1px);
  box-shadow: 0 12px 28px rgba(0, 0, 0, 0.28);
}

.device-card.active {
  border-color: rgba(34, 211, 238, 0.38);
  background: rgba(18, 28, 52, 0.98);
}

.device-card-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
}

.device-card-top p {
  margin: 0;
  color: #c8e0f4;
  font-size: 0.92rem;
  font-weight: 600;
}

.device-card-top strong {
  color: #4d7a94;
  font-size: 0.78rem;
  font-weight: 400;
}

.status-pill {
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(52, 211, 153, 0.12);
  color: #34d399;
  font-size: 0.74rem;
  font-weight: 700;
  flex-shrink: 0;
  border: 1px solid rgba(52, 211, 153, 0.20);
}

.metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.metrics span {
  padding: 3px 8px;
  border-radius: 8px;
  background: rgba(56, 189, 248, 0.07);
  color: #7eb8d4;
  font-size: 0.78rem;
  font-weight: 600;
}

.empty-copy {
  margin: 0;
  color: #4d7a94;
  font-size: 0.88rem;
  line-height: 1.6;
}

.device-card-footer {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.risk-chip {
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 0.76rem;
  font-weight: 700;
  border: 1px solid transparent;
}

.risk-idle {
  background: rgba(56, 189, 248, 0.08);
  color: #4d7a94;
  border-color: rgba(56, 189, 248, 0.12);
}

.risk-low {
  background: rgba(52, 211, 153, 0.10);
  color: #34d399;
  border-color: rgba(52, 211, 153, 0.18);
}

.risk-medium {
  background: rgba(251, 146, 60, 0.10);
  color: #fb923c;
  border-color: rgba(251, 146, 60, 0.20);
}

.risk-high {
  background: rgba(248, 113, 122, 0.10);
  color: #f87171;
  border-color: rgba(248, 113, 122, 0.20);
}

.tone-high {
  border-color: rgba(248, 113, 122, 0.22);
  background: rgba(22, 10, 12, 0.96);
}

.tone-medium {
  border-color: rgba(251, 146, 60, 0.20);
  background: rgba(20, 14, 8, 0.96);
}

.tone-low {
  border-color: rgba(52, 211, 153, 0.16);
}

.sos-chip {
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(248, 113, 122, 0.14);
  color: #f87171;
  font-size: 0.76rem;
  font-weight: 800;
  border: 1px solid rgba(248, 113, 122, 0.28);
  animation: sos-pulse 1.2s ease-in-out infinite;
}

@keyframes sos-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
</style>
