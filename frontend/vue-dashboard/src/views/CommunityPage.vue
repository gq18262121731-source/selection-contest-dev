<script setup lang="ts">
import { computed, toRef, ref } from "vue";
import { AlertTriangle } from "lucide-vue-next";

import type { SessionUser } from "../api/client";
import CommunityDeviceInspector from "../components/CommunityDeviceInspector.vue";
import CommunityDeviceRail from "../components/CommunityDeviceRail.vue";
import CommunityRealtimeVitalsPanel from "../components/CommunityRealtimeVitalsPanel.vue";
import PageHeader from "../components/layout/PageHeader.vue";
import { useCommunityWorkspace } from "../composables/useCommunityWorkspace";

const props = defineProps<{
  sessionUser: SessionUser;
  canAccessDebug?: boolean;
}>();

const workspace = useCommunityWorkspace(toRef(props, "sessionUser"));
const isSimulating = ref(false);

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
        
        <!-- 方案B：低调的模拟告警按钮 -->
        <button 
          v-if="canAccessDebug"
          type="button" 
          class="modern-simulate-alarm-icon-btn"
          :class="{ 'modern-simulate-alarm-icon-btn--active': isSimulating }"
          :disabled="isSimulating"
          :title="isSimulating ? '模拟中...' : '模拟告警（测试）'"
          @click="triggerSOSSimulation"
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
              'modern-alarm-badge--active': workspace.metrics.value?.unacknowledged_alarm_count > 0,
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
        :elder="workspace.selectedElder.value"
        :device="workspace.selectedDevice.value"
        :current-sample="workspace.selectedMonitorCurrentSample.value"
        :samples="workspace.selectedMonitorSamples.value"
        :awaiting-realtime="workspace.isAwaitingSelectedRealtime.value"
      />

      <div class="overview-stage__detail-row">
        <CommunityDeviceInspector
          :elder="workspace.selectedElder.value"
          :device="workspace.selectedDevice.value"
        />

        <article class="panel alerts-panel">
          <div class="alerts-panel__head">
            <div>
              <p class="section-eyebrow">最近告警明细</p>
              <h2>最近告警</h2>
            </div>
            <span class="summary-badge">{{ workspace.recentAlerts.value.length }} 条</span>
          </div>

          <div class="alert-list">
            <article
              v-for="item in workspace.recentAlerts.value.slice(0, 6)"
              :key="item.alarm_id"
              class="alert-row"
            >
              <strong>{{ item.elder_name ?? item.device_mac }}</strong>
              <small>{{ item.message }}</small>
              <em>{{ new Date(item.created_at).toLocaleString("zh-CN", { hour12: false }) }}</em>
            </article>
            <div v-if="!workspace.recentAlerts.value.length" class="empty-copy">
              当前没有最近告警。
            </div>
          </div>
        </article>
      </div>
    </div>
  </section>
</template>

<style scoped>
.overview-stage,
.overview-stage__detail-row,
.alert-list {
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
  grid-template-columns: minmax(0, 1.05fr) minmax(320px, 0.95fr);
  align-items: start;
}

.alerts-panel {
  display: grid;
  gap: 16px;
}

.alerts-panel__head {
  display: flex;
  gap: 14px;
  justify-content: space-between;
  align-items: flex-start;
}

.alerts-panel__head h2 {
  margin: 0;
  color: var(--text-main);
  font-family: var(--font-display);
}

.alert-row {
  padding: 14px 16px;
  border-radius: 20px;
  background: #ffffff;
  border: 1px solid var(--line-medium);
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.04);
  display: grid;
  gap: 6px;
}

.alert-row strong {
  color: var(--text-main);
}

.alert-row small,
.alert-row em,
.empty-copy {
  color: var(--text-sub);
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

@media (max-width: 1180px) {
  .overview-stage__detail-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .alerts-panel__head {
    flex-direction: column;
  }
  
  .modern-alarm-section {
    justify-content: stretch;
  }
  
  .modern-alarm-badge {
    width: 100%;
    justify-content: space-between;
  }
}
</style>
