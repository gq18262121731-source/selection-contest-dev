<script setup lang="ts">
import { computed, ref, watch } from "vue";
import TrendChart from "../components/TrendChart.vue";
import VisionConnectionDebugCard from "../components/VisionConnectionDebugCard.vue";
import PageHeader from "../components/layout/PageHeader.vue";
import { useDebugDashboard } from "../composables/useDebugDashboard";
import { useDeviceTrend } from "../composables/useDeviceTrend";
import type { PageKey } from "../composables/useHashRouting";

defineProps<{
  canGoCommunity: boolean;
}>();

const emit = defineEmits<{
  navigate: [page: PageKey];
}>();

const { dashboardLoadError, dashboardLoading, debugRows, devices, lastSyncAt, latest, refreshDebugData } = useDebugDashboard(5000);
const selectedDeviceMac = ref("");
const { focusLatest, focusTrend, trendWindowMinutes } = useDeviceTrend({
  selectedDeviceMac,
  latest,
  pollIntervalMs: 5000,
  enableSocket: false,
});

const syncLabel = computed(() =>
  lastSyncAt.value ? lastSyncAt.value.toLocaleTimeString("zh-CN", { hour12: false }) : "尚未同步",
);
const pageMeta = computed(() => [
  `设备 ${devices.value.length}`,
  `当前对象 ${selectedDeviceMac.value || "未选择"}`,
  `同步 ${syncLabel.value}`,
]);

watch(
  devices,
  (list) => {
    if (!list.length) {
      selectedDeviceMac.value = "";
      return;
    }
    if (!list.some((item) => item.mac_address === selectedDeviceMac.value)) {
      selectedDeviceMac.value = list[0].mac_address;
    }
  },
  { immediate: true },
);
</script>

<template>
  <section class="page-stack">
    <PageHeader
      eyebrow="Tool Entry / Debug"
      title="调试看板"
      description="调试入口已经从主头部与主导航降级到工具入口，这里只展示设备实时数据、原始字段和趋势调试信息。"
      :meta="pageMeta"
    >
      <template #actions>
        <button type="button" class="ghost-btn" @click="refreshDebugData">刷新数据</button>
        <button v-if="canGoCommunity" type="button" class="ghost-btn" @click="emit('navigate', 'overview')">返回社区总览</button>
      </template>
    </PageHeader>

    <p v-if="dashboardLoadError" class="feedback-banner feedback-error">{{ dashboardLoadError }}</p>

    <div v-else-if="dashboardLoading && !debugRows.length" class="state-block state-loading">
      <strong>正在加载调试数据</strong>
      <p>设备实时数据、原始字段和趋势曲线会在这里集中展示。</p>
    </div>

    <section v-else class="panel-grid relation-grid">
      <VisionConnectionDebugCard class="relation-span-2" />

      <article class="panel relation-intro">
        <p class="section-eyebrow">Realtime Debug</p>
        <h2>实时设备概览</h2>
        <p class="subtle-copy">
          这里保留设备级实时调试能力，帮助核对在线状态、包类型、关键指标和最近同步时间。
        </p>
        <div class="dashboard-chip-row">
          <span class="meta-pill">设备 {{ devices.length }}</span>
          <span class="meta-pill">同步 {{ syncLabel }}</span>
        </div>
      </article>

      <article class="panel relation-table">
        <h2>设备实时明细</h2>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>设备</th>
                <th>状态</th>
                <th>包类型</th>
                <th>心率</th>
                <th>血氧</th>
                <th>体温</th>
                <th>电量</th>
                <th>步数</th>
                <th>环境温度</th>
                <th>表面温度</th>
                <th>时间</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in debugRows"
                :key="row.mac"
                :class="{ current: row.mac === selectedDeviceMac }"
                @click="selectedDeviceMac = row.mac"
              >
                <td><strong>{{ row.deviceName }}</strong><small>{{ row.mac }}</small></td>
                <td>{{ row.status }}</td>
                <td>{{ row.sample?.packet_type ?? "-" }}</td>
                <td>{{ row.sample?.heart_rate ?? "-" }}</td>
                <td>{{ row.sample?.blood_oxygen ?? "-" }}</td>
                <td>{{ row.sample?.temperature ?? "-" }}</td>
                <td>{{ row.sample?.battery ?? "-" }}</td>
                <td>{{ row.sample?.steps ?? "-" }}</td>
                <td>{{ row.sample?.ambient_temperature ?? "-" }}</td>
                <td>{{ row.sample?.surface_temperature ?? "-" }}</td>
                <td>{{ row.sample ? new Date(row.sample.timestamp).toLocaleString("zh-CN", { hour12: false }) : "-" }}</td>
              </tr>
              <tr v-if="!debugRows.length">
                <td colspan="11">当前没有可用的设备实时数据。</td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>

      <article v-if="focusLatest" class="panel relation-table">
        <h2>当前设备原始字段</h2>
        <div class="table-wrap">
          <table>
            <tbody>
              <tr><th>设备 MAC</th><td>{{ focusLatest.device_mac }}</td></tr>
              <tr><th>UUID</th><td>{{ focusLatest.device_uuid ?? "-" }}</td></tr>
              <tr><th>包类型</th><td>{{ focusLatest.packet_type ?? "-" }}</td></tr>
              <tr><th>SOS</th><td>{{ focusLatest.sos_flag ? "是" : "否" }}</td></tr>
              <tr><th>血压</th><td>{{ focusLatest.blood_pressure ?? "-" }}</td></tr>
              <tr><th>步数</th><td>{{ focusLatest.steps ?? "-" }}</td></tr>
              <tr><th>采样时间</th><td>{{ new Date(focusLatest.timestamp).toLocaleString("zh-CN", { hour12: false }) }}</td></tr>
            </tbody>
          </table>
        </div>
      </article>

      <TrendChart
        v-if="selectedDeviceMac && focusTrend.length"
        :device-mac="selectedDeviceMac"
        :samples="focusTrend"
        :window-minutes="trendWindowMinutes"
        @change-window="trendWindowMinutes = $event"
      />
    </section>
  </section>
</template>
