<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { FileDown, RefreshCw } from "lucide-vue-next";
import AgentChartAttachment from "./agent/AgentChartAttachment.vue";
import DecisionSummaryCard from "./report/DecisionSummaryCard.vue";
import EventTimeline from "./report/EventTimeline.vue";
import RecommendationPanel from "./report/RecommendationPanel.vue";
import RiskCardGroup from "./report/RiskCardGroup.vue";
import {
  api,
  type ChartPayload,
  type CommunityDashboardAlertItem,
  type CommunityDashboardDeviceItem,
  type CommunityWindowReportResponse,
  type WindowKind,
} from "../api/client";
import { useReportExport } from "../composables/useReportExport";

type RiskTone = "high" | "medium" | "low";

type RiskCardItem = {
  id: string;
  name: string;
  code: string;
  riskLevel: RiskTone;
  reason: string;
  action: string;
  confidence: string;
  healthScore: string;
  activeAlertCount: number;
};

type DecisionMetric = {
  label: string;
  value: string;
  note: string;
};

type RecommendationGroup = {
  title: string;
  tone: "p0" | "p1" | "p2";
  items: string[];
};

const props = defineProps<{
  communityName: string;
  deviceMacs: string[];
  deviceStatuses: CommunityDashboardDeviceItem[];
  recentAlerts: CommunityDashboardAlertItem[];
}>();

const selectedWindow = ref<WindowKind>("day");
const loading = ref(false);
const errorText = ref("");
const report = ref<CommunityWindowReportResponse | null>(null);

const { exportError, exportReport, exporting } = useReportExport();

const deviceStatusByMac = computed(() =>
  props.deviceStatuses.reduce<Record<string, CommunityDashboardDeviceItem>>((accumulator, item) => {
    accumulator[item.device_mac] = item;
    return accumulator;
  }, {}),
);

