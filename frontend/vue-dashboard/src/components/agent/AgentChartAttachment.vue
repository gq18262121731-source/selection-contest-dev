<script setup lang="ts">
import * as echarts from "echarts";
import { computed, onMounted, onUnmounted, ref, watch } from "vue";

type ChartAttachment = {
  id: string;
  title: string;
  summary?: string;
  echarts_option?: Record<string, unknown>;
};

const props = defineProps<{
  chart: ChartAttachment;
  height?: number;
}>();

const chartRef = ref<HTMLDivElement | null>(null);
let chartInstance: echarts.ECharts | null = null;

/** Detect whether the chart is a pie or donut */
function isPieChart(option: Record<string, unknown>): boolean {
  const series = Array.isArray(option.series) ? option.series : [];
  return series.some(
    (s: Record<string, unknown>) => s && s.type === "pie",
  );
}

const resolvedHeight = computed(() => {
  if (props.height) return props.height;
  // Pie charts get more vertical space by default
  const option = (props.chart.echarts_option ?? {}) as Record<string, unknown>;
  return isPieChart(option) ? 420 : 340;
});

// ── BioRender-inspired color palette ──────────────────────────────
// Curated from BioRender's scientific illustration style:
// clear, saturated-but-not-neon, publication-quality colors.
const BIORENDER_PALETTE = [
  "#3C91E6", // sky blue
  "#6BCB77", // fresh green
  "#FF6B6B", // coral red
  "#FFB347", // warm amber
  "#A78BFA", // soft purple
  "#4ECDC4", // teal
  "#FF8FAB", // rose pink
  "#5DADE2", // light royal blue
  "#F7DC6F", // lemon
  "#E59866", // terracotta
];

// Specific semantic colors for risk/status pie charts
const PIE_SEMANTIC_COLORS: Record<string, string> = {
  high: "#E74C3C",
  medium: "#F5B041",
  low: "#58D68D",
  unknown: "#AEB6BF",
  online: "#58D68D",
  offline: "#AEB6BF",
  warning: "#F5B041",
  "高风险": "#E74C3C",
  "中风险": "#F5B041",
  "低风险": "#58D68D",
  "未知": "#AEB6BF",
  "在线": "#58D68D",
  "离线": "#AEB6BF",
  "告警": "#F5B041",
};

// Deep-merge theme overrides into any echarts option coming from backend
function applyEchartsTheme(option: Record<string, unknown>): Record<string, unknown> {
  const axisStyle = {
    axisLine: { lineStyle: { color: "rgba(15, 23, 42, 0.1)" } },
    splitLine: { lineStyle: { color: "rgba(15, 23, 42, 0.05)", type: "dashed" } },
    axisLabel: { color: "#475569", fontSize: 13 },
    nameTextStyle: { color: "#64748b", fontSize: 13 },
  };

  const applyAxis = (axes: unknown) => {
    if (!axes) return axes;
    const arr = Array.isArray(axes) ? axes : [axes];
    return arr.map((ax: Record<string, unknown>) => ({ ...axisStyle, ...ax,
      axisLine: { ...(axisStyle.axisLine), ...((ax.axisLine as object) ?? {}) },
      splitLine: { ...(axisStyle.splitLine), ...((ax.splitLine as object) ?? {}) },
      axisLabel: { ...(axisStyle.axisLabel), ...((ax.axisLabel as object) ?? {}) },
    }));
  };

  // Upgrade series based on chart type
  const series = Array.isArray(option.series)
    ? (option.series as Record<string, unknown>[]).map((s, i) => {
        // ── Pie / Donut charts ──
        if (s.type === "pie") {
          const dataArr = Array.isArray(s.data) ? s.data as Record<string, unknown>[] : [];
          const coloredData = dataArr.map((item, di) => {
            const name = String(item.name ?? "");
            const semanticColor = PIE_SEMANTIC_COLORS[name.toLowerCase()] ?? PIE_SEMANTIC_COLORS[name];
            const color = semanticColor ?? BIORENDER_PALETTE[di % BIORENDER_PALETTE.length];
            return {
              ...item,
              itemStyle: {
                color,
                borderColor: "#ffffff",
                borderWidth: 3,
                shadowBlur: 12,
                shadowColor: "rgba(0, 0, 0, 0.08)",
                ...((item.itemStyle as object) ?? {}),
              },
            };
          });

          return {
            ...s,
            radius: s.radius ?? ["42%", "75%"],
            center: s.center ?? ["50%", "54%"],
            data: coloredData,
            label: {
              show: true,
              fontSize: 14,
              fontWeight: 600,
              color: "#334155",
              formatter: "{b}\n{d}%",
              lineHeight: 20,
              ...((s.label as object) ?? {}),
            },
            labelLine: {
              length: 18,
              length2: 14,
              lineStyle: { color: "#94a3b8", width: 1.5 },
              ...((s.labelLine as object) ?? {}),
            },
            emphasis: {
              scale: true,
              scaleSize: 8,
              itemStyle: {
                shadowBlur: 24,
                shadowColor: "rgba(0, 0, 0, 0.18)",
              },
              label: { fontSize: 16, fontWeight: 700 },
              ...((s.emphasis as object) ?? {}),
            },
            animationType: "scale",
            animationEasing: "elasticOut",
            animationDelay: (idx: number) => idx * 80,
          };
        }

        // ── Line / Bar / Area charts ──
        return {
          smooth: true,
          showSymbol: false,
          symbolSize: 7,
          ...s,
          lineStyle: { width: 2.8, color: BIORENDER_PALETTE[i % BIORENDER_PALETTE.length], ...(s.lineStyle as object ?? {}) },
          areaStyle: s.type === "line" ? {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: (BIORENDER_PALETTE[i % BIORENDER_PALETTE.length] + "44") },
              { offset: 1, color: (BIORENDER_PALETTE[i % BIORENDER_PALETTE.length] + "05") },
            ]),
            ...(s.areaStyle as object ?? {}),
          } : s.areaStyle,
          itemStyle: {
            color: BIORENDER_PALETTE[i % BIORENDER_PALETTE.length],
            borderRadius: s.type === "bar" ? [6, 6, 0, 0] : undefined,
            ...(s.itemStyle as object ?? {}),
          },
        };
      })
    : option.series;

  const themed: Record<string, unknown> = {
    ...option,
    backgroundColor: "transparent",
    color: BIORENDER_PALETTE,
    textStyle: { color: "#334155", fontFamily: "'Manrope','Noto Sans SC',sans-serif", fontSize: 13 },
    legend: {
      top: 8,
      textStyle: { color: "#475569", fontSize: 14, fontWeight: 500 },
      inactiveColor: "#cbd5e1",
      itemGap: 16,
      ...((option.legend as object) ?? {}),
    },
    tooltip: {
      trigger: isPieChart(option) ? "item" : "axis",
      backgroundColor: "rgba(255, 255, 255, 0.98)",
      borderColor: "rgba(15, 23, 42, 0.12)",
      borderWidth: 1,
      textStyle: { color: "#0f172a", fontSize: 14 },
      axisPointer: {
        lineStyle: { color: "rgba(15, 23, 42, 0.15)", width: 1.5, type: "dashed" },
      },
      ...((option.tooltip as object) ?? {}),
    },
    series,
  };

  // Non-pie charts get grid + axis theming
  if (!isPieChart(option)) {
    themed.grid = option.grid ?? { left: "4%", right: "3%", top: 48, bottom: 32, containLabel: true };
    themed.xAxis = applyAxis(option.xAxis);
    themed.yAxis = applyAxis(option.yAxis);
  }

  return themed;
}

