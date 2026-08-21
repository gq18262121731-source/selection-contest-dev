import { computed, onMounted, onUnmounted, ref, watch, type Ref } from "vue";
import { api, type CommunityDashboardSummary, type SessionUser } from "../api/client";
import { getStoredSessionToken } from "./useSessionAuth";

export function useCommunityDashboard(sessionUser: Ref<SessionUser>) {
  const summary = ref<CommunityDashboardSummary | null>(null);
  const dashboardLoading = ref(false);
  const dashboardLoadError = ref("");
  const selectedDeviceMac = ref("");
  const lastSyncAt = ref<Date | null>(null);

  let refreshTimer: number | null = null;

  const community = computed(() => summary.value?.community ?? null);
  const metrics = computed(() => summary.value?.metrics ?? null);
  const topRiskElders = computed(() => summary.value?.top_risk_elders ?? []);
  const deviceStatuses = computed(() => summary.value?.device_statuses ?? []);
  const recentAlerts = computed(() => summary.value?.recent_alerts ?? []);
  const scoreTrend = computed(() => summary.value?.trend ?? []);
  const relationTopology = computed(() => summary.value?.relation_topology ?? null);

  function stopPolling() {
    if (refreshTimer !== null) {
      window.clearInterval(refreshTimer);
      refreshTimer = null;
    }
  }

  async function refreshDashboardData() {
    const token = getStoredSessionToken();
    if (!token) {
      summary.value = null;
      dashboardLoadError.value = "当前登录状态已失效，请重新登录。";
      return;
    }

    dashboardLoading.value = true;
    dashboardLoadError.value = "";
    try {
      const data = await api.getCommunityDashboard(token);
      summary.value = data;

      const visibleDeviceMacs = new Set(data.device_statuses.map((item) => item.device_mac));
      if (!selectedDeviceMac.value || !visibleDeviceMacs.has(selectedDeviceMac.value)) {
        selectedDeviceMac.value =
          data.top_risk_elders.find((item) => item.device_mac)?.device_mac ?? data.device_statuses[0]?.device_mac ?? "";
      }

      lastSyncAt.value = data.metrics.last_sync_at ? new Date(data.metrics.last_sync_at) : new Date();
    } catch (error) {
      summary.value = null;
      dashboardLoadError.value = error instanceof Error ? error.message : "社区总览加载失败，请稍后重试。";
    } finally {
      dashboardLoading.value = false;
    }
  }

  async function startPolling() {
    stopPolling();
    await refreshDashboardData();
    refreshTimer = window.setInterval(() => {
      void refreshDashboardData();
    }, 15000);
  }

  watch(
    () => sessionUser.value.id,
    () => {
      void startPolling();
    },
  );

  onMounted(() => {
    void startPolling();
  });

  onUnmounted(() => {
    stopPolling();
  });

  return {
    community,
    dashboardLoadError,
    dashboardLoading,
    deviceStatuses,
    lastSyncAt,
    metrics,
    recentAlerts,
    refreshDashboardData,
    relationTopology,
    scoreTrend,
    selectedDeviceMac,
    summary,
    topRiskElders,
  };
}
