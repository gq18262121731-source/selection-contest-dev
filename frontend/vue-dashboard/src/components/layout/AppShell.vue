<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { api, type AlarmRecord, type SessionUser } from "../../api/client";
import { focusCommunityWorkspaceDevice } from "../../composables/useCommunityWorkspace";
import type { PageKey } from "../../composables/useHashRouting";
import CommunitySosOverlay from "./CommunitySosOverlay.vue";
import GlobalHeader from "./GlobalHeader.vue";
import PrimaryNav from "./PrimaryNav.vue";
import ToolEntryMenu from "./ToolEntryMenu.vue";

const props = defineProps<{
  sessionUser: SessionUser;
  activePage: PageKey;
  allowedPages: PageKey[];
  canAccessDebug: boolean;
}>();

const emit = defineEmits<{
  logout: [];
  navigate: [page: PageKey];
}>();

const activeAlarmCount = ref(0);
const activeRealtimeAlarms = ref<AlarmRecord[]>([]);
const simulatedAlarms = ref<AlarmRecord[]>([]); // 存储模拟告警
const acknowledgingSos = ref(false);
const manuallyAcknowledging = ref(false); // 标记是否正在手动确认告警
const isCommunityWorkspace = computed(
  () => props.sessionUser.role === "community" || props.sessionUser.role === "admin",
);
const activeSosAlarms = computed(() =>
  activeRealtimeAlarms.value
    .filter((alarm) => !alarm.acknowledged && isRealSosAlarm(alarm))
    .sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime()),
);
const primarySosAlarm = computed(() => activeSosAlarms.value[0] ?? null);
const additionalSosCount = computed(() => Math.max(0, activeSosAlarms.value.length - 1));

let refreshTimer: number | null = null;
let alarmChannel: WebSocket | null = null;
let lastPresentedSosAlarmId = "";
let sosAudioElement: HTMLAudioElement | null = null;
let unlockAudioListenerBound = false;
let unlockAudioHandler: (() => void) | null = null;

function isRealSosAlarm(alarm: AlarmRecord) {
  return alarm.alarm_type === "sos" && !alarm.acknowledged && Boolean(alarm.metadata?.is_real_device);
}

function ensureSosAudioElement() {
  if (typeof window === "undefined") return null;
  if (!sosAudioElement) {
    const element = new Audio("/sounds/sos_alarm.ogg");
    element.loop = true;
    element.preload = "auto";
    element.volume = 1;
    sosAudioElement = element;
  }
  return sosAudioElement;
}

async function startSosToneLoop() {
  const audio = ensureSosAudioElement();
  if (!audio) return;
  
  // 如果已经在播放，不要重复启动
  if (!audio.paused) {
    console.log('[SOS Audio] Already playing, skip');
    return;
  }
  
  console.log('[SOS Audio] Starting audio loop');
  audio.currentTime = 0;
  try {
    await audio.play();
  } catch (error) {
    console.log('[SOS Audio] Play failed:', error);
    // autoplay may be blocked before first interaction
  }
}

function stopSosToneLoop() {
  if (!sosAudioElement) return;
  console.log('[SOS Audio] Stopping audio loop');
  sosAudioElement.pause();
  sosAudioElement.currentTime = 0;
}

function unlockSosAudio() {
  const audio = ensureSosAudioElement();
  if (!audio) return;
  void audio.play()
    .then(() => {
      audio.pause();
      audio.currentTime = 0;
    })
    .catch(() => undefined);
}

function bindAudioUnlockListeners() {
  if (typeof window === "undefined" || unlockAudioListenerBound) return;
  unlockAudioListenerBound = true;
  unlockAudioHandler = () => {
    unlockSosAudio();
    if (unlockAudioHandler) {
      window.removeEventListener("pointerdown", unlockAudioHandler);
      window.removeEventListener("keydown", unlockAudioHandler);
      window.removeEventListener("touchstart", unlockAudioHandler);
    }
    unlockAudioListenerBound = false;
    unlockAudioHandler = null;
  };
  window.addEventListener("pointerdown", unlockAudioHandler, { once: true, passive: true });
  window.addEventListener("keydown", unlockAudioHandler, { once: true });
  window.addEventListener("touchstart", unlockAudioHandler, { once: true, passive: true });
}

function syncAlarmState(alarms: AlarmRecord[]) {
  // 过滤掉真实告警列表中的模拟告警（避免重复）
  const realAlarms = alarms.filter(alarm => !alarm.id.startsWith('sim_'));
  // 合并真实告警和模拟告警
  const allAlarms = [...realAlarms, ...simulatedAlarms.value];
  activeRealtimeAlarms.value = allAlarms
    .filter((alarm) => !alarm.acknowledged)
    .sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime());
  activeAlarmCount.value = activeRealtimeAlarms.value.length;
  // 处理页面导航（不处理音频，由watch统一管理）
  presentPrimarySos();
}

function upsertAlarm(alarm: AlarmRecord) {
  const next = [...activeRealtimeAlarms.value];
  const index = next.findIndex((item) => item.id === alarm.id);
  if (alarm.acknowledged) {
    if (index >= 0) next.splice(index, 1);
  } else if (index >= 0) {
    next.splice(index, 1, alarm);
  } else {
    next.push(alarm);
  }
  syncAlarmState(next);
}

