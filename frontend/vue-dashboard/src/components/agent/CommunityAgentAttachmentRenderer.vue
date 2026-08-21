<script setup lang="ts">
import { computed } from "vue";
import type { AgentAttachment } from "../../api/client";
import AgentChartAttachment from "./AgentChartAttachment.vue";
import AgentMarkdownContent from "./AgentMarkdownContent.vue";

type TableColumn = {
  key: string;
  label: string;
};

type PrimitiveCell = string | number | boolean | null;

type ReportSection = {
  id: string;
  title: string;
  content: string;
};

const props = defineProps<{
  attachments: AgentAttachment[];
}>();

function normalizeCards(payload: Record<string, unknown>) {
  const items = Array.isArray(payload.cards)
    ? payload.cards
    : Array.isArray(payload.items)
      ? payload.items
      : [];

  return items
    .filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
    .map((item, index) => ({
      id: String(item.id ?? `${index}`),
      label: String(item.label ?? `指标 ${index + 1}`),
      value: item.value == null ? "--" : String(item.value),
      caption: item.caption == null ? "" : String(item.caption),
      tone: item.tone == null ? "default" : String(item.tone),
    }));
}

function normalizeColumns(payload: Record<string, unknown>): TableColumn[] {
  const rawColumns = Array.isArray(payload.columns) ? payload.columns : [];
  return rawColumns
    .map((column, index) => {
      if (typeof column === "string") {
        return { key: column, label: column };
      }

      if (typeof column === "object" && column !== null) {
        const record = column as Record<string, unknown>;
        return {
          key: String(record.key ?? `column_${index}`),
          label: String(record.label ?? record.key ?? `列 ${index + 1}`),
        };
      }

      return null;
    })
    .filter((item): item is TableColumn => item !== null);
}

function normalizeRows(payload: Record<string, unknown>, columns: TableColumn[]) {
  const rawRows = Array.isArray(payload.rows) ? payload.rows : [];
  return rawRows
    .filter((row): row is Record<string, PrimitiveCell> => typeof row === "object" && row !== null)
    .map((row) =>
      columns.reduce<Record<string, string>>((accumulator, column) => {
        const value = row[column.key];
        accumulator[column.key] = value == null ? "--" : String(value);
        return accumulator;
      }, {}),
    );
}

function normalizeCharts(payload: Record<string, unknown>) {
  const charts = Array.isArray(payload.charts)
    ? payload.charts
    : payload.chart && typeof payload.chart === "object"
      ? [payload.chart]
      : payload.echarts_option && typeof payload.echarts_option === "object"
        ? [
            {
              id: payload.id ?? "chart",
              title: payload.title ?? "图表",
              summary: payload.summary,
              echarts_option: payload.echarts_option,
            },
          ]
        : [];

  return charts
    .filter((chart): chart is Record<string, unknown> => typeof chart === "object" && chart !== null)
    .map((chart, index) => ({
      id: String(chart.id ?? `chart_${index}`),
      title: String(chart.title ?? `图表 ${index + 1}`),
      summary: chart.summary == null ? "" : String(chart.summary),
      echarts_option: (chart.echarts_option ?? {}) as Record<string, unknown>,
    }));
}

function normalizeSections(payload: Record<string, unknown>): ReportSection[] {
  const rawSections = Array.isArray(payload.sections) ? payload.sections : [];
  return rawSections
    .filter((section): section is Record<string, unknown> => typeof section === "object" && section !== null)
    .map((section, index) => ({
      id: String(section.id ?? `section_${index}`),
      title: String(section.title ?? `Section ${index + 1}`),
      content: String(section.content ?? "").trim(),
    }))
    .filter((section) => section.content.length > 0);
}

function normalizeDocumentMarkdown(payload: Record<string, unknown>): string {
  if (typeof payload.markdown === "string") return payload.markdown.trim();
  if (typeof payload.content === "string") return payload.content.trim();
  if (typeof payload.body === "string") return payload.body.trim();
  return "";
}

