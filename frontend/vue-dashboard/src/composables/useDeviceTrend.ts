import { computed, onMounted, onUnmounted, ref, watch, type Ref } from "vue";
import { api, type HealthSample } from "../api/client";
import { mergeHealthSample, mergeHealthSeries } from "../domain/healthSampleMerge";

const DISPLAY_READY_SERIAL_PACKET_TYPES = new Set(["response_ab", "response_a", "response_a_only", "response_b", "broadcast", "legacy_response", "legacy_response_a", "legacy_response_b"]);

function parseBloodPressure(value?: string | null): { sbp: number | null; dbp: number | null } {
  if (!value) return { sbp: null, dbp: null };
  const [sbpRaw, dbpRaw] = value.split("/", 2);
  const sbp = Number.parseInt(sbpRaw ?? "", 10);
  const dbp = Number.parseInt(dbpRaw ?? "", 10);
  return {
    sbp: Number.isFinite(sbp) ? sbp : null,
    dbp: Number.isFinite(dbp) ? dbp : null,
  };
}

export function isDisplayReadySample(sample: HealthSample | null | undefined, ingestMode?: string | null): sample is HealthSample {
  if (!sample) return false;
  if (ingestMode === "serial" || sample.source === "serial") {
    if (sample.packet_type && !DISPLAY_READY_SERIAL_PACKET_TYPES.has(sample.packet_type)) return false;
    // 串口模式：至少一项有效生命体征即可展示（后端已回填上一时刻值）
    const hasAnyVital = sample.heart_rate > 0 || sample.blood_oxygen > 0 || sample.temperature > 0;
    return hasAnyVital;
  }
  if (sample.heart_rate <= 0 || sample.blood_oxygen <= 0 || sample.temperature <= 30) return false;
  return true;
}

export function useDeviceTrend(options: {
  selectedDeviceMac: Ref<string>;
  latest: Ref<Record<string, HealthSample>>;
  pollIntervalMs?: number;
  enableSocket?: boolean;
}) {
  const trendWindowMinutes = ref(180);
  const trendStore = ref<Record<string, HealthSample[]>>({});
  const focusLatest = computed(() =>
    options.selectedDeviceMac.value ? options.latest.value[options.selectedDeviceMac.value] ?? null : null,
  );
  const focusTrend = computed(() => trendStore.value[options.selectedDeviceMac.value] ?? []);

  let refreshTimer: number | null = null;
  let healthSocket: WebSocket | null = null;

  async function refreshTrend(mac = options.selectedDeviceMac.value, minutes = trendWindowMinutes.value) {
    if (!mac) return;
    const trend = await api.getTrend(mac, minutes, 120).catch(() => []);
    const mergedTrend = mergeHealthSeries(trend);
    if (mergedTrend.length) {
      const latestSample = mergedTrend[mergedTrend.length - 1];
      options.latest.value = {
        ...options.latest.value,
        [mac]: mergeHealthSample(options.latest.value[mac], latestSample) ?? latestSample,
      };
    }
    trendStore.value = { ...trendStore.value, [mac]: mergedTrend.slice(-240) };
  }

  function stopRuntime() {
    if (refreshTimer !== null) {
      window.clearInterval(refreshTimer);
      refreshTimer = null;
    }
    healthSocket?.close();
    healthSocket = null;
  }

  function connectHealthSocket(mac: string) {
    healthSocket?.close();
    healthSocket = null;

    if (!mac || options.enableSocket === false) return;

    healthSocket = api.healthSocket(mac);
    healthSocket.onmessage = (event) => {
      try {
        const sample = JSON.parse(event.data) as HealthSample;
        const mergedLatest = mergeHealthSample(options.latest.value[sample.device_mac], sample) ?? sample;
        options.latest.value = { ...options.latest.value, [sample.device_mac]: mergedLatest };
        const previous = trendStore.value[sample.device_mac] ?? [];
        const merged = mergeHealthSeries([...previous, mergedLatest]);
        trendStore.value = { ...trendStore.value, [sample.device_mac]: merged.slice(-240) };
      } catch {
        // Keep page state stable if socket data is malformed.
      }
    };
  }

  function startRuntime() {
    stopRuntime();
    if (!options.selectedDeviceMac.value) return;

    void refreshTrend();
    connectHealthSocket(options.selectedDeviceMac.value);

    const pollIntervalMs = options.pollIntervalMs ?? 15000;
    refreshTimer = window.setInterval(() => {
      void refreshTrend();
    }, pollIntervalMs);
  }

  watch([options.selectedDeviceMac, trendWindowMinutes], () => {
    startRuntime();
  });

  onMounted(() => {
    startRuntime();
  });

  onUnmounted(() => {
    stopRuntime();
  });

  return {
    focusLatest,
    focusTrend,
    refreshTrend,
    stopRuntime,
    trendStore,
    trendWindowMinutes,
  };
}
