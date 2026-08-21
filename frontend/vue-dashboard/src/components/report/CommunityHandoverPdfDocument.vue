<script setup lang="ts">
import { computed } from "vue";
import type { ChartPayload, CommunityDashboardAlertItem } from "../../api/client";
import AgentChartAttachment from "../agent/AgentChartAttachment.vue";

type DecisionMetric = {
  label: string;
  value: string;
  note: string;
};

type RiskCardItem = {
  id: string;
  name: string;
  code: string;
  riskLevel: "high" | "medium" | "low";
  reason: string;
  action: string;
  confidence: string;
  healthScore: string;
  activeAlertCount: number;
};

type PdfRiskGroup = {
  title: string;
  tone: "high" | "medium" | "low";
  items: RiskCardItem[];
};

type RecommendationGroup = {
  title: string;
  tone: "p0" | "p1" | "p2";
  items: string[];
};

type ChartInsight = {
  chart: ChartPayload;
  conclusion: string;
};

const props = defineProps<{
  communityName: string;
  generatedAt: string;
  windowLabel: string;
  reportSerial: string;
  statusLabel: string;
  statusTone: "stable" | "attention" | "high";
  spokenConclusion: string;
  summaryLine: string;
  metrics: DecisionMetric[];
  urgentMatters: string[];
  riskGroups: PdfRiskGroup[];
  alerts: CommunityDashboardAlertItem[];
  chartInsights: ChartInsight[];
  recommendationGroups: RecommendationGroup[];
}>();

const chartChunks = computed(() => {
  const chunks: ChartInsight[][] = [];
  for (let index = 0; index < props.chartInsights.length; index += 2) {
    chunks.push(props.chartInsights.slice(index, index + 2));
  }
  return chunks;
});

const riskPreviewGroups = computed(() =>
  props.riskGroups.map((group) => ({
    ...group,
    items: group.items.slice(0, group.tone === "low" ? 3 : 4),
  })),
);

const alertPreview = computed(() => props.alerts.slice(0, 8));
const p0Items = computed(() => props.recommendationGroups.find((group) => group.tone === "p0")?.items ?? []);
</script>

