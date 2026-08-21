<script setup lang="ts">
import { LineChart, type LineSeriesOption } from "echarts/charts";
import {
  GraphicComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  type GraphicComponentOption,
  type GridComponentOption,
  type LegendComponentOption,
  type TooltipComponentOption,
} from "echarts/components";
import { type ComposeOption, init, use, type ECharts } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import type { CommunityDashboardDeviceItem, CommunityDashboardElderItem, HealthSample } from "../api/client";
import { riskLevelToChinese } from "../utils/riskLevel";

use([CanvasRenderer, GraphicComponent, GridComponent, LegendComponent, LineChart, TooltipComponent]);

type RealtimeOption = ComposeOption<
  GridComponentOption | LegendComponentOption | TooltipComponentOption | GraphicComponentOption | LineSeriesOption
>;

const props = defineProps<{
  elder: CommunityDashboardElderItem | null;
  device: CommunityDashboardDeviceItem | null;
  samples: HealthSample[];
  currentSample?: HealthSample | null;
  awaitingRealtime?: boolean;
}>();

const emit = defineEmits<{
  (event: "open-health-analysis"): void;
}>();

const chartRef = ref<HTMLDivElement | null>(null);
let chart: ECharts | null = null;

function parseBloodPressure(value?: string | null) {
  if (!value) return { sbp: null, dbp: null };
  const [sbpRaw, dbpRaw] = value.split("/", 2);
  const sbp = Number.parseInt(sbpRaw ?? "", 10);
  const dbp = Number.parseInt(dbpRaw ?? "", 10);
  return {
    sbp: Number.isFinite(sbp) ? sbp : null,
    dbp: Number.isFinite(dbp) ? dbp : null,
  };
}

function hasNumericValue(value?: number | null) {
  return typeof value === "number" && Number.isFinite(value) && value > 0;
}

const hasSamples = computed(() => props.samples.length > 0);
const isNoDevice = computed(() => Boolean(props.elder) && !props.elder?.device_mac);
const isPending = computed(() => props.device?.device_status === "pending");
const isOffline = computed(() => props.device?.device_status === "offline");
const isAwaitingRealtime = computed(() => !!props.awaitingRealtime && props.device?.ingest_mode === "serial");
const structuredSummary = computed(() => props.device?.structured_health ?? props.elder?.structured_health ?? null);

const tagGlossary: Record<string, string> = {
  hypertension: "血压偏高",
  hypotension: "血压偏低",
  fever: "体温异常",
  low_spo2: "血氧偏低",
  tachycardia: "心率偏高",
  bradycardia: "心率偏低",
  arrhythmia: "心律不齐",
  fall_detected: "跌倒风险"
};
const localizeTag = (tag: string) => tagGlossary[tag.toLowerCase()] || tag;

const structuredTags = computed(() => structuredSummary.value?.abnormal_tags ?? []);
const currentSample = computed(() => props.currentSample ?? props.samples[props.samples.length - 1] ?? null);
const hasObservedRealtime = computed(() =>
  Boolean(
    currentSample.value
      || hasSamples.value
      || props.device?.latest_timestamp
      || hasNumericValue(props.device?.heart_rate)
      || hasNumericValue(props.device?.blood_oxygen)
      || hasNumericValue(props.device?.temperature)
      || hasNumericValue(props.device?.steps)
      || props.device?.blood_pressure,
  ),
);
const showPendingPlaceholder = computed(() => isPending.value && !hasObservedRealtime.value);
const currentPressure = computed(() => parseBloodPressure(currentSample.value?.blood_pressure));
const showPointSymbols = computed(() => props.samples.length <= 2);
const scoreText = computed(() => structuredSummary.value?.health_score?.toFixed(1) ?? props.device?.latest_health_score ?? "--");

const chartSeries = computed(() => {
  const labels = props.samples.map((sample) =>
    new Date(sample.timestamp).toLocaleTimeString("zh-CN", {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }),
  );
  const pressure = props.samples.map((sample) => parseBloodPressure(sample.blood_pressure));
  return {
    labels,
    heartRate: props.samples.map((sample) => sample.heart_rate),
    spo2: props.samples.map((sample) => sample.blood_oxygen),
    sbp: pressure.map((item) => item.sbp),
    dbp: pressure.map((item) => item.dbp),
    temperature: props.samples.map((sample) => sample.temperature),
  };
});

