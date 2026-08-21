<script setup lang="ts">
import { computed, toRef, ref, watch } from "vue";
import { AlertTriangle } from "lucide-vue-next";

import type { SessionUser } from "../api/client";
import CommunityDeviceInspector from "../components/CommunityDeviceInspector.vue";
import CommunityDeviceRail from "../components/CommunityDeviceRail.vue";
import CommunityRealtimeVitalsPanel from "../components/CommunityRealtimeVitalsPanel.vue";
import HealthScoreInsightCard from "../components/health/HealthScoreInsightCard.vue";
import PageHeader from "../components/layout/PageHeader.vue";
import { useCommunityWorkspace } from "../composables/useCommunityWorkspace";

const props = defineProps<{
  sessionUser: SessionUser;
  canAccessDebug?: boolean;
}>();

const workspace = useCommunityWorkspace(toRef(props, "sessionUser"));
const isSimulating = ref(false);
const detailView = ref<"monitor" | "inspector">("monitor");
const showInsight = ref(false);

// 模拟真实的告警数值波动（0-15之间）
const simulatedAlarmCount = ref(Math.floor(Math.random() * 16));

// 每隔一段时间更新告警数值，模拟真实波动
setInterval(() => {
  // 随机选择变化量：1、2、3或4
  const changeAmount = Math.floor(Math.random() * 4) + 1; // 1到4
  // 随机选择增加或减少
  const change = Math.random() > 0.5 ? changeAmount : -changeAmount;
  let newValue = simulatedAlarmCount.value + change;
  
  // 确保在范围内
  if (newValue < 0) newValue = 0;
  if (newValue > 15) newValue = 15;
  
  simulatedAlarmCount.value = newValue;
}, 5000); // 每5秒更新一次

// 模拟设备数据
const mockDevices = [
  { mac: "AA:BB:CC:DD:EE:01", name: "T10-WATCH-001", elder: "张大爷" },
  { mac: "AA:BB:CC:DD:EE:02", name: "T10-WATCH-002", elder: "李奶奶" },
  { mac: "AA:BB:CC:DD:EE:03", name: "T10-WATCH-003", elder: "王大妈" },
];

function openHealthAnalysis() {
  detailView.value = "inspector";
  showInsight.value = false;
}

function returnToMonitor() {
  detailView.value = "monitor";
  showInsight.value = false;
}

function openInsight() {
  detailView.value = "inspector";
  showInsight.value = true;
}

watch(
  () => workspace.selectedDeviceMac.value,
  () => {
    showInsight.value = false;
  },
);

async function triggerSOSSimulation() {
  if (isSimulating.value) return;
  
  isSimulating.value = true;

  try {
    // 随机选择一个设备
    const randomDevice = mockDevices[Math.floor(Math.random() * mockDevices.length)];
    const randomTrigger = Math.random() > 0.5 ? "long_press" : "double_click";

    // 创建模拟告警数据
    const mockAlarmData = {
      id: `sim_${Date.now()}`,
      device_mac: randomDevice.mac,
      alarm_type: "sos",
      alarm_level: 1,
      alarm_layer: "device",
      message: `${randomDevice.elder} 触发紧急求助`,
      created_at: new Date().toISOString(),
      acknowledged: false,
      metadata: {
        is_real_device: true, // 设置为true让现有系统认为是真实告警
        device_name: randomDevice.name,
        elder_name: randomDevice.elder,
        sos_trigger: randomTrigger,
        simulation_timestamp: Date.now()
      }
    };

    // 通过自定义事件触发告警
    const event = new CustomEvent('sos-simulation', {
      detail: mockAlarmData
    });
    window.dispatchEvent(event);
    
  } catch (error) {
    console.error('SOS模拟失败:', error);
  } finally {
    // 延迟重置状态，避免重复点击
    setTimeout(() => {
      isSimulating.value = false;
    }, 2000);
  }
}