function isStreamingReportDocument(summary?: string): boolean {
  // 后端流式阶段会把 summary 设为：报告已生成第 {index}/{total} 个章节。
  // 此时渲染整篇 documentMarkdown 会导致每次更新都做全量 markdown-it 重排，
  // 视觉上更像“不流式/抖动”。按章节 sections 逐块展示会更顺滑。
  if (!summary) return false;
  return /报告已生成第\s*\d+\s*\/\s*\d+\s*个章节/.test(summary);
}

const preparedAttachments = computed(() =>
  props.attachments.map((attachment) => {
    const payload = attachment.render_payload ?? {};
    const columns = normalizeColumns(payload);

    return {
      ...attachment,
      cards: normalizeCards(payload),
      columns,
      rows: normalizeRows(payload, columns),
      charts: normalizeCharts(payload),
      documentTitle: String(payload.document_title ?? attachment.title),
      documentMarkdown: normalizeDocumentMarkdown(payload),
      sections: normalizeSections(payload),
    };
  }),
);
</script>

<template>
  <div v-if="preparedAttachments.length" class="agent-attachment-stack">
    <article
      v-for="attachment in preparedAttachments"
      :key="attachment.id"
      class="agent-attachment"
      :data-type="attachment.render_type"
    >
      <header
        v-if="attachment.render_type !== 'report_document'"
        class="agent-attachment__head"
      >
        <div>
          <h3>{{ attachment.title }}</h3>
          <p v-if="attachment.summary">{{ attachment.summary }}</p>
        </div>
        <span v-if="attachment.source_tool" class="summary-badge">{{ attachment.source_tool }}</span>
      </header>

      <div v-if="attachment.render_type === 'metric_cards'" class="agent-attachment__metric-grid">
        <article
          v-for="card in attachment.cards"
          :key="card.id"
          class="agent-metric-card"
          :data-tone="card.tone"
        >
          <span>{{ card.label }}</span>
          <strong>{{ card.value }}</strong>
          <small v-if="card.caption">{{ card.caption }}</small>
        </article>
      </div>

      <div v-else-if="attachment.render_type === 'table'" class="agent-table-wrap">
        <table>
          <thead>
            <tr>
              <th v-for="column in attachment.columns" :key="column.key">{{ column.label }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, index) in attachment.rows" :key="`${attachment.id}-${index}`">
              <td v-for="column in attachment.columns" :key="column.key">{{ row[column.key] }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-else-if="attachment.render_type === 'echarts'" class="agent-chart-grid">
        <AgentChartAttachment
          v-for="chart in attachment.charts"
          :key="chart.id"
          :chart="chart"
        />
      </div>

      <section v-else-if="attachment.render_type === 'report_document'" class="agent-report">
        <header class="agent-report__head">
          <div class="agent-report__eyebrow">分析报告</div>
          <h4>{{ attachment.documentTitle }}</h4>
          <p v-if="attachment.summary" class="agent-report__summary">{{ attachment.summary }}</p>
        </header>

        <div
          v-if="attachment.documentMarkdown && attachment.sections.length === 0 && !isStreamingReportDocument(attachment.summary)"
          class="agent-report__body"
        >
          <AgentMarkdownContent :content="attachment.documentMarkdown" variant="report" />
        </div>

        <div v-else class="agent-report__sections">
          <article
            v-for="(section, sectionIndex) in attachment.sections"
            :key="section.id"
            class="agent-report__section"
          >
            <header class="agent-report__section-head">
              <span class="agent-report__section-index">{{ String(sectionIndex + 1).padStart(2, '0') }}</span>
              <h5>{{ section.title }}</h5>
            </header>
            <AgentMarkdownContent :content="section.content" variant="report" />
          </article>
        </div>
      </section>
    </article>
  </div>
</template>

<style scoped>
.agent-attachment-stack,
.agent-attachment,
.agent-chart-grid,
.agent-report,
.agent-report__body,
.agent-report__sections {
  display: grid;
  gap: 14px;
}

.agent-attachment {
  padding: 18px;
  border-radius: 24px;
  background: #ffffff;
  border: 1px solid var(--line-medium);
  box-shadow: 0 8px 30px rgba(15, 23, 42, 0.05);
}

.agent-attachment__head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.agent-attachment__head h3,
.agent-report__head h4,
.agent-report__section h5 {
  margin: 0;
  color: var(--text-main);
}

.agent-attachment__head h3 {
  font-size: 1.3rem;
  font-weight: 700;
}

.agent-attachment__head p,
.agent-report__summary {
  margin: 6px 0 0;
  color: var(--text-sub);
  line-height: 1.7;
  font-size: 1.02rem;
}

.agent-attachment__metric-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
}