const temperatureAxisRange = computed(() => {
  const values = chartSeries.value.temperature.filter(
    (value): value is number => typeof value === "number" && Number.isFinite(value),
  );
  if (!values.length) {
    return { min: 34, max: 42 };
  }
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const min = Math.max(20, Math.floor(minValue) - 1);
  const max = Math.min(45, Math.max(min + 4, Math.ceil(maxValue) + 1));
  return { min, max };
});

const metricCards = computed(() => [
  {
    label: "心率",
    value: currentSample.value ? `${currentSample.value.heart_rate} bpm` : "--",
    tone: "heart",
  },
  {
    label: "血氧",
    value: currentSample.value ? `${currentSample.value.blood_oxygen}%` : "--",
    tone: "spo2",
  },
  {
    label: "血压",
    value:
      currentPressure.value.sbp !== null && currentPressure.value.dbp !== null
        ? `${currentPressure.value.sbp}/${currentPressure.value.dbp} mmHg`
        : "--",
    tone: "pressure",
  },
  {
    label: "体温",
    value: currentSample.value ? `${currentSample.value.temperature.toFixed(1)} °C` : "--",
    tone: "temp",
  },
  {
    label: "健康分析",
    value: scoreText.value === "--" ? "--" : `评分 ${scoreText.value}`,
    tone: "analysis",
    action: true,
  },
]);

const panelMeta = computed(() => {
  if (!props.elder) {
    return {
      title: "请选择老人",
      subtitle: "先从上方老人卡片中选中一位监护对象，再查看设备绑定状态和实时数据。",
      badge: "未选择",
    };
  }

  if (isNoDevice.value) {
    return {
      title: props.elder.elder_name,
      subtitle: `${props.elder.apartment} · 当前无设备，需要先在移动端为这位老人绑定手环。`,
      badge: "无设备",
    };
  }

  if (isOffline.value) {
    return {
      title: props.elder.elder_name,
      subtitle: `${props.device?.device_name ?? "T10-WATCH"} · ${props.elder.device_mac} · 设备当前离线，暂时没有新的实时曲线。`,
      badge: "离线",
    };
  }

  if (showPendingPlaceholder.value) {
    return {
      title: props.elder.elder_name,
      subtitle: `${props.device?.device_name ?? "T10-WATCH"} · ${props.elder.device_mac} · 已绑定，等待首个实时包进入。`,
      badge: "待同步",
    };
  }

  if (isAwaitingRealtime.value) {
    return {
      title: props.elder.elder_name,
      subtitle: `${props.device?.device_name ?? "T10-WATCH"} · ${props.elder.device_mac} · 正在切换采集目标，等待新的串口样本。`,
      badge: "接入中",
    };
  }

  return {
    title: props.elder.elder_name,
    subtitle: `${props.device?.device_name ?? "T10-WATCH"} · ${props.elder.device_mac} · ${props.elder.apartment}`,
    badge: riskLevelToChinese(structuredSummary.value?.risk_level ?? props.elder.risk_level),
  };
});

const fallbackTag = computed(() => {
  if (isNoDevice.value) return "当前无设备";
  if (isOffline.value) return "设备离线";
  if (showPendingPlaceholder.value) return "等待首包";
  if (isAwaitingRealtime.value) return "等待新串口样本";
  return "当前没有持续异常标签";
});

const noteText = computed(() => {
  if (structuredSummary.value?.trigger_reasons?.[0]) {
    return structuredSummary.value.trigger_reasons[0];
  }
  if (isNoDevice.value) {
    return "先在移动端为这位老人绑定手环，绑定完成后回到这里点击对应老人即可查看实时曲线。";
  }
  if (isOffline.value) {
    return "这位老人已有设备，但当前处于离线状态，需要先恢复设备连接后才会继续更新。";
  }
  if (showPendingPlaceholder.value) {
    return "设备已经绑定成功，等待采集链路收到首个实时包后，这里会自动切换成实时监护曲线。";
  }
  if (isAwaitingRealtime.value) {
    return "当前正在切换采集目标，新的串口样本到达后，这里会立刻刷新。";
  }
  return "收到实时数据后会持续更新曲线，没有新数据时会保留上一条有效数据。";
});

