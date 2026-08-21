<script setup lang="ts">
import { computed, ref } from "vue";
import type { AgentCitation } from "../../api/client";

type StageRecord = {
  stage: string;
  label: string;
  detail: string;
  summary: string;
  status: "running" | "completed" | "error";
  updatedAt: string;
  elapsedMs: number | null;
  group: string;
};

type TraceChildTool = {
  name: string;
  title: string;
  summary: string;
  status: string;
};

type ToolRecord = {
  requestId: string;
  toolName: string;
  title: string;
  toolKind: "data_query" | "analysis" | "report" | "recommendation";
  source: string;
  status: string;
  success: boolean | null;
  summary: string;
  inputPreview: string;
  outputPreview: string;
  childTools: TraceChildTool[];
  updatedAt: string;
};

const props = withDefaults(
  defineProps<{
    stages: StageRecord[];
    tools: ToolRecord[];
    citations: AgentCitation[];
    selectedModel?: string;
    degradedNotes?: string[];
    streaming?: boolean;
  }>(),
  {
    selectedModel: "",
    degradedNotes: () => [],
    streaming: false,
  },
);

const detailsOpen = ref(false);

function handleToggle(event: Event) {
  detailsOpen.value = (event.target as HTMLDetailsElement).open;
}

function stageTone(status: StageRecord["status"]) {
  if (status === "error") return "error";
  if (status === "running") return "running";
  return "completed";
}

function toolTone(kind: ToolRecord["toolKind"]) {
  return {
    data_query: "query",
    analysis: "analysis",
    report: "report",
    recommendation: "recommendation",
  }[kind];
}

const runningStageCount = computed(() => props.stages.filter((item) => item.status === "running").length);
const runningToolCount = computed(() => props.tools.filter((item) => item.status === "running").length);
const latestRunningTool = computed(() => [...props.tools].reverse().find((item) => item.status === "running"));
const latestRunningStage = computed(() => [...props.stages].reverse().find((item) => item.status === "running"));

const summaryTitle = computed(() => {
  if (latestRunningTool.value) return `正在调用 ${latestRunningTool.value.title}`;
  if (latestRunningStage.value) return `正在${latestRunningStage.value.label}`;
  if (props.streaming) return "正在生成回答";
  if (props.tools.length > 0 || props.stages.length > 0) return "执行过程已完成";
  if (props.selectedModel?.trim()) return `当前模型 ${props.selectedModel}`;
  return "查看执行过程";
});

const summaryText = computed(() => {
  if (latestRunningTool.value) {
    return latestRunningTool.value.summary || latestRunningTool.value.toolName;
  }

  if (latestRunningStage.value) {
    return latestRunningStage.value.summary || latestRunningStage.value.detail;
  }

  if (props.streaming) {
    return "回答内容会继续实时流式输出";
  }

  if (props.tools.length > 0) {
    return `共完成 ${props.tools.length} 个工具调用，详情默认折叠`;
  }

  if (props.stages.length > 0) {
    return `共记录 ${props.stages.length} 个执行阶段`;
  }

  if (props.selectedModel?.trim()) {
    return "点击展开查看完整执行细节";
  }

  return "点击展开查看完整步骤";
});

const summaryMeta = computed(() => {
  if (runningToolCount.value > 0) return `${runningToolCount.value} 个工具运行中`;
  if (runningStageCount.value > 0) return `${runningStageCount.value} 个阶段进行中`;
  if (props.tools.length > 0) return `${props.tools.length} 个工具`;
  if (props.stages.length > 0) return `${props.stages.length} 个阶段`;
  if (props.citations.length > 0) return `${props.citations.length} 条来源`;
  return "";
});
</script>