<template>
  <div class="pdf-report-host" aria-hidden="true">
    <div id="pdf-report" class="pdf-report-container">
      <section class="pdf-page pdf-page--cover">
        <header class="pdf-cover-header">
          <div>
            <p class="pdf-kicker">Medical Grade Community Handover</p>
            <h1>社区健康交接报告</h1>
            <p class="pdf-cover-subtitle">A4 标准化可打印版本 · 面向值守交班与应急决策</p>
          </div>
          <div class="pdf-cover-badge" :data-tone="statusTone">
            <span>社区状态</span>
            <strong>{{ statusLabel }}</strong>
          </div>
        </header>

        <div class="pdf-cover-meta">
          <article>
            <span>社区名称</span>
            <strong>{{ communityName || "当前社区" }}</strong>
          </article>
          <article>
            <span>观察窗口</span>
            <strong>{{ windowLabel }}</strong>
          </article>
          <article>
            <span>报告编号</span>
            <strong>{{ reportSerial }}</strong>
          </article>
          <article>
            <span>生成时间</span>
            <strong>{{ generatedAt }}</strong>
          </article>
        </div>

        <div class="pdf-cover-hero">
          <div class="pdf-cover-hero__main">
            <p class="pdf-section-label">交班口播结论</p>
            <strong>{{ spokenConclusion }}</strong>
            <p>{{ summaryLine }}</p>
          </div>
          <div class="pdf-cover-hero__side">
            <p class="pdf-section-label">P0 立即执行</p>
            <ol>
              <li v-for="item in p0Items.slice(0, 3)" :key="item">{{ item }}</li>
            </ol>
          </div>
        </div>

        <div class="pdf-cover-metrics">
          <article v-for="metric in metrics" :key="metric.label">
            <span>{{ metric.label }}</span>
            <strong>{{ metric.value }}</strong>
            <small>{{ metric.note }}</small>
          </article>
        </div>

        <footer class="pdf-footer">
          <span>医疗级交接版式 · 适配 A4 打印</span>
          <span>第 1 页</span>
        </footer>
      </section>

      <section class="pdf-page">
        <header class="pdf-page-header">
          <div>
            <p class="pdf-kicker">Executive Summary</p>
            <h2>一屏决策摘要与风险分层</h2>
          </div>
          <span>{{ reportSerial }}</span>
        </header>

        <section class="pdf-summary-box">
          <div>
            <p class="pdf-section-label">当前最紧急事项</p>
            <ul>
              <li v-for="item in urgentMatters" :key="item">{{ item }}</li>
            </ul>
          </div>
        </section>

        <section class="pdf-risk-layer">
          <article
            v-for="group in riskPreviewGroups"
            :key="group.title"
            class="pdf-risk-column"
            :data-tone="group.tone"
          >
            <header>
              <strong>{{ group.title }}</strong>
              <span>{{ group.items.length }} 项</span>
            </header>
            <div v-if="group.items.length" class="pdf-risk-list">
              <article v-for="item in group.items" :key="item.id" class="pdf-risk-card">
                <div class="pdf-risk-card__head">
                  <div>
                    <small>{{ item.code }}</small>
                    <strong>{{ item.name }}</strong>
                  </div>
                  <span>{{ item.confidence }}</span>
                </div>
                <p><b>原因：</b>{{ item.reason }}</p>
                <p><b>动作：</b>{{ item.action }}</p>
                <div class="pdf-risk-card__meta">
                  <span>健康分 {{ item.healthScore }}</span>
                  <span>告警 {{ item.activeAlertCount }}</span>
                </div>
              </article>
            </div>
            <div v-else class="pdf-empty-note">当前无该分层对象。</div>
          </article>
        </section>

        <footer class="pdf-footer">
          <span>{{ communityName || "当前社区" }}</span>
          <span>第 2 页</span>
        </footer>
      </section>

      <section class="pdf-page">
        <header class="pdf-page-header">
          <div>
            <p class="pdf-kicker">Incident Timeline</p>
            <h2>异常事件时间线</h2>
          </div>
          <span>{{ windowLabel }}</span>
        </header>

        <div class="pdf-timeline">
          <article
            v-for="event in alertPreview"
            :key="event.alarm_id"
            class="pdf-timeline-item"
            :data-tone="event.alarm_level >= 3 ? 'high' : event.alarm_level === 2 ? 'medium' : 'low'"
          >
            <div class="pdf-timeline-item__marker"></div>
            <div class="pdf-timeline-item__body">
              <div class="pdf-timeline-item__head">
                <strong>{{ event.elder_name ?? event.device_mac }}</strong>
                <time>{{ new Date(event.created_at).toLocaleString("zh-CN", { hour12: false }) }}</time>
              </div>
              <div class="pdf-timeline-item__meta">
                <span>{{ event.alarm_type }}</span>
                <span>{{ event.alarm_layer }}</span>
                <span>等级 {{ event.alarm_level }}</span>
              </div>
              <p>{{ event.message }}</p>
            </div>
          </article>
        </div>

        <footer class="pdf-footer">
          <span>异常事件按时间倒序排列</span>
          <span>第 3 页</span>
        </footer>
      </section>

      <section v-for="(chunk, pageIndex) in chartChunks" :key="`chart-${pageIndex}`" class="pdf-page">
        <header class="pdf-page-header">
          <div>
            <p class="pdf-kicker">Chart Interpretation</p>
            <h2>图表分析与结论解释</h2>
          </div>
          <span>图表页 {{ pageIndex + 1 }}</span>
        </header>

        <div class="pdf-chart-grid">
          <article v-for="item in chunk" :key="item.chart.id" class="pdf-chart-card">
            <AgentChartAttachment :chart="item.chart" :height="220" />
            <div class="pdf-chart-card__insight">
              <span>结论解释</span>
              <p>{{ item.conclusion }}</p>
            </div>
          </article>
        </div>

        <footer class="pdf-footer">
          <span>图表保留原始数据能力，结论用于交班复述</span>
          <span>第 {{ pageIndex + 4 }} 页</span>
        </footer>
      </section>

      <section class="pdf-page">
        <header class="pdf-page-header">
          <div>
            <p class="pdf-kicker">Disposition Priorities</p>
            <h2>P0 / P1 / P2 处置建议</h2>
          </div>
          <span>闭环执行页</span>
        </header>

        <div class="pdf-priority-grid">
          <article
            v-for="group in recommendationGroups"
            :key="group.title"
            class="pdf-priority-card"
            :data-tone="group.tone"
          >
            <header>
              <strong>{{ group.title }}</strong>
              <span>{{ group.items.length }} 条</span>
            </header>
            <ul v-if="group.items.length">
              <li v-for="item in group.items" :key="item">{{ item }}</li>
            </ul>
            <p v-else class="pdf-empty-note">当前无新增动作。</p>
          </article>
        </div>

        <section class="pdf-signoff-grid">
          <article>
            <span>交班人签名</span>
            <div></div>
          </article>
          <article>
            <span>接班人签名</span>
            <div></div>
          </article>
          <article>
            <span>复核时间</span>
            <div></div>
          </article>
        </section>

        <footer class="pdf-footer">
          <span>打印后可直接用于现场交班签核</span>
          <span>最终页</span>
        </footer>
      </section>
    </div>
  </div>