const emptyTitle = computed(() => {
  if (!props.elder) return "请选择老人";
  if (isNoDevice.value) return "当前无设备";
  if (isOffline.value) return "设备离线";
  if (showPendingPlaceholder.value) return "等待实时数据";
  if (isAwaitingRealtime.value) return "正在接入实时数据";
  return "暂未收到实时数据";
});

const emptyDescription = computed(() => {
  if (!props.elder) return "先从上方老人卡片中选择一位监护对象。";
  if (isNoDevice.value) return "这位老人还没有绑定手环，所以这里不会显示实时曲线。";
  if (isOffline.value) return "设备恢复在线后，这里会继续展示最新曲线。";
  if (showPendingPlaceholder.value) return "已绑定设备，等待首个实时样本进入。";
  if (isAwaitingRealtime.value) return "串口采集目标已经切换，新包到达后就会开始绘制。";
  if (hasObservedRealtime.value) return "已有最近样本，等待更多数据点后就会继续拉出曲线。";
  return "等待下一次采样进入。";
});

function buildChartOption(): RealtimeOption {
  return {
    backgroundColor: "transparent",
    animation: false,
    animationDuration: 0,
    animationDurationUpdate: 0,
    legend: {
      top: 8,
      left: 10,
      itemWidth: 18,
      itemHeight: 8,
      textStyle: { color: "#64748b", fontSize: 13, fontWeight: 600 },
    },
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(255, 255, 255, 0.98)",
      borderColor: "rgba(15, 23, 42, 0.12)",
      textStyle: { color: "#0f172a" },
      extraCssText: "border-radius: 8px; box-shadow: 0 4px 16px rgba(15, 23, 42, 0.08);",
    },
    grid: [
      { left: "5%", top: 58, width: "41%", height: "29%" },
      { left: "55%", top: 58, width: "40%", height: "29%" },
      { left: "5%", top: "58%", width: "41%", height: "29%" },
      { left: "55%", top: "58%", width: "40%", height: "29%" },
    ],
    xAxis: Array.from({ length: 4 }, (_, index) => ({
      type: "category",
      gridIndex: index,
      boundaryGap: false,
      data: chartSeries.value.labels,
      axisLabel: { color: "#64748b", fontSize: 12, margin: 12 },
      axisLine: { lineStyle: { color: "rgba(15, 23, 42, 0.1)" } },
    })),
    yAxis: [
      {
        type: "value",
        gridIndex: 0,
        min: 40,
        max: 180,
        splitLine: { lineStyle: { color: "rgba(15, 23, 42, 0.06)", type: "dashed" } },
        axisLabel: { color: "#64748b", fontSize: 12 },
      },
      {
        type: "value",
        gridIndex: 1,
        min: 80,
        max: 100,
        splitLine: { lineStyle: { color: "rgba(15, 23, 42, 0.06)", type: "dashed" } },
        axisLabel: { color: "#64748b", fontSize: 12 },
      },
      {
        type: "value",
        gridIndex: 2,
        min: 40,
        max: 200,
        splitLine: { lineStyle: { color: "rgba(15, 23, 42, 0.06)", type: "dashed" } },
        axisLabel: { color: "#64748b", fontSize: 12 },
      },
      {
        type: "value",
        gridIndex: 3,
        min: temperatureAxisRange.value.min,
        max: temperatureAxisRange.value.max,
        splitLine: { lineStyle: { color: "rgba(15, 23, 42, 0.06)", type: "dashed" } },
        axisLabel: { color: "#64748b", fontSize: 12 },
      },
    ],
    series: [
      {
        name: "心率",
        type: "line",
        xAxisIndex: 0,
        yAxisIndex: 0,
        smooth: true,
        showSymbol: showPointSymbols.value,
        symbolSize: showPointSymbols.value ? 8 : 0,
        connectNulls: true,
        data: chartSeries.value.heartRate,
        lineStyle: { width: 3, color: "#ff6b57" },
        areaStyle: { color: "rgba(255, 107, 87, 0.10)" },
      },
      {
        name: "血氧",
        type: "line",
        xAxisIndex: 1,
        yAxisIndex: 1,
        smooth: true,
        showSymbol: showPointSymbols.value,
        symbolSize: showPointSymbols.value ? 8 : 0,
        connectNulls: true,
        data: chartSeries.value.spo2,
        lineStyle: { width: 3, color: "#17bebb" },
        areaStyle: { color: "rgba(23, 190, 187, 0.10)" },
      },
      {
        name: "收缩压",
        type: "line",
        xAxisIndex: 2,
        yAxisIndex: 2,
        smooth: true,
        showSymbol: showPointSymbols.value,
        symbolSize: showPointSymbols.value ? 8 : 0,
        connectNulls: true,
        data: chartSeries.value.sbp,
        lineStyle: { width: 2.5, color: "#9b5de5" },
      },
      {
        name: "舒张压",
        type: "line",
        xAxisIndex: 2,
        yAxisIndex: 2,
        smooth: true,
        showSymbol: showPointSymbols.value,
        symbolSize: showPointSymbols.value ? 8 : 0,
        connectNulls: true,
        data: chartSeries.value.dbp,
        lineStyle: { width: 2.5, color: "#5a189a" },
      },
      {
        name: "体温",
        type: "line",
        xAxisIndex: 3,
        yAxisIndex: 3,
        smooth: true,
        showSymbol: showPointSymbols.value,
        symbolSize: showPointSymbols.value ? 8 : 0,
        connectNulls: true,
        data: chartSeries.value.temperature,
        lineStyle: { width: 3, color: "#ff9f1c" },
        areaStyle: { color: "rgba(255, 159, 28, 0.10)" },
      },
    ],
    graphic: [
      { type: "text", left: "23%", top: 24, style: { text: "心率", fill: "rgba(15, 23, 42, 0.8)", fontWeight: 800, fontSize: 56, align: "center" } },
      { type: "text", left: "73%", top: 24, style: { text: "血氧", fill: "rgba(15, 23, 42, 0.8)", fontWeight: 800, fontSize: 56, align: "center" } },
      { type: "text", left: "23%", top: "52%", style: { text: "血压", fill: "rgba(15, 23, 42, 0.8)", fontWeight: 800, fontSize: 56, align: "center" } },
      { type: "text", left: "73%", top: "52%", style: { text: "体温", fill: "rgba(15, 23, 42, 0.8)", fontWeight: 800, fontSize: 56, align: "center" } },
    ],
  };
}