function presentPrimarySos() {
  if (!isCommunityWorkspace.value || !primarySosAlarm.value) {
    return;
  }
  
  // 只处理页面导航和设备聚焦，不处理音频（由watch统一管理）
  if (lastPresentedSosAlarmId !== primarySosAlarm.value.id) {
    lastPresentedSosAlarmId = primarySosAlarm.value.id;
    focusCommunityWorkspaceDevice(primarySosAlarm.value.device_mac);
    if (props.activePage !== "overview") {
      emit("navigate", "overview");
    }
  }
}

function stopAlarmRuntime() {
  stopSosToneLoop();
  if (refreshTimer !== null) {
    window.clearInterval(refreshTimer);
    refreshTimer = null;
  }
  alarmChannel?.close();
  alarmChannel = null;
}

async function refreshAlarmState() {
  const alarms = await api.listAlarms().catch(() => [] as AlarmRecord[]);
  syncAlarmState(alarms);
}

function connectAlarmSocket() {
  alarmChannel?.close();
  alarmChannel = null;
  if (!isCommunityWorkspace.value) return;

  alarmChannel = api.alarmSocket();
  alarmChannel.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data) as AlarmRecord | { type?: string; queue?: Array<{ alarm?: AlarmRecord }> };
      if ("type" in payload && payload.type === "alarm_queue") {
        const alarms = Array.isArray(payload.queue)
          ? payload.queue
              .map((item) => item.alarm)
              .filter((item): item is AlarmRecord => Boolean(item))
          : [];
        syncAlarmState(alarms);
        return;
      } 
      upsertAlarm(payload as AlarmRecord);
    } catch {
      // ignore malformed websocket payloads
    }
  };
  alarmChannel.onclose = () => {
    alarmChannel = null;
    // Auto-reconnect after 2 seconds for real-time SOS delivery
    setTimeout(() => {
      if (isCommunityWorkspace.value) connectAlarmSocket();
    }, 2000);
  };
}

function startAlarmRuntime() {
  stopAlarmRuntime();
  void refreshAlarmState();
  connectAlarmSocket();
  refreshTimer = window.setInterval(() => {
    void refreshAlarmState();
  }, 5000);
}

// 监听SOS模拟事件
function handleSOSSimulation(event: CustomEvent) {
  if (!isCommunityWorkspace.value) return;
  
  const mockAlarm = event.detail as AlarmRecord;
  // 将模拟告警添加到模拟告警列表中，这样不会被刷新覆盖
  simulatedAlarms.value.push(mockAlarm);
  
  // 手动更新activeRealtimeAlarms，避免调用syncAlarmState导致重复
  const realAlarms = activeRealtimeAlarms.value.filter(alarm => !alarm.id.startsWith('sim_'));
  const allAlarms = [...realAlarms, ...simulatedAlarms.value];
  activeRealtimeAlarms.value = allAlarms
    .filter((alarm) => !alarm.acknowledged)
    .sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime());
  activeAlarmCount.value = activeRealtimeAlarms.value.length;
  
  // 处理页面导航（不处理音频，由watch统一管理）
  presentPrimarySos();
}

watch(() => props.sessionUser.id, () => {
  startAlarmRuntime();
});

onMounted(() => {
  bindAudioUnlockListeners();
  startAlarmRuntime();
  
  // 添加SOS模拟事件监听器
  window.addEventListener('sos-simulation', handleSOSSimulation as EventListener);
});

onUnmounted(() => {
  stopAlarmRuntime();
  if (unlockAudioListenerBound && unlockAudioHandler) {
    window.removeEventListener("pointerdown", unlockAudioHandler);
    window.removeEventListener("keydown", unlockAudioHandler);
    window.removeEventListener("touchstart", unlockAudioHandler);
  }
  unlockAudioListenerBound = false;
  unlockAudioHandler = null;
  if (sosAudioElement) {
    sosAudioElement.pause();
    sosAudioElement.src = "";
  }
  sosAudioElement = null;
});

async function acknowledgePrimarySos() {
  const current = primarySosAlarm.value;
  if (!current) return;
  
  console.log('[SOS Acknowledge] Starting acknowledgment for:', current.id);
  
  // 标记正在手动确认，防止watch触发音频
  manuallyAcknowledging.value = true;
  acknowledgingSos.value = true;
  
  // 先停止音频
  stopSosToneLoop();
  
  try {
    // 如果是模拟告警，直接从模拟列表中移除
    if (current.id.startsWith('sim_')) {
      console.log('[SOS Acknowledge] Removing simulated alarm');
      simulatedAlarms.value = simulatedAlarms.value.filter(alarm => alarm.id !== current.id);
      // 手动更新状态
      const realAlarms = activeRealtimeAlarms.value.filter(alarm => !alarm.id.startsWith('sim_'));
      const allAlarms = [...realAlarms, ...simulatedAlarms.value];
      activeRealtimeAlarms.value = allAlarms
        .filter((alarm) => !alarm.acknowledged)
        .sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime());
      activeAlarmCount.value = activeRealtimeAlarms.value.length;
      console.log('[SOS Acknowledge] Remaining alarms:', activeRealtimeAlarms.value.length);
    } else {
      // 真实告警通过API确认
      console.log('[SOS Acknowledge] Acknowledging real alarm via API');
      await api.ackAlarm(current.id);
      await refreshAlarmState();
    }
    lastPresentedSosAlarmId = "";
  } finally {
    acknowledgingSos.value = false;
    // 延迟重置标记，确保watch不会立即触发
    setTimeout(() => {
      console.log('[SOS Acknowledge] Resetting manual acknowledgment flag');
      manuallyAcknowledging.value = false;
    }, 100);
  }
}