function renderChart() {
  if (!chartRef.value) return;
  chartInstance ??= echarts.init(chartRef.value, undefined, { renderer: "canvas" });
  const base = (props.chart.echarts_option ?? {}) as Record<string, unknown>;
  chartInstance.setOption(applyEchartsTheme(base) as echarts.EChartsCoreOption, true);
  chartInstance.resize();
}

function handleResize() {
  chartInstance?.resize();
}

onMounted(() => {
  renderChart();
  window.addEventListener("resize", handleResize);
});

watch(() => props.chart, renderChart, { deep: true });

onUnmounted(() => {
  window.removeEventListener("resize", handleResize);
  chartInstance?.dispose();
  chartInstance = null;
});
</script>

<template>
  <article class="agent-chart-card">
    <header class="agent-chart-card__head">
      <div>
        <h4>{{ chart.title }}</h4>
        <p v-if="chart.summary">{{ chart.summary }}</p>
      </div>
      <span class="agent-chart-card__badge">CHART</span>
    </header>
    <div ref="chartRef" class="agent-chart-card__canvas" :style="{ height: `${resolvedHeight}px` }"></div>
  </article>
</template>

<style scoped>
.agent-chart-card {
  display: grid;
  gap: 16px;
  padding: 24px;
  border-radius: 24px;
  background: #ffffff;
  border: 1px solid var(--line-medium);
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.04);
  position: relative;
  overflow: hidden;
}

.agent-chart-card::before {
  content: '';
  position: absolute;
  inset: 0 auto auto 0;
  width: 100%;
  height: 4px;
  background: linear-gradient(90deg, #3C91E6 0%, #4ECDC4 40%, #6BCB77 100%);
  border-radius: 24px 24px 0 0;
  opacity: 0.9;
}

.agent-chart-card__head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.agent-chart-card__head h4 {
  margin: 0;
  color: var(--text-main);
  font-size: 1.25rem;
  font-weight: 800;
  letter-spacing: -0.01em;
}

.agent-chart-card__head p {
  margin: 6px 0 0;
  color: var(--text-sub);
  line-height: 1.65;
  font-size: 0.95rem;
}

.agent-chart-card__badge {
  padding: 5px 12px;
  border-radius: 999px;
  background: linear-gradient(135deg, #f0fdf4, #ecfeff);
  color: #0f766e;
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.12em;
  border: 1px solid rgba(15, 118, 110, 0.15);
  flex-shrink: 0;
  margin-top: 2px;
}

.agent-chart-card__canvas {
  width: 100%;
  min-height: 280px;
  border-radius: 16px;
  background: #fafbfc;
  border: 1px solid var(--line-medium);
}
</style>