function updateChart() {
  if (!chartRef.value) return;
  chart ??= init(chartRef.value);
  chart.setOption(buildChartOption(), { notMerge: false });
}

function handleResize() {
  chart?.resize();
}

onMounted(() => {
  updateChart();
  window.addEventListener("resize", handleResize);
});

watch(() => [props.samples.length, props.device?.device_status, props.device?.ingest_mode], updateChart);
watch([chartSeries, showPointSymbols, temperatureAxisRange], updateChart);

onUnmounted(() => {
  window.removeEventListener("resize", handleResize);
  chart?.dispose();
  chart = null;
});
</script>

<template>
  <section class="panel realtime-monitor-panel">
    <div class="monitor-hero">
      <div>
        <p class="section-eyebrow">实时监护视图</p>
        <h2>{{ panelMeta.title }}</h2>
        <p class="monitor-subtitle">{{ panelMeta.subtitle }}</p>
      </div>
      <div class="monitor-badges">
        <span class="monitor-badge">{{ panelMeta.badge }}</span>
        <span class="monitor-badge subtle">模型评分 {{ scoreText }}</span>
      </div>
    </div>

    <div class="monitor-metrics">
      <article v-for="item in metricCards" :key="item.label" class="metric-plate" :data-tone="item.tone">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
        <button
          v-if="item.action"
          type="button"
          class="metric-action"
          @click="emit('open-health-analysis')"
        >
          查看分析
        </button>
      </article>
    </div>

    <div class="monitor-context">
      <div class="monitor-chip-row">
        <span v-for="tag in structuredTags" :key="tag" class="signal-chip">{{ localizeTag(tag) }}</span>
        <span v-if="!structuredTags.length" class="signal-chip muted">{{ fallbackTag }}</span>
      </div>
      <p class="monitor-note">{{ noteText }}</p>
    </div>

    <div class="monitor-chart-shell">
      <div ref="chartRef" class="monitor-chart"></div>
      <div v-if="!hasSamples" class="monitor-empty">
        <strong>{{ emptyTitle }}</strong>
        <p>{{ emptyDescription }}</p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.realtime-monitor-panel {
  display: grid;
  width: 100%;
  gap: 18px;
  min-height: calc(100vh - 220px);
  background: #ffffff;
}