watch(
  [primarySosAlarm, isCommunityWorkspace],
  ([alarm, canRing], [oldAlarm]) => {
    console.log('[SOS Watch] Triggered', {
      alarm: alarm?.id,
      oldAlarm: oldAlarm?.id,
      canRing,
      manuallyAcknowledging: manuallyAcknowledging.value
    });
    
    // 如果正在手动确认告警，不要播放音频
    if (manuallyAcknowledging.value) {
      console.log('[SOS Watch] Skipping due to manual acknowledgment');
      return;
    }
    
    if (!canRing || !alarm) {
      console.log('[SOS Watch] Stopping audio - no alarm or not community');
      stopSosToneLoop();
      return;
    }
    
    // 只在新告警出现时播放音频（告警ID改变）
    if (alarm && (!oldAlarm || alarm.id !== oldAlarm.id)) {
      console.log('[SOS Watch] New alarm detected, starting audio');
      void startSosToneLoop();
    } else {
      console.log('[SOS Watch] Same alarm, no action');
    }
  },
  { immediate: true },
);
</script>

<template>
  <main class="app-shell" :class="{ 'app-shell--workspace': isCommunityWorkspace }">
    <aside v-if="isCommunityWorkspace" class="workspace-sidebar">
      <PrimaryNav
        v-if="allowedPages.length"
        :active-page="activePage"
        :allowed-pages="allowedPages"
        @navigate="emit('navigate', $event)"
      />

      <div class="workspace-sidebar__footer">
        <ToolEntryMenu
          v-if="canAccessDebug"
          :active-page="activePage"
          :can-access-debug="canAccessDebug"
          @navigate="emit('navigate', $event)"
        />
      </div>
    </aside>

    <div class="workspace-stage">
      <GlobalHeader
        :session-user="sessionUser"
        :active-alarm-count="activeAlarmCount"
        @logout="emit('logout')"
      />

      <div
        v-if="!isCommunityWorkspace && allowedPages.length"
        class="app-shell__controls"
      >
        <PrimaryNav
          :active-page="activePage"
          :allowed-pages="allowedPages"
          @navigate="emit('navigate', $event)"
        />
        <ToolEntryMenu
          v-if="canAccessDebug"
          :active-page="activePage"
          :can-access-debug="canAccessDebug"
          @navigate="emit('navigate', $event)"
        />
      </div>

      <div class="app-shell__content">
        <slot />
      </div>
    </div>

    <CommunitySosOverlay
      v-if="isCommunityWorkspace"
      :alarm="primarySosAlarm"
      :additional-count="additionalSosCount"
      :acknowledging="acknowledgingSos"
      @acknowledge="acknowledgePrimarySos"
    />
  </main>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
  width: 100%;
  background: var(--bg-base);
}

.app-shell--workspace {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

.workspace-sidebar {
  position: fixed;
  left: 0;
  top: 0;
  bottom: 0;
  width: 260px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px 12px;
  background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
  border-right: 1px solid #e2e8f0;
  overflow: hidden;
  z-index: 100;
}

.workspace-sidebar__footer {
  margin-top: auto;
  padding-top: 16px;
  border-top: 1px solid #e2e8f0;
}

.workspace-stage {
  flex: 1;
  margin-left: 260px;
  width: calc(100% - 260px);
  height: 100vh;
  overflow-y: auto;
  overflow-x: hidden;
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 14px 20px 32px;
}

.workspace-stage::-webkit-scrollbar {
  width: 8px;
}

.workspace-stage::-webkit-scrollbar-track {
  background: transparent;
}

.workspace-stage::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.3);
  border-radius: 4px;
}

.workspace-stage::-webkit-scrollbar-thumb:hover {
  background: rgba(148, 163, 184, 0.5);
}

.app-shell__controls {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: flex-start;
}

.app-shell__content {
  flex: 1;
  width: 100%;
  min-height: 0;
}

@media (max-width: 960px) {
  .app-shell--workspace {
    flex-direction: column;
    height: auto;
    overflow: visible;
  }

  .workspace-sidebar {
    position: static;
    width: 100%;
    height: auto;
    border-right: none;
    border-bottom: 1px solid #e2e8f0;
  }

  .workspace-stage {
    margin-left: 0;
    width: 100%;
    height: auto;
    overflow: visible;
  }
}
</style>