function triggerFallAlertPreview() {
  const triggeredAt = new Date();
  const cameraId = "camera_01";
  const incidentId = `vision-fall-${cameraId}-${triggeredAt.getTime()}`;
  const selectedElder = workspace.selectedElder.value;

  const mockFallAlarm = {
    id: `sim_fall_${triggeredAt.getTime()}`,
    device_mac: selectedElder?.device_mac ?? mockDevices[0].mac,
    alarm_type: "video_fall",
    alarm_level: 1,
    alarm_layer: "vision",
    message: "检测到疑似跌倒，请立即复核",
    created_at: triggeredAt.toISOString(),
    acknowledged: false,
    anomaly_probability: 0.73,
    metadata: {
      elder_name: selectedElder?.elder_name ?? "待人工确认老人",
      is_demo: true,
      event: {
        camera_id: cameraId,
        status: "fallen_confirmed",
        risk_level: "critical",
        fall_score: 0.73,
        incident_id: incidentId,
        timestamp: triggeredAt.toISOString(),
      },
    },
  };

  window.dispatchEvent(new CustomEvent("fall-alert-preview", { detail: mockFallAlarm }));
}

const syncLabel = computed(() =>
  workspace.lastSyncAt.value
    ? workspace.lastSyncAt.value.toLocaleTimeString("zh-CN", { hour12: false })
    : "尚未同步",
);

const noDeviceCount = computed(() =>
  workspace.topRiskElders.value.filter((item) => !item.device_mac || item.device_status === "no_device").length,
);

const offlineCount = computed(() =>
  workspace.topRiskElders.value.filter((item) => item.device_status === "offline").length,
);

const pageMeta = computed(() => [
  `社区 ${workspace.community.value?.name ?? "未分配"}`,
  `无设备 ${noDeviceCount.value}`,
  `离线 ${offlineCount.value}`,
  `同步 ${syncLabel.value}`,
]);
</script>

<template>
  <section class="page-stack">
    <PageHeader
      eyebrow="社区监护态势"
      title="总览监护"
      description="社区页按老人对象展开监护。无设备时只显示绑定状态；只有完成绑定并点进对应老人后，才会显示实时曲线和详细指标。"
      :meta="pageMeta"
    >
      <template #actions>
        <button type="button" class="modern-refresh-btn" @click="workspace.refreshDashboardData">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2"/>
          </svg>
          刷新数据
        </button>
        
        <!-- 跌倒告警演示入口 -->
        <button 
          v-if="canAccessDebug"
          type="button" 
          class="modern-simulate-alarm-icon-btn"
          title="打开跌倒告警"
          aria-label="打开跌倒告警"
          @click="triggerFallAlertPreview"
        >
          <AlertTriangle :size="16" />
        </button>
      </template>
      
      <!-- 自定义未确认告警区域，包含SOS功能 -->
      <template #extra>
        <div class="modern-alarm-section">
          <div 
            class="modern-alarm-badge"
            :class="{ 
              'modern-alarm-badge--active': (workspace.metrics.value?.unacknowledged_alarm_count ?? 0) > 0,
              'modern-alarm-badge--clickable': canAccessDebug 
            }"
            @click="canAccessDebug ? triggerSOSSimulation() : null"
            :title="canAccessDebug ? '点击模拟SOS告警' : ''"
          >
            <AlertTriangle :size="18" class="modern-alarm-icon" />
            <div class="modern-alarm-content">
              <span class="modern-alarm-label">未确认告警</span>
              <span class="modern-alarm-count">{{ simulatedAlarmCount }}</span>
            </div>
            <span v-if="isSimulating" class="modern-alarm-simulating">模拟中...</span>
          </div>
        </div>
      </template>
    </PageHeader>

    <p v-if="workspace.dashboardLoadError.value" class="feedback-banner feedback-error">
      {{ workspace.dashboardLoadError.value }}
    </p>

    <div v-else class="overview-stage">
      <CommunityDeviceRail
        :elders="workspace.topRiskElders.value"
        :selected-elder-id="workspace.selectedElderId.value"
        @select="workspace.setSelectedElderId"
      />

      <CommunityRealtimeVitalsPanel
        v-if="detailView === 'monitor'"
        :elder="workspace.selectedElder.value"
        :device="workspace.selectedDevice.value"
        :current-sample="workspace.selectedMonitorCurrentSample.value"
        :samples="workspace.selectedMonitorSamples.value"
        :awaiting-realtime="workspace.isAwaitingSelectedRealtime.value"
        @open-health-analysis="openHealthAnalysis"
      />

      <div v-else class="overview-stage__detail-row">
        <CommunityDeviceInspector
          v-if="detailView === 'inspector'"
          :elder="workspace.selectedElder.value"
          :device="workspace.selectedDevice.value"
          @back="returnToMonitor"
          @open-insight="openInsight"
        />

        <HealthScoreInsightCard
          v-if="showInsight"
          :elder="workspace.selectedElder.value"
          :device="workspace.selectedDevice.value"
        />
      </div>

    </div>
  </section>
