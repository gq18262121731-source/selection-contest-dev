import { computed, onMounted, onUnmounted, ref, unref, watch, type Ref } from "vue";
import {
  api,
  type AlarmRecord,
  type CareDirectory,
  type DeviceRecord,
  type HealthSample,
  type SessionUser,
} from "../api/client";
import { mergeHealthSample } from "../domain/healthSampleMerge";

type MaybeRef<T> = T | Ref<T>;

async function loadDirectoryForCurrentUser(user: SessionUser) {
  return user.role === "family" && user.family_id
    ? api.getFamilyCareDirectory(user.family_id)
    : api.getCareDirectory();
}

function collectVisibleDeviceMacs(directory: CareDirectory) {
  return new Set(
    directory.elders.flatMap((elder) =>
      elder.device_macs?.length ? elder.device_macs : elder.device_mac ? [elder.device_mac] : [],
    ),
  );
}

export function useCareDirectoryDashboard(
  sessionUser: Ref<SessionUser>,
  options: {
    pollIntervalMs?: number;
    includeAllDevices?: MaybeRef<boolean>;
  } = {},
) {
  const directory = ref<CareDirectory | null>(null);
  const devices = ref<DeviceRecord[]>([]);
  const latest = ref<Record<string, HealthSample>>({});
  const alarms = ref<AlarmRecord[]>([]);
  const dashboardLoading = ref(false);
  const dashboardLoadError = ref("");
  const lastSyncAt = ref<Date | null>(null);

  const pollIntervalMs = options.pollIntervalMs ?? 15000;
  const includeAllDevices = computed(() => Boolean(unref(options.includeAllDevices ?? false)));
  const community = computed(() => directory.value?.community ?? null);
  const elders = computed(() => directory.value?.elders ?? []);
  const allFamilies = computed(() => directory.value?.families ?? []);

  let refreshTimer: number | null = null;

  function stopPolling() {
    if (refreshTimer !== null) {
      window.clearInterval(refreshTimer);
      refreshTimer = null;
    }
  }

  async function refreshDashboardData() {
    dashboardLoading.value = true;
    dashboardLoadError.value = "";

    const data = await loadDirectoryForCurrentUser(sessionUser.value).catch(() => null);
    if (!data) {
      directory.value = null;
      devices.value = [];
      latest.value = {};
      alarms.value = [];
      dashboardLoadError.value = "当前页面数据加载失败，请稍后重试。";
      dashboardLoading.value = false;
      return;
    }

    directory.value = data;

    const allDevices = await api.listDevices().catch(() => [] as DeviceRecord[]);
    const visibleDeviceMacs = collectVisibleDeviceMacs(data);
    devices.value =
      includeAllDevices.value && sessionUser.value.role !== "family"
        ? allDevices
        : allDevices.filter((device) => visibleDeviceMacs.has(device.mac_address));

    const snapshots = await Promise.all(devices.value.map((device) => api.getRealtime(device.mac_address).catch(() => null)));
    const nextLatest = { ...latest.value };
    snapshots.forEach((sample) => {
      if (sample) {
        nextLatest[sample.device_mac] = mergeHealthSample(nextLatest[sample.device_mac], sample) ?? sample;
      }
    });
    latest.value = nextLatest;

    alarms.value = await api.listAlarms().catch(() => [] as AlarmRecord[]);
    lastSyncAt.value = new Date();
    dashboardLoading.value = false;
  }

  async function startPolling() {
    stopPolling();
    await refreshDashboardData();
    refreshTimer = window.setInterval(() => {
      void refreshDashboardData();
    }, pollIntervalMs);
  }

  watch([sessionUser, includeAllDevices], () => {
    void startPolling();
  });

  onMounted(() => {
    void startPolling();
  });

  onUnmounted(() => {
    stopPolling();
  });

  return {
    alarms,
    allFamilies,
    community,
    dashboardLoadError,
    dashboardLoading,
    devices,
    directory,
    elders,
    lastSyncAt,
    latest,
    refreshDashboardData,
    stopPolling,
  };
}