.agent-metric-card {
  display: grid;
  gap: 8px;
  padding: 16px;
  border-radius: 18px;
  background: #f8fafc;
  border: 1px solid var(--line-medium);
  text-align: center;
  justify-items: center;
}

.agent-metric-card span {
  color: var(--text-sub);
  font-size: 1.05rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.agent-metric-card strong {
  color: var(--text-main);
  font-size: 1.75rem;
  font-weight: 700;
  line-height: 1.2;
}

.agent-metric-card small {
  color: var(--text-sub);
  font-size: 0.92rem;
}

.agent-metric-card[data-tone="high"] strong,
.agent-metric-card[data-tone="critical"] strong,
.agent-metric-card[data-tone="danger"] strong {
  color: #f87171;
}

.agent-metric-card[data-tone="accent"] strong,
.agent-metric-card[data-tone="active"] strong {
  color: #34d399;
}

.agent-metric-card[data-tone="warning"] strong {
  color: #fb923c;
}

.agent-table-wrap {
  overflow: auto;
  border-radius: 18px;
  border: 1px solid var(--line-medium);
  background: #ffffff;
}

.agent-table-wrap table {
  min-width: 100%;
  border-collapse: collapse;
  font-size: 1.08rem;
}

.agent-table-wrap th {
  padding: 14px 18px;
  text-align: left;
  white-space: nowrap;
  color: var(--text-sub);
  font-size: 0.98rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  background: #f8fafc;
  border-bottom: 1px solid var(--line-medium);
}

.agent-table-wrap td {
  padding: 13px 18px;
  white-space: nowrap;
  color: var(--text-main);
  font-size: 1.02rem;
  border-bottom: 1px solid var(--line-default);
  min-width: 80px;
}

.agent-table-wrap tr:last-child td {
  border-bottom: none;
}

.agent-table-wrap tr:hover td {
  background: #f1f5f9;
}

.agent-report {
  gap: 20px;
  padding: 4px;
}

.agent-report__head {
  display: grid;
  gap: 10px;
  padding: 12px 4px 4px;
  border-bottom: 1px solid var(--line-medium);
  margin-bottom: 4px;
}

.agent-report__eyebrow {
  color: var(--brand);
  font-size: 0.72rem;
  font-weight: 800;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.agent-report__head h4 {
  font-size: 1.75rem;
  letter-spacing: -0.03em;
  font-weight: 700;
  color: var(--text-main);
  margin: 0;
  line-height: 1.2;
}

.agent-report__summary {
  margin: 4px 0 0;
  color: var(--text-sub);
  font-size: 1.08rem;
  line-height: 1.7;
}

.agent-report__sections {
  display: grid;
  gap: 16px;
}

.agent-report__section {
  display: grid;
  gap: 14px;
  padding: 22px 24px;
  border-radius: 22px;
  background: #ffffff;
  border: 1px solid var(--line-medium);
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.04);
}

.agent-report__section-head {
  display: flex;
  gap: 12px;
  align-items: center;
  padding-bottom: 10px;
  border-bottom: 1px solid var(--line-medium);
}

.agent-report__section-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.9rem;
  height: 1.9rem;
  border-radius: 999px;
  background: #f1f5f9;
  border: 1px solid var(--line-medium);
  color: var(--text-main);
  font-size: 0.82rem;
  font-weight: 700;
  letter-spacing: 0.06em;
}

.agent-report__section h5 {
  font-size: 1.35rem;
  letter-spacing: -0.01em;
  font-weight: 700;
  color: var(--text-main);
  margin: 0;
}

@media (max-width: 760px) {
  .agent-attachment__head {
    flex-direction: column;
  }
}
</style>