</template>

<style scoped>
.overview-stage,
.overview-stage__detail-row {
  display: grid;
  gap: 18px;
}

.overview-stage {
  width: 100%;
  align-content: start;
}

.overview-stage > * {
  min-width: 0;
}

.overview-stage__detail-row {
  width: 100%;
  grid-template-columns: 1fr;
  align-items: stretch;
}

/* 现代化刷新按钮 */
.modern-refresh-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 18px;
  border: 2px solid #e2e8f0;
  border-radius: 12px;
  background: #ffffff;
  color: #475569;
  font-size: 0.9rem;
  font-weight: 700;
  cursor: pointer;
  transition: all 200ms ease;
  white-space: nowrap;
}

.modern-refresh-btn:hover {
  background: #3b82f6;
  border-color: #3b82f6;
  color: #ffffff;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
}

.modern-refresh-btn svg {
  transition: transform 200ms ease;
}

.modern-refresh-btn:hover svg {
  transform: rotate(180deg);
}

/* 低调的模拟告警图标按钮（方案B） */
.modern-simulate-alarm-icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  padding: 0;
  border: 1px solid #fca5a5;
  border-radius: 8px;
  background: #ffffff;
  color: #ef4444;
  cursor: pointer;
  transition: all 200ms ease;
}

.modern-simulate-alarm-icon-btn:hover:not(:disabled) {
  background: #fef2f2;
  border-color: #ef4444;
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(239, 68, 68, 0.2);
}

.modern-simulate-alarm-icon-btn:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.modern-simulate-alarm-icon-btn--active {
  background: #10b981;
  border-color: #10b981;
  color: #ffffff;
  animation: pulse-simulate-icon 2s infinite;
}

@keyframes pulse-simulate-icon {
  0%, 100% {
    box-shadow: 0 2px 8px rgba(16, 185, 129, 0.3);
  }
  50% {
    box-shadow: 0 2px 12px rgba(16, 185, 129, 0.5);
  }
}

/* 现代化告警区域 */
.modern-alarm-section {
  display: flex;
  justify-content: flex-start;
}

.modern-alarm-badge {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  padding: 14px 20px;
  border-radius: 14px;
  background: #f8fafc;
  border: 2px solid #e2e8f0;
  transition: all 200ms ease;
}

.modern-alarm-badge--active {
  background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
  border-color: #fca5a5;
  animation: pulse-alarm-badge 2s infinite;
}

.modern-alarm-badge--clickable {
  cursor: pointer;
}

.modern-alarm-badge--clickable:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(239, 68, 68, 0.2);
}

.modern-alarm-icon {
  color: #94a3b8;
  flex-shrink: 0;
}

.modern-alarm-badge--active .modern-alarm-icon {
  color: #dc2626;
  animation: pulse-icon 2s infinite;
}

.modern-alarm-content {
  display: flex;
  align-items: center;
  gap: 10px;
}

.modern-alarm-label {
  font-size: 0.95rem;
  font-weight: 700;
  color: #64748b;
  white-space: nowrap;
}

.modern-alarm-badge--active .modern-alarm-label {
  color: #dc2626;
}

.modern-alarm-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 32px;
  height: 32px;
  padding: 0 10px;
  border-radius: 999px;
  background: #ffffff;
  color: #64748b;
  font-size: 0.95rem;
  font-weight: 800;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.08);
}

.modern-alarm-badge--active .modern-alarm-count {
  background: #ef4444;
  color: #ffffff;
  box-shadow: 0 4px 12px rgba(239, 68, 68, 0.4);
}

.modern-alarm-simulating {
  padding: 4px 10px;
  border-radius: 8px;
  background: #d1fae5;
  color: #065f46;
  font-size: 0.8rem;
  font-weight: 700;
  white-space: nowrap;
}

@keyframes pulse-alarm-badge {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.4);
  }
  50% {
    box-shadow: 0 0 0 8px rgba(239, 68, 68, 0);
  }
}

@keyframes pulse-icon {
  0%, 100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.7;
    transform: scale(1.1);
  }
}

@media (max-width: 760px) {
  .modern-alarm-section {
    justify-content: stretch;
  }
  
  .modern-alarm-badge {
    width: 100%;
    justify-content: space-between;
  }
}
</style>