const analysis = computed(() => report.value?.analysis ?? null);
const metrics = computed(() => analysis.value?.key_metrics ?? {});
const highRiskEntities = computed(() => analysis.value?.high_risk_entities ?? []);
const charts = computed(() => analysis.value?.chart_payloads ?? []);
const trendFindings = computed(() => analysis.value?.trend_findings ?? []);
const orderedAlerts = computed(() =>
  [...props.recentAlerts].sort(
    (left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime(),
  ),
);

function toNumber(value: unknown, fallback = 0) {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
}

function normalizeRiskTone(value: string): RiskTone {
  if (value === "high") return "high";
  if (value === "medium") return "medium";
  return "low";
}

function percentage(value: number) {
  return `${Math.round(value * 100)}%`;
}

function formatHealthScore(value: number | null | undefined) {
  if (typeof value !== "number" || Number.isNaN(value)) return "--";
  return value.toFixed(0);
}

function deriveConfidence(device: CommunityDashboardDeviceItem | undefined, riskLevel: RiskTone, activeAlertCount: number) {
  let confidence = riskLevel === "high" ? 0.74 : riskLevel === "medium" ? 0.66 : 0.58;
  const structured = device?.structured_health;

  if (structured?.active_event_count) {
    confidence += Math.min(structured.active_event_count * 0.04, 0.12);
  }
  if (structured?.trigger_reasons?.length) {
    confidence += Math.min(structured.trigger_reasons.length * 0.02, 0.08);
  }
  if (activeAlertCount > 0) {
    confidence += Math.min(activeAlertCount * 0.04, 0.12);
  }
  if (typeof device?.latest_health_score === "number") {
    if (device.latest_health_score <= 65) confidence += 0.08;
    else if (device.latest_health_score >= 88) confidence += 0.03;
  }

  return percentage(Math.min(Math.max(confidence, 0.55), 0.96));
}

function deriveAction(riskLevel: RiskTone, reasons: string[], device: CommunityDashboardDeviceItem | undefined, activeAlertCount: number) {
  const reasonText = reasons.join(" ");
  if (riskLevel === "high") {
    if (activeAlertCount > 0) return "立即电话核实对象状态，并安排现场复核或责任人闭环确认。";
    if (reasonText.includes("离线")) return "立即排查设备离线链路，确认采集是否中断并补齐现场观察。";
    return "立即核实生命体征波动原因，必要时升级为现场处置。";
  }
  if (riskLevel === "medium") {
    if (device?.device_status === "warning") return "24 小时内完成复测与设备状态复核，并补充随访记录。";
    return "24 小时内回访确认趋势是否持续，视结果决定是否升为重点对象。";
  }
  return "纳入持续观察清单，下个巡检周期复核趋势即可。";
}

const layeredRiskCards = computed(() => {
  const mediumHighCards = highRiskEntities.value.map((entity) => {
    const device = deviceStatusByMac.value[entity.device_mac];
    const riskLevel = normalizeRiskTone(entity.risk_level);
    const reasons = entity.reasons.length ? entity.reasons : device?.risk_reasons ?? ["等待补充风险解释"];
    return {
      id: `${riskLevel}-${entity.device_mac}`,
      name: entity.elder_name || device?.elder_name || entity.device_mac,
      code: device?.elder_id || entity.device_mac,
      riskLevel,
      reason: reasons[0] ?? "等待补充风险解释",
      action: deriveAction(riskLevel, reasons, device, entity.active_alert_count),
      confidence: deriveConfidence(device, riskLevel, entity.active_alert_count),
      healthScore: formatHealthScore(entity.latest_health_score ?? device?.latest_health_score),
      activeAlertCount: entity.active_alert_count,
    } satisfies RiskCardItem;
  });

  const seenMacs = new Set(highRiskEntities.value.map((item) => item.device_mac));
  const lowCards = props.deviceStatuses
    .filter((item) => item.risk_level === "low")
    .filter((item) => !seenMacs.has(item.device_mac))
    .map((item) => {
      const reasons = item.risk_reasons.length ? item.risk_reasons : ["当前未发现显著异常，维持常规观察。"];
      return {
        id: `low-${item.device_mac}`,
        name: item.elder_name || item.device_mac,
        code: item.elder_id || item.device_mac,
        riskLevel: "low" as const,
        reason: reasons[0],
        action: deriveAction("low", reasons, item, item.active_alarm_count),
        confidence: deriveConfidence(item, "low", item.active_alarm_count),
        healthScore: formatHealthScore(item.latest_health_score),
        activeAlertCount: item.active_alarm_count,
      } satisfies RiskCardItem;
    });

  return {
    high: mediumHighCards.filter((item) => item.riskLevel === "high"),
    medium: mediumHighCards.filter((item) => item.riskLevel === "medium"),
    low: lowCards,
  };
});

const reportStatus = computed<"stable" | "attention" | "high">(() => {
  const highCount = layeredRiskCards.value.high.length;
  const mediumCount = layeredRiskCards.value.medium.length;
  const avgScore = toNumber(metrics.value.average_health_score, 0);
  const alertCount = toNumber(metrics.value.window_alert_count, orderedAlerts.value.length);

  if (highCount > 0 || alertCount >= 4 || avgScore < 72) return "high";
  if (mediumCount > 0 || alertCount > 0 || avgScore < 82) return "attention";
  return "stable";
});

const reportStatusLabel = computed(() => {
  if (reportStatus.value === "high") return "高风险";
  if (reportStatus.value === "attention") return "注意";
  return "稳定";
});

const windowLabel = computed(() => (selectedWindow.value === "week" ? "过去一周" : "过去一天"));

const reportSerial = computed(() => {
  const date = report.value?.generated_at ? new Date(report.value.generated_at) : new Date();
  const stamp = [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("");
  return `COMMUNITY-HO-${stamp}-${selectedWindow.value.toUpperCase()}`;
});

const decisionMetrics = computed<DecisionMetric[]>(() => [
  {
    label: "平均健康分",
    value: `${toNumber(metrics.value.average_health_score, 0).toFixed(1)}`,
    note: "时间窗口内整体评分",
  },
  {
    label: "告警总数",
    value: `${toNumber(metrics.value.window_alert_count, orderedAlerts.value.length)}`,
    note: "窗口内累计异常事件",
  },
  {
    label: "风险人数",
    value: `${layeredRiskCards.value.high.length + layeredRiskCards.value.medium.length}`,
    note: "需重点交接对象",
  },
]);

const urgentMatters = computed(() => {
  const urgent: string[] = [];

  for (const item of layeredRiskCards.value.high.slice(0, 2)) {
    urgent.push(`优先核实 ${item.name}：${item.reason}`);
  }

  const latestAlert = orderedAlerts.value[0];
  if (latestAlert && urgent.length < 3) {
    urgent.push(
      `${latestAlert.elder_name ?? latestAlert.device_mac} 于 ${new Date(latestAlert.created_at).toLocaleTimeString("zh-CN", { hour12: false })} 出现 ${latestAlert.alarm_type}，需确认处置闭环。`,
    );
  }

  if (!urgent.length) {
    urgent.push("当前无新增高风险对象，建议按计划完成巡检和趋势复核。");
  }

  return urgent.slice(0, 3);
});

const spokenConclusion = computed(() => {
  const highCount = layeredRiskCards.value.high.length;
  const mediumCount = layeredRiskCards.value.medium.length;
  const topName = layeredRiskCards.value.high[0]?.name || layeredRiskCards.value.medium[0]?.name;
  const alertCount = toNumber(metrics.value.window_alert_count, orderedAlerts.value.length);

  if (reportStatus.value === "high") {
    return `本班次社区进入高风险关注状态，当前需优先处理 ${topName ?? "重点对象"} 等 ${Math.max(highCount, 1)} 个高风险对象，并同步闭环 ${alertCount} 条异常事件。`;
  }
  if (reportStatus.value === "attention") {
    return `本班次社区整体可控，但仍有 ${mediumCount} 个中风险对象和 ${alertCount} 条异常事件需要持续跟进。`;
  }
  return "本班次社区整体运行稳定，无新增高风险对象，按常规巡检和趋势观察交接即可。";
});

const summaryLine = computed(() => {
  const findings = trendFindings.value.slice(0, 2).join(" ");
  return findings || "当前报告以风险分层、异常时间线和图表趋势为核心，支持值守人员快速完成交班复述与处置排序。";
});

function seriesValues(chartId: string) {
  const target = charts.value.find((item) => item.id === chartId);
  if (!target) return [];
  const series = Array.isArray(target.echarts_option.series) ? target.echarts_option.series : [];
  const first = series[0];
  if (!first || !Array.isArray((first as Record<string, unknown>).data)) return [];
  return ((first as Record<string, unknown>).data as unknown[]).map((item) => toNumber(item, 0));
}

function categoryLabels(chartId: string) {
  const target = charts.value.find((item) => item.id === chartId);
  const xAxis = target?.echarts_option.xAxis;
  const axis = Array.isArray(xAxis) ? xAxis[0] : xAxis;
  const data = axis && typeof axis === "object" ? (axis as Record<string, unknown>).data : [];
  return Array.isArray(data) ? data.map((item) => String(item)) : [];
}

function chartConclusion(chartId: string) {
  const highCount = layeredRiskCards.value.high.length;
  const mediumCount = layeredRiskCards.value.medium.length;

  if (chartId === "community_score_trend") {
    const values = seriesValues(chartId);
    if (values.length >= 2) {
      const delta = values[values.length - 1] - values[0];
      if (Math.abs(delta) >= 3) {
        return delta > 0
          ? `当前平均健康分较窗口起点回升 ${delta.toFixed(1)} 分，整体态势有所修复。`
          : `当前平均健康分较窗口起点下降 ${Math.abs(delta).toFixed(1)} 分，需要警惕持续波动。`;
      }
    }
    return "当前平均健康分波动不大，整体仍以结构化巡检为主。";
  }

  if (chartId === "community_alert_trend") {
    const values = seriesValues(chartId);
    const labels = categoryLabels(chartId);
    const peakValue = Math.max(...values, 0);
    const peakIndex = values.findIndex((item) => item === peakValue);
    return peakValue > 0 && peakIndex >= 0
      ? `当前风险主要集中在 ${labels[peakIndex]} 时段，共出现 ${peakValue} 条异常事件。`
      : "当前时间窗口内未形成明显告警集中时段。";
  }

  if (chartId === "risk_distribution") {
    return highCount > 0
      ? `当前高风险对象 ${highCount} 个，中风险对象 ${mediumCount} 个，值守资源应优先向高风险侧倾斜。`
      : mediumCount > 0
        ? "当前暂无高风险对象，但中风险对象仍需在 24 小时内跟进复核。"
        : "当前风险分布以低风险为主，可维持常规观察节奏。";
  }

  if (chartId === "device_online_distribution") {
    const offline = toNumber(metrics.value.offline_device_count, 0);
    const warning = toNumber(metrics.value.warning_device_count, 0);
    return offline > 0 || warning > 0
      ? `当前存在 ${offline} 台离线设备、${warning} 台告警设备，交接时需同步采集链路排查安排。`
      : "当前设备在线状态整体平稳，未形成明显链路风险。";
  }

  if (chartId === "top_risk_entities") {
    const first = layeredRiskCards.value.high[0] ?? layeredRiskCards.value.medium[0];
    return first
      ? `${first.name} 当前位于优先关注序列首位，应作为交接首条重点对象。`
      : "当前未形成突出的重点对象排序。";
  }

  return "当前图表反映了本时间窗口内的结构化趋势，可结合上方分层结果综合判断。";
}

const chartInsights = computed(() =>
  charts.value.map((chart) => ({
    chart,
    conclusion: chartConclusion(chart.id),
  })),
);

const recommendationGroups = computed<RecommendationGroup[]>(() => {
  const offlineCount = toNumber(metrics.value.offline_device_count, 0);
  const p0: string[] = [];
  const p1: string[] = [];
  const p2: string[] = [];

  for (const item of layeredRiskCards.value.high) {
    p0.push(`立即核实 ${item.name}：${item.action}`);
  }
  if (orderedAlerts.value.length) {
    p0.push(`立即闭环最近 ${Math.min(orderedAlerts.value.length, 3)} 条异常事件，确认电话回访或现场核查结果。`);
  }
  if (offlineCount > 0) {
    p0.push(`立即排查 ${offlineCount} 台离线设备，避免关键对象采集链路持续缺数。`);
  }

  for (const item of layeredRiskCards.value.medium) {
    p1.push(`24 小时内跟进 ${item.name}：${item.action}`);
  }
  if (!p1.length) {
    p1.push("24 小时内复核中风险波动对象，并同步更新交接记录。");
  }

  if (layeredRiskCards.value.low.length) {
    p2.push(`持续观察 ${layeredRiskCards.value.low.length} 个低风险对象，关注趋势是否由稳转弱。`);
  }
  p2.push("持续观察平均健康分与告警趋势，下个班次继续复核是否出现风险抬头。");

  return [
    { title: "P0 立即执行", tone: "p0", items: Array.from(new Set(p0)).slice(0, 4) },
    { title: "P1 24小时内", tone: "p1", items: Array.from(new Set(p1)).slice(0, 4) },
    { title: "P2 持续观察", tone: "p2", items: Array.from(new Set(p2)).slice(0, 4) },
  ];
});

const reportOverviewItems = computed(() => {
  const totalDevices = props.deviceStatuses.length;
  const offlineDevices = props.deviceStatuses.filter((item) => item.device_status === "offline").length;
  const activeDevices = Math.max(totalDevices - offlineDevices, 0);
  const averageScore = toNumber(metrics.value.average_health_score, 0).toFixed(1);
  const alertCount = toNumber(metrics.value.window_alert_count, orderedAlerts.value.length);
  const focusCount = layeredRiskCards.value.high.length + layeredRiskCards.value.medium.length;

  return [
    {
      label: "设备覆盖",
      value: `共 ${totalDevices} 台，纳入分析 ${activeDevices} 台，离线 ${offlineDevices} 台`,
    },
    {
      label: "风险分布",
      value: `高风险 ${layeredRiskCards.value.high.length} 台，中风险 ${layeredRiskCards.value.medium.length} 台，低风险 ${layeredRiskCards.value.low.length} 台`,
    },
    {
      label: "核心指标",
      value: `平均健康分 ${averageScore}，窗口告警 ${alertCount} 条，重点对象 ${focusCount} 人`,
    },
    {
      label: "交班结论",
      value: spokenConclusion.value,
    },
  ];
});

const reportRiskRows = computed(() => {
  const rows = [
    ...layeredRiskCards.value.high,
    ...layeredRiskCards.value.medium,
    ...layeredRiskCards.value.low.slice(0, 4),
  ];
  return rows.slice(0, 8);
});

const reportPriorityRows = computed(() => {
  const focusRows = [...layeredRiskCards.value.high, ...layeredRiskCards.value.medium];
  return (focusRows.length ? focusRows : reportRiskRows.value).slice(0, 5);
});

const pdfRiskGroups = computed(() => [
  { title: "高风险对象", tone: "high" as const, items: layeredRiskCards.value.high },
  { title: "中风险对象", tone: "medium" as const, items: layeredRiskCards.value.medium },
  { title: "低风险对象", tone: "low" as const, items: layeredRiskCards.value.low },
]);

async function loadReport() {
  if (!props.deviceMacs.length) {
    report.value = null;
    return;
  }

  loading.value = true;
  errorText.value = "";

  try {
    report.value = await api.getCommunityWindowReport({
      window: selectedWindow.value,
      device_macs: props.deviceMacs,
    });
  } catch (error) {
    report.value = null;
    errorText.value = error instanceof Error ? error.message : "交接报告加载失败，请稍后重试。";
  } finally {
    loading.value = false;
  }
}

async function handleExport() {
  await exportReport(
    document.getElementById("report-pdf-body"),
    `${props.communityName || "社区"}运营报告正文`,
  );
}

watch(() => props.deviceMacs.join("|"), loadReport, { immediate: true });
watch(selectedWindow, loadReport);
</script>

<template>
  <section class="handover-report-shell">
    <div class="handover-report-toolbar">
      <div class="handover-report-toolbar__copy">
        <p class="handover-report-toolbar__eyebrow">Community Handover Report</p>
        <h2>社区健康运营交接报告</h2>
        <p>屏幕版用于快速浏览，A4 医疗版用于打印、交班和比赛展示，导出时将自动使用标准分页文档。</p>
      </div>

      <div class="handover-report-toolbar__actions">
        <div class="handover-window-toggle">
          <button
            type="button"
            class="handover-window-toggle__btn"
            :class="{ 'handover-window-toggle__btn--active': selectedWindow === 'day' }"
            @click="selectedWindow = 'day'"
          >
            过去一天
          </button>
          <button
            type="button"
            class="handover-window-toggle__btn"
            :class="{ 'handover-window-toggle__btn--active': selectedWindow === 'week' }"
            @click="selectedWindow = 'week'"
          >
            过去一周
          </button>
        </div>

        <button type="button" class="handover-ghost-btn" :disabled="loading" @click="loadReport">
          <RefreshCw :size="16" />
          {{ loading ? "刷新中..." : "刷新报告" }}
        </button>

        <button type="button" class="handover-primary-btn" :disabled="loading || exporting" @click="handleExport">
          <FileDown :size="16" />
          {{ exporting ? "导出中..." : "导出交接报告PDF" }}
        </button>
      </div>
    </div>

    <p v-if="errorText || exportError" class="handover-report-shell__error">
      {{ errorText || exportError }}
    </p>

    <div v-if="report && !loading" class="report-container">
      <DecisionSummaryCard
        :title="`${communityName || '当前社区'}值守决策摘要`"
        :summary-line="summaryLine"
        :spoken-conclusion="spokenConclusion"
        :generated-at="new Date(report.generated_at).toLocaleString('zh-CN', { hour12: false })"
        :status="reportStatus"
        :urgent-matters="urgentMatters"
        :metrics="decisionMetrics"
      />

      <section class="handover-section">
        <div class="handover-section__head">
          <div>
            <p class="handover-section__eyebrow">Risk Layer</p>
            <h3>风险分层</h3>
            <p>按红黄绿语义拆成可执行优先级，方便交班人员在一屏内完成风险排序。</p>
          </div>
        </div>

        <div class="handover-risk-grid">
          <RiskCardGroup
            title="高风险对象"
            tone="high"
            description="需要本班次优先处理并明确闭环责任。"
            :items="layeredRiskCards.high"
          />
          <RiskCardGroup
            title="中风险对象"
            tone="medium"
            description="需要在 24 小时内完成复核与回访。"
            :items="layeredRiskCards.medium"
          />
          <RiskCardGroup
            title="低风险对象"
            tone="low"
            description="当前整体平稳，但仍需纳入持续观察。"
            :items="layeredRiskCards.low"
          />
        </div>
      </section>

      <EventTimeline :events="orderedAlerts" />

      <section class="handover-section">
        <div class="handover-section__head">
          <div>
            <p class="handover-section__eyebrow">Chart Reading</p>
            <h3>图表分析区</h3>
            <p>保留现有 echarts 数据能力，但每张图都补齐临床式结论解释，不再只展示图形。</p>
          </div>
        </div>

        <div class="handover-chart-grid">
          <article v-for="item in chartInsights" :key="item.chart.id" class="handover-chart-block">
            <AgentChartAttachment :chart="item.chart" />
            <div class="handover-chart-block__insight">
              <span>结论解释</span>
              <p>{{ item.conclusion }}</p>
            </div>
          </article>
        </div>
      </section>

      <RecommendationPanel :groups="recommendationGroups" />
    </div>

    <div v-else-if="loading" class="handover-report-shell__loading">
      正在生成交接报告视图，请稍候。
    </div>

    <div v-else class="handover-report-shell__empty">
      当前没有可用于生成交接报告的社区设备样本，请先确认设备绑定与数据上报状态。
    </div>

    <div v-if="report" class="report-pdf-host" aria-hidden="true">
      <div id="report-pdf-body" class="report-pdf-body">
        <header class="report-pdf-body__header">
          <p>Community Operation Report</p>
          <h2>{{ communityName || "当前社区" }}健康运营分析报告</h2>
          <span>{{ new Date(report.generated_at).toLocaleString("zh-CN", { hour12: false }) }}</span>
        </header>

        <section class="report-pdf-section">
          <h3>整体概况</h3>
          <ul class="report-pdf-overview">
            <li v-for="item in reportOverviewItems" :key="item.label">
              <strong>{{ item.label }}</strong>
              <span>{{ item.value }}</span>
            </li>
          </ul>
        </section>

        <section class="report-pdf-section">
          <h3>风险分层表格</h3>
          <div class="report-pdf-table-wrap">
            <table class="report-pdf-table">
              <thead>
                <tr>
                  <th>风险等级</th>
                  <th>对象</th>
                  <th>编号</th>
                  <th>风险原因</th>
                  <th>建议动作</th>
                  <th>置信度</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in reportRiskRows" :key="item.id">
                  <td>{{ item.riskLevel === "high" ? "高风险" : item.riskLevel === "medium" ? "中风险" : "低风险" }}</td>
                  <td>{{ item.name }}</td>
                  <td>{{ item.code }}</td>
                  <td>{{ item.reason }}</td>
                  <td>{{ item.action }}</td>
                  <td>{{ item.confidence }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="report-pdf-section">
          <h3>优先对象</h3>
          <div class="report-pdf-priority">
            <article v-for="item in reportPriorityRows" :key="`priority-${item.id}`" class="report-pdf-priority__item">
              <div class="report-pdf-priority__head">
                <strong>{{ item.name }}</strong>
                <span>{{ item.riskLevel === "high" ? "高风险" : item.riskLevel === "medium" ? "中风险" : "观察对象" }}</span>
              </div>
              <p>{{ item.reason }}</p>
              <small>{{ item.action }}</small>
            </article>
          </div>
        </section>

        <section class="report-pdf-section">
          <h3>处置建议</h3>
          <div class="report-pdf-recommendations">
            <article v-for="group in recommendationGroups" :key="group.title" class="report-pdf-recommendations__group">
              <strong>{{ group.title }}</strong>
              <ul>
                <li v-for="entry in group.items" :key="entry">{{ entry }}</li>
              </ul>
            </article>
          </div>
        </section>
      </div>
    </div>
  </section>
</template>

<style scoped>
.handover-report-shell,
.report-container,
.handover-risk-grid,
.handover-chart-grid {
  display: grid;
  gap: 22px;
}

.report-pdf-host {
  position: absolute;
  left: -100000px;
  top: 0;
  width: 210mm;
  pointer-events: none;
}

.report-pdf-body {
  width: 210mm;
  box-sizing: border-box;
  padding: 16mm 14mm;
  background: #ffffff;
  color: #17212d;
  display: grid;
  gap: 8mm;
  font-family: var(--font-main);
}

.report-pdf-body__header,
.report-pdf-section,
.report-pdf-priority,
.report-pdf-recommendations {
  display: grid;
  gap: 4mm;
}

.report-pdf-body__header p,
.report-pdf-body__header span {
  margin: 0;
  color: #5b6575;
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.report-pdf-body__header h2,
.report-pdf-section h3 {
  margin: 0;
  color: #111827;
}

.report-pdf-body__header h2 {
  font-size: 24px;
  line-height: 1.3;
}

.report-pdf-section {
  padding: 5mm;
  border-radius: 4mm;
  border: 1px solid #d7dde5;
  background: #fcfcfd;
}

.report-pdf-section h3 {
  font-size: 16px;
}

.report-pdf-overview,
.report-pdf-recommendations ul {
  margin: 0;
  padding-left: 5mm;
  display: grid;
  gap: 2.5mm;
}

.report-pdf-overview li,
.report-pdf-recommendations li {
  color: #1f2937;
  font-size: 12px;
  line-height: 1.7;
}

.report-pdf-overview strong {
  margin-right: 2mm;
}

.report-pdf-table-wrap {
  overflow: hidden;
  border-radius: 3mm;
  border: 1px solid #d7dde5;
}

.report-pdf-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
}

.report-pdf-table th,
.report-pdf-table td {
  padding: 3mm 2.6mm;
  border-bottom: 1px solid #e5e7eb;
  text-align: left;
  vertical-align: top;
  font-size: 11px;
  line-height: 1.6;
  word-break: break-word;
}

.report-pdf-table th {
  background: #f5f7fb;
  color: #344256;
  font-weight: 800;
}

.report-pdf-table tr:last-child td {
  border-bottom: none;
}

.report-pdf-priority {
  grid-template-columns: 1fr;
}

.report-pdf-priority__item,
.report-pdf-recommendations__group {
  display: grid;
  gap: 2.5mm;
  padding: 4mm;
  border-radius: 3mm;
  background: #ffffff;
  border: 1px solid #dbe2ea;
}

.report-pdf-priority__head {
  display: flex;
  justify-content: space-between;
  gap: 3mm;
  align-items: flex-start;
}

.report-pdf-priority__head strong,
.report-pdf-recommendations__group strong {
  color: #111827;
  font-size: 12px;
}

.report-pdf-priority__head span {
  color: #8b5e00;
  font-size: 10px;
  font-weight: 700;
}

.report-pdf-priority__item p,
.report-pdf-priority__item small {
  margin: 0;
  color: #374151;
  font-size: 11px;
  line-height: 1.65;
}

.handover-report-shell {
  padding: clamp(22px, 2.6vw, 30px);
  border-radius: 30px;
  background:
    radial-gradient(circle at top left, rgba(186, 230, 253, 0.28), transparent 25%),
    radial-gradient(circle at top right, rgba(254, 240, 138, 0.18), transparent 24%),
    linear-gradient(180deg, #f7f7f2 0%, #f4f7fb 100%);
  border: 1px solid rgba(15, 23, 42, 0.08);
}

.handover-report-toolbar {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  align-items: flex-start;
}

.handover-report-toolbar__copy {
  max-width: 760px;
}

.handover-report-toolbar__eyebrow,
.handover-section__eyebrow {
  margin: 0 0 8px;
  color: #9a3412;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  font-size: 0.72rem;
  font-weight: 800;
}

.handover-report-toolbar h2,
.handover-section h3 {
  margin: 0;
  color: var(--text-main);
  font-family: var(--font-display);
  letter-spacing: -0.03em;
}

.handover-report-toolbar h2 {
  font-size: clamp(1.8rem, 2.5vw, 2.35rem);
}

.handover-report-toolbar p,
.handover-section__head p {
  margin: 10px 0 0;
  color: var(--text-sub);
  line-height: 1.78;
}

.handover-report-toolbar__actions,
.handover-window-toggle {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  justify-content: flex-end;
}

.handover-window-toggle {
  padding: 6px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.8);
  border: 1px solid rgba(15, 23, 42, 0.08);
}

.handover-window-toggle__btn,
.handover-ghost-btn,
.handover-primary-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 46px;
  border-radius: 999px;
  padding: 0 18px;
  font-weight: 700;
  cursor: pointer;
  transition: transform 180ms ease, box-shadow 180ms ease, background 180ms ease, border-color 180ms ease;
}

.handover-window-toggle__btn {
  border: none;
  background: transparent;
  color: var(--text-sub);
}

.handover-window-toggle__btn--active {
  background: #101e34;
  color: #eff6ff;
}

.handover-ghost-btn {
  border: 1px solid rgba(15, 23, 42, 0.12);
  background: rgba(255, 255, 255, 0.9);
  color: var(--text-main);
}

.handover-primary-btn {
  border: none;
  background: linear-gradient(135deg, #b91c1c 0%, #dc2626 100%);
  color: #fff7f7;
  box-shadow: 0 10px 24px rgba(185, 28, 28, 0.22);
}

.handover-ghost-btn:hover:not(:disabled),
.handover-primary-btn:hover:not(:disabled),
.handover-window-toggle__btn:hover:not(:disabled) {
  transform: translateY(-1px);
}

.handover-primary-btn:disabled,
.handover-ghost-btn:disabled,
.handover-window-toggle__btn:disabled {
  opacity: 0.58;
  cursor: not-allowed;
}

.handover-section {
  display: grid;
  gap: 18px;
}

.handover-section__head {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: flex-start;
}

.handover-risk-grid {
  grid-template-columns: 1fr;
}

.handover-chart-grid {
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
}

.handover-chart-block {
  display: grid;
  gap: 12px;
}

.handover-chart-block__insight {
  padding: 16px 18px;
  border-radius: 20px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: rgba(255, 255, 255, 0.76);
}

.handover-chart-block__insight span {
  display: inline-flex;
  margin-bottom: 8px;
  padding: 6px 10px;
  border-radius: 999px;
  background: #e0f2fe;
  color: #0c4a6e;
  font-size: 0.75rem;
  font-weight: 800;
}

.handover-chart-block__insight p {
  margin: 0;
  color: var(--text-main);
  line-height: 1.7;
}

.handover-report-shell__error,
.handover-report-shell__loading,
.handover-report-shell__empty {
  padding: 18px 20px;
  border-radius: 20px;
  line-height: 1.7;
}

.handover-report-shell__error {
  background: #fff1f2;
  color: #be123c;
  border: 1px solid #fecdd3;
}

.handover-report-shell__loading,
.handover-report-shell__empty {
  background: rgba(255, 255, 255, 0.8);
  color: var(--text-sub);
  border: 1px solid rgba(15, 23, 42, 0.08);
}

@media (max-width: 980px) {
  .handover-report-toolbar {
    flex-direction: column;
  }

  .handover-report-toolbar__actions {
    width: 100%;
    justify-content: flex-start;
  }
}
</style>