</template>

<style scoped>
.pdf-report-host {
  position: absolute;
  left: -100000px;
  top: 0;
  width: 210mm;
  pointer-events: none;
}

.pdf-report-container {
  width: 210mm;
  background: #eef2f7;
  color: #17212d;
  font-family: var(--font-main);
}

.pdf-page {
  width: 210mm;
  min-height: 297mm;
  box-sizing: border-box;
  padding: 14mm 14mm 12mm;
  background: #ffffff;
  display: grid;
  gap: 7mm;
  box-shadow: 0 0 0 1px rgba(15, 23, 42, 0.08);
  page-break-after: always;
}

.pdf-page:last-child {
  page-break-after: auto;
}

.pdf-page--cover {
  background:
    linear-gradient(180deg, rgba(236, 253, 245, 0.65), rgba(255, 255, 255, 0.96) 36%),
    linear-gradient(135deg, #f7fafc 0%, #ffffff 100%);
}

.pdf-kicker,
.pdf-section-label {
  margin: 0 0 3mm;
  font-size: 9px;
  letter-spacing: 0.26em;
  text-transform: uppercase;
  font-weight: 800;
  color: #0f766e;
}

.pdf-cover-header,
.pdf-page-header,
.pdf-cover-meta,
.pdf-cover-hero,
.pdf-cover-metrics,
.pdf-risk-layer,
.pdf-chart-grid,
.pdf-priority-grid,
.pdf-signoff-grid {
  display: grid;
  gap: 5mm;
}

.pdf-cover-header,
.pdf-page-header {
  grid-template-columns: 1fr auto;
  align-items: start;
}

.pdf-cover-header h1,
.pdf-page-header h2 {
  margin: 0;
  font-family: var(--font-display);
  color: #111827;
  letter-spacing: -0.04em;
}

.pdf-cover-header h1 {
  font-size: 28px;
}

.pdf-page-header h2 {
  font-size: 20px;
}

.pdf-cover-subtitle,
.pdf-summary-box p,
.pdf-page-header span {
  color: #4b5563;
}

.pdf-cover-badge {
  display: grid;
  gap: 2mm;
  padding: 4mm;
  min-width: 34mm;
  border-radius: 4mm;
  border: 1px solid #d1d5db;
  text-align: center;
}

.pdf-cover-badge span,
.pdf-cover-meta span,
.pdf-risk-card small,
.pdf-footer {
  font-size: 10px;
  color: #6b7280;
}

.pdf-cover-badge strong,
.pdf-cover-hero__main strong {
  color: #111827;
}

.pdf-cover-badge[data-tone="high"] {
  background: #fef2f2;
  border-color: #fca5a5;
}

.pdf-cover-badge[data-tone="attention"] {
  background: #fffbeb;
  border-color: #fcd34d;
}

.pdf-cover-badge[data-tone="stable"] {
  background: #ecfdf5;
  border-color: #86efac;
}

.pdf-cover-meta {
  grid-template-columns: repeat(4, 1fr);
}

.pdf-cover-meta article,
.pdf-cover-metrics article,
.pdf-signoff-grid article {
  display: grid;
  gap: 2mm;
}

.pdf-cover-meta strong,
.pdf-cover-metrics strong {
  font-size: 13px;
  color: #111827;
}

.pdf-cover-hero {
  grid-template-columns: 1.35fr 0.95fr;
  align-items: start;
}

.pdf-cover-hero__main,
.pdf-cover-hero__side,
.pdf-summary-box,
.pdf-timeline-item__body,
.pdf-priority-card {
  padding: 5mm;
  border-radius: 4mm;
  border: 1px solid #d7dde5;
  background: #fcfcfd;
}

.pdf-cover-hero__main strong {
  display: block;
  margin-bottom: 3mm;
  font-size: 18px;
  line-height: 1.6;
}

.pdf-cover-hero__main p,
.pdf-cover-hero__side ol,
.pdf-summary-box ul,
.pdf-timeline-item__body p,
.pdf-priority-card ul {
  margin: 0;
  line-height: 1.7;
  font-size: 12px;
  color: #1f2937;
}

.pdf-cover-hero__side ol,
.pdf-summary-box ul,
.pdf-priority-card ul {
  padding-left: 4.5mm;
}

.pdf-cover-metrics {
  grid-template-columns: repeat(3, 1fr);
}

.pdf-cover-metrics article {
  padding: 4mm;
  border-radius: 4mm;
  background: #f8fafc;
  border: 1px solid #e5e7eb;
}

.pdf-cover-metrics strong {
  font-size: 22px;
  font-weight: 800;
}

.pdf-risk-layer {
  grid-template-columns: repeat(3, 1fr);
}

.pdf-risk-column {
  display: grid;
  gap: 4mm;
  padding: 5mm;
  border-radius: 4mm;
  border: 1px solid #d7dde5;
}

.pdf-risk-column header,
.pdf-risk-card__head,
.pdf-risk-card__meta,
.pdf-timeline-item__head,
.pdf-timeline-item__meta,
.pdf-priority-card header,
.pdf-footer {
  display: flex;
  justify-content: space-between;
  gap: 3mm;
  align-items: flex-start;
}

.pdf-risk-column[data-tone="high"] {
  background: #fff7f7;
}

.pdf-risk-column[data-tone="medium"] {
  background: #fffaf0;
}

.pdf-risk-column[data-tone="low"] {
  background: #f3fbf7;
}

.pdf-risk-list,
.pdf-timeline,
.pdf-priority-card ul {
  display: grid;
  gap: 3.5mm;
}

.pdf-risk-card {
  display: grid;
  gap: 2mm;
  padding: 3.5mm;
  border-radius: 3.5mm;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid rgba(15, 23, 42, 0.08);
}

.pdf-risk-card__head strong,
.pdf-priority-card strong,
.pdf-timeline-item__head strong {
  font-size: 12px;
  color: #111827;
}

.pdf-risk-card__head span,
.pdf-priority-card header span {
  padding: 1.5mm 2.2mm;
  border-radius: 999px;
  background: #eef2ff;
  font-size: 9px;
  font-weight: 800;
  color: #1d4ed8;
}

.pdf-risk-card p,
.pdf-empty-note,
.pdf-priority-card p {
  margin: 0;
  font-size: 11px;
  line-height: 1.65;
  color: #374151;
}

.pdf-timeline {
  gap: 4mm;
}

.pdf-timeline-item {
  display: grid;
  grid-template-columns: 5mm 1fr;
  gap: 4mm;
}

.pdf-timeline-item__marker {
  margin-top: 4mm;
  width: 3mm;
  height: 3mm;
  border-radius: 999px;
}

.pdf-timeline-item[data-tone="high"] .pdf-timeline-item__marker {
  background: #dc2626;
}

.pdf-timeline-item[data-tone="medium"] .pdf-timeline-item__marker {
  background: #f59e0b;
}

.pdf-timeline-item[data-tone="low"] .pdf-timeline-item__marker {
  background: #16a34a;
}

.pdf-timeline-item__meta span {
  font-size: 10px;
  color: #6b7280;
}

.pdf-chart-grid {
  grid-template-columns: 1fr;
  align-content: start;
}

.pdf-chart-card {
  display: grid;
  gap: 3mm;
}

.pdf-chart-card__insight {
  padding: 4mm;
  border-radius: 4mm;
  border: 1px solid #dbeafe;
  background: #f8fbff;
}

.pdf-chart-card__insight span {
  display: inline-flex;
  margin-bottom: 2mm;
  padding: 1.3mm 2.2mm;
  border-radius: 999px;
  background: #dbeafe;
  color: #0c4a6e;
  font-size: 9px;
  font-weight: 800;
}

.pdf-chart-card__insight p {
  margin: 0;
  font-size: 11px;
  line-height: 1.65;
  color: #1f2937;
}

.pdf-priority-grid {
  grid-template-columns: repeat(3, 1fr);
}

.pdf-priority-card[data-tone="p0"] {
  background: #fff5f5;
  border-color: #fecaca;
}

.pdf-priority-card[data-tone="p1"] {
  background: #fffaf0;
  border-color: #fde68a;
}

.pdf-priority-card[data-tone="p2"] {
  background: #f3fbf7;
  border-color: #bbf7d0;
}

.pdf-signoff-grid {
  grid-template-columns: repeat(3, 1fr);
  margin-top: auto;
}

.pdf-signoff-grid div {
  min-height: 12mm;
  border-bottom: 1px solid #9ca3af;
}

.pdf-footer {
  margin-top: auto;
  padding-top: 3mm;
  border-top: 1px solid #e5e7eb;
}

@page {
  size: A4 portrait;
  margin: 0;
}

@media print {
  .pdf-report-host {
    position: static;
    width: auto;
  }

  .pdf-page {
    box-shadow: none;
  }
}
</style>