.monitor-hero,
.monitor-badges,
.monitor-metrics,
.monitor-chip-row {
  display: flex;
  gap: 12px;
}

.monitor-hero {
  justify-content: space-between;
  align-items: flex-start;
}

.monitor-hero h2 {
  margin: 0;
  font-family: var(--font-display);
  font-size: clamp(2.15rem, 2.8vw, 3rem);
  color: var(--text-main);
}

.monitor-subtitle,
.monitor-note {
  margin: 8px 0 0;
  color: var(--text-sub);
  line-height: 1.7;
  font-size: 1rem;
}

.monitor-badges {
  flex-wrap: wrap;
  justify-content: flex-end;
}

.monitor-badge {
  padding: 12px 16px;
  border-radius: 999px;
  background: #f8fafc;
  color: var(--text-main);
  border: 1px solid var(--line-medium);
  font-size: 0.94rem;
  font-weight: 600;
}

.monitor-badge.subtle {
  background: #f1f5f9;
  color: var(--text-sub);
}

.monitor-metrics {
  flex-wrap: wrap;
}

.metric-plate {
  flex: 1 1 180px;
  min-width: 0;
  padding: 22px 20px;
  border-radius: 20px;
  background: #ffffff;
  border: 1px solid var(--line-medium);
  box-shadow: 0 2px 12px rgba(15, 23, 42, 0.03);
  display: grid;
  gap: 6px;
  text-align: center;
  justify-items: center;
}

.metric-plate span {
  color: var(--text-main);
  font-size: 1.4rem;
  letter-spacing: 0.05em;
  font-weight: 800;
}

.metric-plate strong {
  color: var(--text-main);
  font-size: 2.2rem;
  font-weight: 700;
  line-height: 1.15;
  letter-spacing: -0.02em;
}

.metric-plate[data-tone="heart"] strong {
  color: #ef4444;
}

.metric-plate[data-tone="spo2"] strong {
  color: #0ea5e9;
}

.metric-plate[data-tone="pressure"] strong {
  color: #8b5cf6;
}

.metric-plate[data-tone="temp"] strong {
  color: #f59e0b;
}

.metric-plate[data-tone="analysis"] strong {
  color: #3b82f6;
}

.metric-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 34px;
  padding: 0 14px;
  border: 1px solid #bfdbfe;
  border-radius: 999px;
  background: #eff6ff;
  color: #1d4ed8;
  font-size: 0.9rem;
  font-weight: 800;
  cursor: pointer;
  transition: background 180ms ease, border-color 180ms ease, transform 180ms ease;
}

.metric-action:hover {
  background: #dbeafe;
  border-color: #60a5fa;
  transform: translateY(-1px);
}

.monitor-context {
  display: grid;
  gap: 10px;
}

.monitor-chip-row {
  flex-wrap: wrap;
}

.signal-chip {
  padding: 8px 14px;
  border-radius: 999px;
  background: #fef2f2;
  color: #b91c1c;
  border: 1px solid rgba(239, 68, 68, 0.2);
  font-size: 0.92rem;
  font-weight: 600;
}

.signal-chip.muted {
  background: #f8fafc;
  color: var(--text-sub);
  border: 1px solid var(--line-medium);
}

.monitor-chart-shell {
  position: relative;
  width: 100%;
  min-width: 0;
}

.monitor-chart {
  height: min(74vh, 760px);
  min-height: 620px;
  width: 100%;
  display: block;
  border-radius: 28px;
  background: #ffffff;
  border: 1px solid var(--line-medium);
}

.monitor-empty {
  position: absolute;
  inset: 0;
  display: grid;
  place-content: center;
  gap: 10px;
  padding: 24px;
  text-align: center;
  background: rgba(255, 255, 255, 0.94);
  border-radius: 28px;
}

.monitor-empty strong {
  color: var(--text-main);
  font-size: 1.45rem;
}

.monitor-empty p {
  margin: 0;
  color: var(--text-sub);
  line-height: 1.7;
  font-size: 1rem;
  max-width: 520px;
}

@media (max-width: 960px) {
  .realtime-monitor-panel {
    min-height: auto;
  }

  .monitor-hero {
    flex-direction: column;
  }

  .monitor-badges {
    justify-content: flex-start;
  }

  .monitor-chart {
    min-height: 520px;
    height: 70vh;
  }
}
</style>
