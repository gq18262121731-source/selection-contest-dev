<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from "vue";
import type { CommunityDashboardElderItem } from "../api/client";
import { riskLevelToChinese } from "../utils/riskLevel";

const props = defineProps<{
  elders: CommunityDashboardElderItem[];
  selectedElderId: string;
}>();

const emit = defineEmits<{
  select: [elderId: string];
}>();

type CardTone = "sos" | "no-device" | "offline" | "pending" | "risk-high" | "risk-medium" | "risk-low";

const railGridRef = ref<HTMLElement | null>(null);

function elderHasObservedRealtime(elder: CommunityDashboardElderItem) {
  return Boolean(
    elder.latest_timestamp
      || elder.heart_rate != null
      || elder.blood_oxygen != null
      || elder.blood_pressure
      || elder.temperature != null
      || elder.latest_health_score != null,
  );
}

function elderHasActiveSos(elder: CommunityDashboardElderItem) {
  return elder.sos_active === true || Boolean(elder.active_sos_alarm_id);
}

function elderTone(elder: CommunityDashboardElderItem): CardTone {
  if (elderHasActiveSos(elder)) return "sos";
  if (!elder.device_mac || elder.device_status === "no_device") return "no-device";
  if (elder.device_status === "offline") return "offline";
  if (elder.device_status === "pending" && !elderHasObservedRealtime(elder)) return "pending";
  if (elder.risk_level === "high") return "risk-high";
  if (elder.risk_level === "medium") return "risk-medium";
  return "risk-low";
}

function elderLabel(elder: CommunityDashboardElderItem): string {
  if (elderHasActiveSos(elder)) return "告警中";
  if (!elder.device_mac || elder.device_status === "no_device") return "无设备";
  if (elder.device_status === "offline") return "离线";
  if (elder.device_status === "pending" && !elderHasObservedRealtime(elder)) return "待同步";
  return "在线";
}

function elderMeta(elder: CommunityDashboardElderItem): string {
  if (!elder.device_mac || elder.device_status === "no_device") {
    return `${elder.apartment} · 等待移动端绑定手环`;
  }
  if (elder.device_status === "offline") {
    return `${elder.apartment} · 设备暂时离线`;
  }
  if (elder.device_status === "pending" && !elderHasObservedRealtime(elder)) {
    return `${elder.apartment} · 已绑定，等待首包`;
  }
  return `${elder.apartment} · 风险 ${riskLevelToChinese(elder.structured_health?.risk_level ?? elder.risk_level)}`;
}

const noDeviceCount = computed(() => props.elders.filter((elder) => !elder.device_mac || elder.device_status === "no_device").length);
const offlineCount = computed(() => props.elders.filter((elder) => elder.device_status === "offline").length);

async function scrollSelectedIntoView() {
  if (!props.selectedElderId) return;
  await nextTick();
  const target = railGridRef.value?.querySelector<HTMLElement>(`[data-elder-id="${props.selectedElderId}"]`);
  target?.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
}

watch(() => props.selectedElderId, () => {
  void scrollSelectedIntoView();
});

onMounted(() => {
  void scrollSelectedIntoView();
});
</script>

<template>
  <section class="device-rail">
    <div class="device-rail__head">
      <div>
        <p class="section-eyebrow">社区监护总览</p>
        <h2>老人监护对象</h2>
      </div>
      <small>先按老人查看绑定状态；只有已绑定设备的老人，点进去后才会加载实时曲线和监护数据。</small>
    </div>

    <div class="device-rail__meta">
      <span class="summary-badge">老人 {{ elders.length }}</span>
      <span class="summary-badge">无设备 {{ noDeviceCount }}</span>
      <span class="summary-badge">离线 {{ offlineCount }}</span>
    </div>

    <div ref="railGridRef" class="device-rail__grid">
      <button
        v-for="elder in elders"
        :key="elder.elder_id"
        type="button"
        class="device-pill"
        :data-elder-id="elder.elder_id"
        :class="[elderTone(elder), { 'device-pill--active': selectedElderId === elder.elder_id }]"
        @click="emit('select', elder.elder_id)"
      >
        <div class="device-pill__top">
          <strong>{{ elder.elder_name }}</strong>
          <span class="device-pill__state">{{ elderLabel(elder) }}</span>
        </div>
        <small>{{ elder.device_mac ?? "未绑定手环" }}</small>
        <span class="device-pill__meta">{{ elderMeta(elder) }}</span>
      </button>
    </div>
  </section>