<template>
  <details
    v-if="stages.length || tools.length || citations.length || degradedNotes.length"
    class="agent-trace"
    :data-streaming="streaming ? 'true' : 'false'"
    :open="detailsOpen"
    @toggle="handleToggle"
  >
    <summary class="agent-trace__summary">
      <span class="agent-trace__spark">AI</span>
      <div class="agent-trace__summary-copy">
        <strong>{{ summaryTitle }}</strong>
        <span>{{ summaryText }}</span>
      </div>
      <small v-if="summaryMeta" class="agent-trace__summary-tag">{{ summaryMeta }}</small>
      <span class="agent-trace__caret" :data-open="detailsOpen">></span>
    </summary>

    <div class="agent-trace__body">
      <section v-if="stages.length" class="agent-trace__section">
        <header>
          <h4>关键阶段</h4>
          <span>{{ stages.length }} steps</span>
        </header>
        <div class="agent-stage-list">
          <article
            v-for="stage in stages"
            :key="stage.stage"
            class="agent-stage-card"
            :data-tone="stageTone(stage.status)"
          >
            <div class="agent-stage-card__head">
              <strong>{{ stage.label }}</strong>
              <span>{{ stage.elapsedMs != null ? `${stage.elapsedMs} ms` : stage.status }}</span>
            </div>
            <p>{{ stage.summary || stage.detail }}</p>
          </article>
        </div>
      </section>

      <section v-if="tools.length" class="agent-trace__section">
        <header>
          <h4>工具调用</h4>
          <span>{{ tools.length }} tools</span>
        </header>
        <div class="agent-tool-list">
          <article
            v-for="tool in tools"
            :key="tool.requestId"
            class="agent-tool-card"
            :data-kind="toolTone(tool.toolKind)"
          >
            <div class="agent-tool-card__head">
              <div class="agent-tool-card__title">
                <strong>{{ tool.title }}</strong>
                <span>{{ tool.toolName }}</span>
              </div>
              <em>{{ tool.status }}</em>
            </div>
            <p>{{ tool.summary }}</p>

            <details
              v-if="tool.inputPreview || tool.outputPreview || tool.childTools.length"
              class="agent-tool-card__details"
            >
              <summary>查看结果</summary>
              <dl v-if="tool.inputPreview || tool.outputPreview" class="agent-tool-card__meta">
                <div v-if="tool.inputPreview">
                  <dt>输入</dt>
                  <dd>{{ tool.inputPreview }}</dd>
                </div>
                <div v-if="tool.outputPreview">
                  <dt>输出</dt>
                  <dd>{{ tool.outputPreview }}</dd>
                </div>
              </dl>

              <div v-if="tool.childTools.length" class="agent-tool-card__children">
                <span>内部步骤</span>
                <ul>
                  <li v-for="child in tool.childTools" :key="`${tool.requestId}-${child.name}`">
                    <strong>{{ child.title }}</strong>
                    <span>{{ child.summary }}</span>
                  </li>
                </ul>
              </div>
            </details>
          </article>
        </div>
      </section>

      <section v-if="citations.length" class="agent-trace__section">
        <header>
          <h4>证据来源</h4>
          <span>{{ citations.length }} citations</span>
        </header>
        <div class="agent-citation-list">
          <article v-for="citation in citations.slice(0, 4)" :key="citation.id" class="agent-citation-card">
            <strong>{{ citation.title }}</strong>
            <p>{{ citation.snippet }}</p>
            <span>{{ citation.source_path }}</span>
          </article>
        </div>
      </section>

      <section v-if="degradedNotes.length" class="agent-trace__section">
        <header>
          <h4>运行提示</h4>
        </header>
        <ul class="agent-degraded-list">
          <li v-for="note in degradedNotes" :key="note">{{ note }}</li>
        </ul>
      </section>
    </div>
  </details>
</template>

<style scoped>
.agent-trace {
  border-radius: 22px;
  background: #ffffff;
  border: 1px solid var(--line-medium);
  overflow: hidden;
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.04);
}

.agent-trace[data-streaming="true"] {
  border-color: rgba(37, 99, 235, 0.26);
  box-shadow: 0 10px 24px rgba(37, 99, 235, 0.08);
}

.agent-trace__summary {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  cursor: pointer;
  list-style: none;
}

.agent-trace__summary::-webkit-details-marker {
  display: none;
}

