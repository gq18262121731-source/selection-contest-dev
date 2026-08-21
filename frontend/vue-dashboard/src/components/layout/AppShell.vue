<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { api, type AlarmRecord, type SessionUser } from "../../api/client";
import { focusCommunityWorkspaceDevice } from "../../composables/useCommunityWorkspace";
import type { PageKey } from "../../composables/useHashRouting";
import {
  emergencyAlarmStorageKey,
  extractRobotAlarmExtension,
} from "../../utils/robotEmergencyPolicy";
import CommunitySosOverlay from "./CommunitySosOverlay.vue";
import FallAlertOverlay from "./FallAlertOverlay.vue";
import GlobalHeader from "./GlobalHeader.vue";
import PrimaryNav from "./PrimaryNav.vue";
import RobotWorkspaceNav from "../robot/RobotWorkspaceNav.vue";
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
  openEmergency: [incidentId: string];
}>();

const activeAlarmCount = ref(0);
const activeRealtimeAlarms = ref<AlarmRecord[]>([]);
const simulatedAlarms = ref<AlarmRecord[]>([]);
const acknowledgingSos = ref(false);
const acknowledgingFall = ref(false);
const dismissedFallAlarmIds = ref(new Set<string>());
const manuallyAcknowledging = ref(false);
const isCommunityWorkspace = computed(
  () => props.sessionUser.role === "community" || props.sessionUser.role === "admin",
);
const robotWorkspacePages = new Set<PageKey>([
  "robot-tasks",
  "robot-status",
  "robot-navigation",
  "robot-follow",
  "robot-emergency",
]);
const showRobotWorkspaceNav = computed(() => robotWorkspacePages.has(props.activePage));
const activeSosAlarms = computed(() =>
  activeRealtimeAlarms.value
    .filter((alarm) => !alarm.acknowledged && isRealSosAlarm(alarm))
    .sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime()),
);
const primarySosAlarm = computed(() => activeSosAlarms.value[0] ?? null);
const additionalSosCount = computed(() => Math.max(0, activeSosAlarms.value.length - 1));
const activeFallAlarms = computed(() =>
  activeRealtimeAlarms.value
    .filter((alarm) =>
      !alarm.acknowledged
      && !dismissedFallAlarmIds.value.has(alarm.id)
      && isFallAlarm(alarm),
    )
    .sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime()),
);
const primaryFallAlarm = computed(() => activeFallAlarms.value[0] ?? null);
const additionalFallCount = computed(() => Math.max(0, activeFallAlarms.value.length - 1));

let refreshTimer: number | null = null;
let alarmReconnectTimer: number | null = null;
let alarmChannel: WebSocket | null = null;
let alarmRuntimeActive = false;
let lastPresentedAlarmId = "";
let sosAudioElement: HTMLAudioElement | null = null;
let unlockAudioListenerBound = false;
let unlockAudioHandler: (() => void) | null = null;

function isRealSosAlarm(alarm: AlarmRecord) {
  return alarm.alarm_type === "sos" && !alarm.acknowledged && Boolean(alarm.metadata?.is_real_device);
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function isFallAlarm(alarm: AlarmRecord) {
  if (!["fall_detected", "fall_injury_risk", "video_fall"].includes(alarm.alarm_type)) {
    return false;
  }
  const metadata = asRecord(alarm.metadata);
  return Boolean(asRecord(metadata?.event) || asRecord(metadata?.raw_event) || metadata);
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
  if (!audio.paused) return;
  audio.currentTime = 0;
  try {
    await audio.play();
  } catch {
    // autoplay may be blocked before first interaction
  }
}

function stopSosToneLoop() {
  if (!sosAudioElement) return;
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
  const realAlarms = alarms.filter((alarm) => !alarm.id.startsWith("sim_"));
  const allAlarms = [...realAlarms, ...simulatedAlarms.value];
  activeRealtimeAlarms.value = allAlarms
    .filter((alarm) => !alarm.acknowledged)
    .sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime());
  activeAlarmCount.value = activeRealtimeAlarms.value.length;
  presentPrimaryAlarm();
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

function presentPrimaryAlarm() {
  const current = primarySosAlarm.value ?? primaryFallAlarm.value;
  if (!isCommunityWorkspace.value || !current) {
    return;
  }
  if (lastPresentedAlarmId !== current.id) {
    lastPresentedAlarmId = current.id;
    focusCommunityWorkspaceDevice(current.device_mac);
    if (props.activePage !== "overview") {
      emit("navigate", "overview");
    }
  }
}

function stopAlarmRuntime() {
  alarmRuntimeActive = false;
  stopSosToneLoop();
  if (refreshTimer !== null) {
    window.clearInterval(refreshTimer);
    refreshTimer = null;
  }
  if (alarmReconnectTimer !== null) {
    window.clearTimeout(alarmReconnectTimer);
    alarmReconnectTimer = null;
  }
  if (alarmChannel) alarmChannel.onclose = null;
  alarmChannel?.close();
  alarmChannel = null;
}

async function refreshAlarmState() {
  const alarms = await api.listAlarms().catch(() => [] as AlarmRecord[]);
  syncAlarmState(alarms);
}

function connectAlarmSocket() {
  if (!alarmRuntimeActive) return;
  if (alarmReconnectTimer !== null) {
    window.clearTimeout(alarmReconnectTimer);
    alarmReconnectTimer = null;
  }
  if (alarmChannel) alarmChannel.onclose = null;
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
    if (!alarmRuntimeActive || !isCommunityWorkspace.value) return;
    alarmReconnectTimer = window.setTimeout(() => {
      alarmReconnectTimer = null;
      if (alarmRuntimeActive && isCommunityWorkspace.value) connectAlarmSocket();
    }, 2000);
  };
}

