import { ref } from "vue";

import { api, ApiError, type HealthScoreInsightRequest, type HealthScoreInsightResponse } from "../api/client";

export function useHealthScoreInsight() {
  const insight = ref<HealthScoreInsightResponse | null>(null);
  const loading = ref(false);
  const error = ref("");
  const lastRequestedMac = ref("");

  async function analyze(payload: HealthScoreInsightRequest) {
    const mac = payload.device_mac?.trim();
    if (!mac) {
      insight.value = null;
      error.value = "当前未绑定设备，无法生成智能解读。";
      return null;
    }

    loading.value = true;
    error.value = "";
    lastRequestedMac.value = mac;
    try {
      const result = await api.getHealthScoreInsight({
        window_minutes: 5,
        use_llm: true,
        ...payload,
        device_mac: mac,
      });
      insight.value = result;
      return result;
    } catch (err) {
      const message = err instanceof ApiError || err instanceof Error ? err.message : "AI健康分析暂不可用。";
      error.value = message;
      return null;
    } finally {
      loading.value = false;
    }
  }

  return {
    insight,
    loading,
    error,
    lastRequestedMac,
    analyze,
  };
}