.agent-trace__spark {
  width: 32px;
  height: 32px;
  border-radius: 999px;
  display: grid;
  place-items: center;
  color: var(--brand);
  background: linear-gradient(135deg, #eff6ff, #f8fafc);
  font-size: 0.76rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  flex-shrink: 0;
}

.agent-trace[data-streaming="true"] .agent-trace__spark {
  animation: trace-pulse 1.6s ease-in-out infinite;
}

.agent-trace__summary-copy {
  flex: 1;
  min-width: 0;
  display: grid;
  gap: 2px;
}

.agent-trace__summary-copy strong {
  color: var(--text-main);
  line-height: 1.35;
}

.agent-trace__summary-copy span {
  color: var(--text-sub);
  font-size: 0.84rem;
  line-height: 1.45;
}

.agent-trace__summary-tag {
  flex-shrink: 0;
  padding: 6px 10px;
  border-radius: 999px;
  background: #f8fafc;
  border: 1px solid var(--line-medium);
  color: var(--text-sub);
  font-size: 0.74rem;
  font-weight: 700;
}

.agent-trace__caret {
  color: var(--text-sub);
  font-size: 0.94rem;
  transition: transform 180ms ease;
  flex-shrink: 0;
}

.agent-trace__caret[data-open="true"] {
  transform: rotate(90deg);
}

.agent-trace__body,
.agent-stage-list,
.agent-tool-list,
.agent-citation-list {
  display: grid;
  gap: 14px;
}

.agent-trace__body {
  padding: 0 18px 18px;
}

.agent-trace__section {
  display: grid;
  gap: 12px;
}

.agent-trace__section header {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
}

.agent-trace__section h4 {
  margin: 0;
  color: var(--text-main);
  font-size: 0.96rem;
}

.agent-trace__section header span {
  color: var(--text-sub);
  font-size: 0.8rem;
}

.agent-stage-card,
.agent-tool-card,
.agent-citation-card {
  padding: 14px 16px;
  border-radius: 18px;
  background: #f8fafc;
  border: 1px solid var(--line-medium);
}

.agent-stage-card__head,
.agent-tool-card__head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.agent-stage-card strong,
.agent-tool-card strong,
.agent-citation-card strong {
  color: var(--text-main);
}

.agent-stage-card p,
.agent-tool-card p,
.agent-citation-card p {
  margin: 8px 0 0;
  color: var(--text-sub);
  line-height: 1.7;
  font-size: 0.88rem;
}

.agent-stage-card__head span,
.agent-tool-card__head em,
.agent-tool-card__head span,
.agent-citation-card span {
  color: #64748b;
  font-size: 0.8rem;
  font-style: normal;
}

.agent-stage-card[data-tone="running"] {
  border-color: var(--brand);
  background: #ffffff;
}

.agent-stage-card[data-tone="error"] {
  border-color: #f87171;
  background: #fef2f2;
}

.agent-tool-card__title {
  display: grid;
  gap: 3px;
}

.agent-tool-card__details {
  margin-top: 12px;
  border-top: 1px solid var(--line-medium);
  padding-top: 12px;
}

.agent-tool-card__details summary {
  cursor: pointer;
  color: var(--brand);
  font-size: 0.84rem;
  font-weight: 600;
}

.agent-tool-card__meta {
  display: grid;
  gap: 8px;
  margin: 12px 0 0;
}

.agent-tool-card__meta div {
  display: grid;
  gap: 2px;
}

.agent-tool-card__meta dt {
  color: var(--text-sub);
  font-size: 0.78rem;
}

.agent-tool-card__meta dd {
  margin: 0;
  color: var(--text-main);
  font-size: 0.85rem;
}

.agent-tool-card__children {
  display: grid;
  gap: 8px;
  margin-top: 12px;
}

.agent-tool-card__children > span {
  color: var(--text-sub);
  font-size: 0.78rem;
}

.agent-tool-card__children ul,
.agent-degraded-list {
  margin: 0;
  padding-left: 18px;
  color: var(--text-main);
  display: grid;
  gap: 6px;
}

.agent-tool-card__children li {
  display: grid;
  gap: 2px;
}

.agent-citation-list {
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}

.agent-tool-card[data-kind="query"] {
  border-color: rgba(56, 189, 248, 0.4);
}

.agent-tool-card[data-kind="analysis"] {
  border-color: rgba(52, 211, 153, 0.4);
}

.agent-tool-card[data-kind="report"] {
  border-color: rgba(251, 146, 60, 0.4);
}

.agent-tool-card[data-kind="recommendation"] {
  border-color: rgba(167, 139, 250, 0.4);
}

@keyframes trace-pulse {
  0%,
  100% {
    transform: scale(1);
    box-shadow: 0 0 0 0 rgba(37, 99, 235, 0.16);
  }

  50% {
    transform: scale(1.04);
    box-shadow: 0 0 0 8px rgba(37, 99, 235, 0);
  }
}

@media (max-width: 760px) {
  .agent-trace__summary {
    align-items: flex-start;
    flex-wrap: wrap;
  }

  .agent-trace__summary-tag {
    order: 3;
  }
}
</style>
