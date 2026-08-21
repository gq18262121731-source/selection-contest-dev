import { computed, onMounted, onUnmounted, ref } from "vue";
import { api, type DeviceRecord, type HealthSample } from "../api/client";
import { mergeHealthSample } from "../domain/healthSampleMerge";

export function useDebugDashboard(pollIntervalMs = 5000) {
  const devices = ref<DeviceRecord[]>([]);
  const latest = ref<Record<string, HealthSample>>({});
  const dashboardLoading = ref(false);
  const dashboardLoadError = ref("");
  const lastSyncAt = ref<Date | null>(null);

  const debugRows = computed(() =>
    devices.value.map((device) => ({
      mac: device.mac_address,
      deviceName: device.device_name,
      status: device.status,
      sample: latest.value[device.mac_address] ?? null,
    })),
  );

  let refreshTimer: number | null = null;

  function stopPolling() {
    if (refreshTimer !== null) {
      window.clearInterval(refreshTimer);
      refreshTimer = null;
    }
  }

  async function refreshDebugData() {
    dashboardLoading.value = true;
    dashboardLoadError.value = "";

    devices.value = await api.listDevices().catch(() => [] as DeviceRecord[]);
    const samples = await Promise.all(devices.value.map((device) => api.getRealtime(device.mac_address).catch(() => null)));
    const nextLatest = { ...latest.value };
    samples.forEach((sample) => {
      if (sample) {
        nextLatest[sample.device_mac] = mergeHealthSample(nextLatest[sample.device_mac], sample) ?? sample;
      }
    });
    latest.value = nextLatest;

    if (!devices.value.length) {
      dashboardLoadError.value = "";
    }

    lastSyncAt.value = new Date();
    dashboardLoading.value = false;
  }

  async function startPolling() {
    stopPolling();
    await refreshDebugData();
    refreshTimer = window.setInterval(() => {
      void refreshDebugData();
    }, pollIntervalMs);
  }

  onMounted(() => {
    void startPolling();
  });

  onUnmounted(() => {
    stopPolling();
  });

  return {
    dashboardLoadError,
    dashboardLoading,
    debugRows,
    devices,
    lastSyncAt,
    latest,
    refreshDebugData,
    stopPolling,
  };
}
