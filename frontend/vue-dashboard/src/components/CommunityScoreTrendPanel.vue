<script setup lang="ts">
import { BarChart, LineChart } from "echarts/charts";
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
  type GridComponentOption,
  type LegendComponentOption,
  type TooltipComponentOption,
} from "echarts/components";
import { type BarSeriesOption, type LineSeriesOption } from "echarts/charts";
import { type ComposeOption, init, use, type ECharts } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import type { CommunityDashboardTrendPoint } from "../api/client";

use([BarChart, CanvasRenderer, GridComponent, LegendComponent, LineChart, TooltipComponent]);

type TrendOption = ComposeOption<
  BarSeriesOption | LineSeriesOption | GridComponentOption | LegendComponentOption | TooltipComponentOption
>;

const props = defineProps<{
  trend: CommunityDashboardTrendPoint[];
}>();

const chartRef = ref<HTMLDivElement | null>(null);
let chart: ECharts | null = null;

const summary = computed(() => {
  const latest = props.trend[props.trend.length - 1];
  const previous = props.trend[props.trend.length - 2];
  const scoreDelta = latest && previous ? latest.average_health_score - previous.average_health_score : 0;
  return {
    latestScore: latest?.average_health_score ?? 0,
    latestAlerts: latest?.alert_count ?? 0,
    latestHighRisk: latest?.high_risk_count ?? 0,
    scoreDelta,
  };
});

function renderChart() {
  if (!chartRef.value) return;
  chart ??= init(chartRef.value);

  const option: TrendOption = {
    backgroundColor: "transparent",
    animationDuration: 500,
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(255, 255, 255, 0.98)",
      borderColor: "rgba(15, 23, 42, 0.12)",
      textStyle: { color: "#0f172a" },
    },
    legend: {
      top: 6,
      textStyle: { color: "#475569" },
    },
    grid: { left: 42, right: 42, top: 54, bottom: 30 },
    xAxis: {
      type: "category",
      boundaryGap: true,
      data: props.trend.map((item) =>
        new Date(item.timestamp).toLocaleTimeString("zh-CN", {
          hour12: false,
          hour: "2-digit",
          minute: "2-digit",
        }),
      ),
      axisLine: { lineStyle: { color: "rgba(15, 23, 42, 0.1)" } },
      axisLabel: { color: "#64748b" },
    },
    yAxis: [
      {
        type: "value",
        name: "平均评分",
        min: 0,
        max: 100,
        axisLabel: { color: "#64748b" },
        splitLine: { lineStyle: { color: "rgba(15, 23, 42, 0.05)" } },
      },
      {
        type: "value",
        name: "告警 / 高风险",
        minInterval: 1,
        axisLabel: { color: "#64748b" },
      },
    ],
    series: [
      {
        name: "平均健康评分",
        type: "line",
        smooth: true,
        symbol: "circle",
        symbolSize: 6,
        data: props.trend.map((item) => item.average_health_score),
        lineStyle: { width: 3, color: "#0f766e" },
        itemStyle: { color: "#0f766e" },
        areaStyle: { color: "rgba(15, 118, 110, 0.10)" },
      },
      {
        name: "新增告警",
        type: "bar",
        yAxisIndex: 1,
        barMaxWidth: 18,
        data: props.trend.map((item) => item.alert_count),
        itemStyle: { color: "rgba(249, 115, 22, 0.72)", borderRadius: [10, 10, 0, 0] },
      },
      {
        name: "高风险对象",
        type: "line",
        yAxisIndex: 1,
        smooth: true,
        symbol: "none",
        data: props.trend.map((item) => item.high_risk_count),
        lineStyle: { width: 2, color: "#dc2626" },
      },
    ],
  };

  chart.setOption(option, { notMerge: true });
  chart.resize();
}

function handleResize() {
  chart?.resize();
}

onMounted(() => {
  renderChart();
  window.addEventListener("resize", handleResize);
});

watch(() => props.trend, renderChart, { deep: true });

onUnmounted(() => {
  window.removeEventListener("resize", handleResize);
  chart?.dispose();
});
</script>

<template>
  <section class="panel trend-panel">
    <div class="panel-head">
      <div>
        <h2>社区趋势总览</h2>
        <p class="panel-subtitle">按小时汇总近 12 小时的平均健康评分、告警新增和高风险对象数量，方便值守人员判断社区整体态势。</p>
      </div>
      <span>{{ trend.length }} 个时间点</span>
    </div>

    <div class="community-trend-kpis">
      <article>
        <span>当前平均评分</span>
        <strong>{{ summary.latestScore.toFixed(1) }}</strong>
      </article>
      <article>
        <span>本时段新增告警</span>
        <strong>{{ summary.latestAlerts }}</strong>
      </article>
      <article>
        <span>当前高风险对象</span>
        <strong>{{ summary.latestHighRisk }}</strong>
      </article>
      <article>
        <span>评分环比变化</span>
        <strong>{{ summary.scoreDelta >= 0 ? "+" : "" }}{{ summary.scoreDelta.toFixed(1) }}</strong>
      </article>
    </div>

    <div ref="chartRef" class="trend-canvas"></div>
  </section>
</template>

<style scoped>
.community-trend-kpis {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-top: 14px;
}

.community-trend-kpis article {
  display: grid;
  gap: 8px;
  border-radius: 16px;
  border: 1px solid var(--line-medium);
  background: #ffffff;
  padding: 14px;
}

.community-trend-kpis span {
  color: var(--text-sub);
  font-size: 0.82rem;
}

.community-trend-kpis strong {
  color: var(--text-main);
  font-size: 1.3rem;
  font-weight: 700;
}

@media (max-width: 960px) {
  .community-trend-kpis {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .community-trend-kpis {
    grid-template-columns: 1fr;
  }
}
</style>