</template>

<style scoped>
.device-rail {
  display: grid;
  gap: 18px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 24px;
  padding: 24px;
  box-shadow: 0 4px 16px rgba(15, 23, 42, 0.04);
}

.device-rail__head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  padding-bottom: 16px;
  border-bottom: 1px solid #e2e8f0;
}

.device-rail__head h2 {
  margin: 0;
  color: #0f172a;
  font-family: var(--font-display);
  font-size: 1.35rem;
  font-weight: 700;
  letter-spacing: -0.02em;
}

.device-rail__head small {
  color: #64748b;
  font-size: 0.88rem;
  line-height: 1.6;
  max-width: 480px;
}

.device-pill__meta {
  color: #64748b;
  font-size: 0.82rem;
  line-height: 1.5;
}

.device-rail__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.device-rail__grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  max-width: 100%;
  overflow-x: hidden;
}

.device-pill {
  display: grid;
  gap: 10px;
  padding: 18px 20px;
  border-radius: 16px;
  border: 2px solid #e2e8f0;
  background: #ffffff;
  text-align: left;
  cursor: pointer;
  transition: all 200ms ease;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.03);
  position: relative;
  overflow: hidden;
}

.device-pill::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 4px;
  background: linear-gradient(90deg, #3b82f6, #2563eb);
  opacity: 0;
  transition: opacity 200ms ease;
}

.device-pill:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.08);
  border-color: #cbd5e1;
}

.device-pill--active {
  border-color: #3b82f6;
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1), 0 8px 20px rgba(59, 130, 246, 0.15);
}

.device-pill--active::before {
  opacity: 1;
}

.device-pill__top {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.device-pill strong {
  color: #0f172a;
  font-size: 1.05rem;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.device-pill small {
  color: #64748b;
  font-size: 0.82rem;
  font-weight: 500;
  font-family: var(--font-mono);
}

.device-pill__state {
  padding: 6px 12px;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 700;
  flex-shrink: 0;
  letter-spacing: 0.02em;
}

/* 状态样式 */
.no-device {
  border-color: #e2e8f0;
  background: #f8fafc;
}

.no-device .device-pill__state {
  background: #f1f5f9;
  color: #64748b;
  border: 1px solid #cbd5e1;
}

.offline {
  border-color: #bfdbfe;
  background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
}

.offline .device-pill__state {
  background: #dbeafe;
  color: #1e40af;
  border: 1px solid #93c5fd;
}

.pending {
  border-color: #fde68a;
  background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
}

.pending .device-pill__state {
  background: #fef08a;
  color: #92400e;
  border: 1px solid #fde047;
}

.sos {
  border-color: #fca5a5;
  background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
  box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.1), 0 8px 20px rgba(239, 68, 68, 0.2);
  animation: pulse-sos 2s infinite;
}

.sos::before {
  background: linear-gradient(90deg, #ef4444, #dc2626);
  opacity: 1;
}

.sos .device-pill__state {
  background: #fecaca;
  color: #991b1b;
  border: 1px solid #f87171;
  animation: pulse-state 2s infinite;
}

@keyframes pulse-sos {
  0%, 100% {
    box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.1), 0 8px 20px rgba(239, 68, 68, 0.2);
  }
  50% {
    box-shadow: 0 0 0 6px rgba(239, 68, 68, 0.15), 0 12px 28px rgba(239, 68, 68, 0.3);
  }
}

@keyframes pulse-state {
  0%, 100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.05);
  }
}

.risk-high {
  border-color: #fca5a5;
  background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
}

.risk-high .device-pill__state {
  background: #fecaca;
  color: #991b1b;
  border: 1px solid #f87171;
}

.risk-medium {
  border-color: #fde68a;
  background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
}

.risk-medium .device-pill__state {
  background: #fef08a;
  color: #92400e;
  border: 1px solid #fde047;
}

.risk-low {
  border-color: #86efac;
  background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%);
}

.risk-low .device-pill__state {
  background: #bbf7d0;
  color: #14532d;
  border: 1px solid #4ade80;
}

@media (max-width: 960px) {
  .device-rail {
    padding: 20px;
  }

  .device-rail__head {
    flex-direction: column;
    align-items: flex-start;
  }

  .device-rail__grid {
    grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  }
}

@media (max-width: 640px) {
  .device-rail {
    padding: 16px;
  }

  .device-rail__grid {
    grid-template-columns: 1fr;
  }
}
</style>