function startAlarmRuntime() {
  stopAlarmRuntime();
  alarmRuntimeActive = true;
  void refreshAlarmState();
  connectAlarmSocket();
  refreshTimer = window.setInterval(() => {
    void refreshAlarmState();
  }, 5000);
}

function handleAlarmSimulation(event: CustomEvent) {
  if (!isCommunityWorkspace.value) return;
  const mockAlarm = event.detail as AlarmRecord;
  simulatedAlarms.value = [
    mockAlarm,
    ...simulatedAlarms.value.filter((alarm) => alarm.id !== mockAlarm.id),
  ];
  const realAlarms = activeRealtimeAlarms.value.filter((alarm) => !alarm.id.startsWith("sim_"));
  const allAlarms = [...realAlarms, ...simulatedAlarms.value];
  activeRealtimeAlarms.value = allAlarms
    .filter((alarm) => !alarm.acknowledged)
    .sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime());
  activeAlarmCount.value = activeRealtimeAlarms.value.length;
  presentPrimaryAlarm();
}

watch(() => props.sessionUser.id, () => {
  startAlarmRuntime();
});

onMounted(() => {
  bindAudioUnlockListeners();
  startAlarmRuntime();
  window.addEventListener("sos-simulation", handleAlarmSimulation as EventListener);
  window.addEventListener("fall-alert-preview", handleAlarmSimulation as EventListener);
});

onUnmounted(() => {
  stopAlarmRuntime();
  window.removeEventListener("sos-simulation", handleAlarmSimulation as EventListener);
  window.removeEventListener("fall-alert-preview", handleAlarmSimulation as EventListener);
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
  manuallyAcknowledging.value = true;
  acknowledgingSos.value = true;
  stopSosToneLoop();
  try {
    if (current.id.startsWith("sim_")) {
      simulatedAlarms.value = simulatedAlarms.value.filter((alarm) => alarm.id !== current.id);
      const realAlarms = activeRealtimeAlarms.value.filter((alarm) => !alarm.id.startsWith("sim_"));
      const allAlarms = [...realAlarms, ...simulatedAlarms.value];
      activeRealtimeAlarms.value = allAlarms
        .filter((alarm) => !alarm.acknowledged)
        .sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime());
      activeAlarmCount.value = activeRealtimeAlarms.value.length;
    } else {
      await api.ackAlarm(current.id);
      await refreshAlarmState();
    }
    lastPresentedAlarmId = "";
  } finally {
    acknowledgingSos.value = false;
    setTimeout(() => {
      manuallyAcknowledging.value = false;
    }, 100);
  }
}

async function acknowledgePrimaryFall() {
  const current = primaryFallAlarm.value;
  if (!current) return;
  acknowledgingFall.value = true;
  try {
    if (current.id.startsWith("sim_")) {
      simulatedAlarms.value = simulatedAlarms.value.filter((alarm) => alarm.id !== current.id);
      const realAlarms = activeRealtimeAlarms.value.filter((alarm) => !alarm.id.startsWith("sim_"));
      syncAlarmState(realAlarms);
    } else {
      await api.ackAlarm(current.id);
      await refreshAlarmState();
    }
    lastPresentedAlarmId = "";
  } finally {
    acknowledgingFall.value = false;
  }
}

function openPrimaryFallEmergency(incidentId: string) {
  const current = primaryFallAlarm.value;
  if (!current) return;
  const extension = extractRobotAlarmExtension(current);
  if (!extension || extension.incident_id !== incidentId) return;
  try {
    window.sessionStorage.setItem(
      emergencyAlarmStorageKey(incidentId),
      JSON.stringify(extension),
    );
  } catch {
    // The route remains usable even when browser storage is unavailable.
  }
  dismissedFallAlarmIds.value = new Set([...dismissedFallAlarmIds.value, current.id]);
  lastPresentedAlarmId = "";
  emit("openEmergency", incidentId);
}

watch(
  [primarySosAlarm, isCommunityWorkspace],
  ([alarm, canRing], [oldAlarm]) => {
    if (manuallyAcknowledging.value) {
      return;
    }
    if (!canRing || !alarm) {
      stopSosToneLoop();
      return;
    }
    if (!oldAlarm || alarm.id !== oldAlarm.id) {
      void startSosToneLoop();
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

      <RobotWorkspaceNav
        v-if="showRobotWorkspaceNav"
        :active-page="activePage"
        :allowed-pages="allowedPages"
        @navigate="emit('navigate', $event)"
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
    <FallAlertOverlay
      v-if="isCommunityWorkspace && !primarySosAlarm"
      :alarm="primaryFallAlarm"
      :additional-count="additionalFallCount"
      :acknowledging="acknowledgingFall"
      @acknowledge="acknowledgePrimaryFall"
      @open-emergency="openPrimaryFallEmergency"
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
