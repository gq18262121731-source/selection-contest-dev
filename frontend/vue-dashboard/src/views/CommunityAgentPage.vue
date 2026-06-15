<script setup lang="ts">
import { Bot, RefreshCw, SendHorizontal, Sparkles, Square } from "lucide-vue-next";
import { computed, toRef, watch } from "vue";
import type { SessionUser } from "../api/client";
import AgentMarkdownContent from "../components/agent/AgentMarkdownContent.vue";
import AgentTracePanel from "../components/agent/AgentTracePanel.vue";
import CommunityAgentAttachmentRenderer from "../components/agent/CommunityAgentAttachmentRenderer.vue";
import PageHeader from "../components/layout/PageHeader.vue";
import { useCommunityAgentWorkbench } from "../composables/useCommunityAgentWorkbench";
import { useCommunityWorkspace } from "../composables/useCommunityWorkspace";

const props = defineProps<{
  sessionUser: SessionUser;
  /**
   * Trigger refresh behavior when user re-clicks the nav entry,
   * even if the route/hash doesn't change.
   */
  refreshKey?: number;
}>();

const workspace = useCommunityWorkspace(toRef(props, "sessionUser"));
const workbench = useCommunityAgentWorkbench(
  () => workspace.deviceStatuses.value.map((item) => item.device_mac),
  () => workspace.selectedDeviceMac.value,
);

watch(
  () => props.refreshKey,
  (key, prev) => {
    if (key == null) return;
    // Ignore the first run after mount; this page already initializes a clean state.
    if (prev == null) return;
    workbench.clearConversationState();
    void workbench.loadContext();
  },
);

const headerBadges = computed(() => [
  workbench.selectedSubjectLabel.value,
  workbench.selectedWindow.value === "week" ? "过去一周" : "过去一天",
  `模型 ${workbench.selectedProvider.value}`,
]);

const sampleStatusText = computed(() => {
  if (workbench.demoDataStatus.value?.enabled && workbench.demoDataStatus.value.subject_count) {
    return `社区样本已准备 ${workbench.demoDataStatus.value.subject_count} 位对象`;
  }
  return "社区样本等待刷新";
});

const quickSuggestions = computed(() => workbench.quickActions.value.slice(0, 4));

function submitFreeChat() {
  void workbench.submit("free_chat");
}
</script>

<template>
  <section class="agent-page">
    <PageHeader
      eyebrow="社区智能体"
      title="社区智能体工作台"
      description="围绕单个老人或整个社区，直接发起真实分析、图表整理、报告生成和综合建议。"
      :meta="headerBadges"
    />

    <section class="agent-shell">
      <div class="agent-controls">
          <div class="agent-toggle-group">
            <button
              type="button"
              class="agent-toggle"
              :class="{ 'agent-toggle--active': workbench.selectedScope.value === 'elder' }"
              @click="workbench.selectedScope.value = 'elder'"
            >
              某位老人
            </button>
            <button
              type="button"
              class="agent-toggle"
              :class="{ 'agent-toggle--active': workbench.selectedScope.value === 'community' }"
              @click="workbench.selectedScope.value = 'community'"
            >
              整个社区
            </button>
          </div>

          <div class="agent-toggle-group">
            <button
              type="button"
              class="agent-toggle"
              :class="{ 'agent-toggle--active': workbench.selectedWindow.value === 'day' }"
              @click="workbench.selectedWindow.value = 'day'"
            >
              过去一天
            </button>
            <button
              type="button"
              class="agent-toggle"
              :class="{ 'agent-toggle--active': workbench.selectedWindow.value === 'week' }"
              @click="workbench.selectedWindow.value = 'week'"
            >
              过去一周
            </button>
          </div>

          <label v-if="workbench.selectedScope.value === 'elder'" class="agent-select agent-select--wide">
            <span>分析对象</span>
            <select v-model="workbench.selectedElderId.value">
              <option
                v-for="subject in workbench.elderSubjects.value"
                :key="subject.elder_id"
                :value="subject.elder_id"
              >
                {{ subject.elder_name }} / {{ subject.apartment }}
              </option>
            </select>
          </label>

          <label class="agent-select">
            <span>分析模型</span>
            <select v-model="workbench.selectedProvider.value">
              <option value="auto">自动</option>
              <option value="tongyi">Tongyi</option>
              <option value="ollama">Ollama</option>
            </select>
          </label>

          <button
            type="button"
            class="ghost-btn"
            :disabled="workbench.refreshingSamples.value"
            @click="workbench.refreshCommunitySamples"
          >
            <RefreshCw :size="15" />
            {{ workbench.refreshingSamples.value ? "刷新中..." : "刷新社区样本" }}
          </button>
        </div>

      <div class="agent-chat-surface">
        <div class="agent-chat-surface__head">
          <div class="agent-badge-row">
            <span v-for="badge in headerBadges" :key="badge" class="summary-badge">{{ badge }}</span>
          </div>
          <span class="agent-sample-status">{{ sampleStatusText }}</span>
        </div>

        <p v-if="workbench.errorText.value" class="feedback-banner feedback-error">
          {{ workbench.errorText.value }}
        </p>

        <div class="agent-message-list">
          <div v-if="!workbench.messages.value.length" class="agent-empty-state">
            <div class="agent-empty-state__icon">
              <Sparkles :size="20" />
            </div>
            <h2>像真正的大模型一样，直接发起一次分析</h2>
            <p>选好分析对象和时间窗口后输入问题。执行过程、工具调用、图表和报告都会在同一条回答里展开。</p>
            <div class="agent-empty-state__actions">
              <button
                v-for="action in quickSuggestions"
                :key="action.workflow"
                type="button"
                class="agent-suggestion-chip"
                @click="workbench.submit(action.workflow, action.prompt)"
              >
                {{ action.label }}
              </button>
            </div>
          </div>

          <article
            v-for="message in workbench.messages.value"
            :key="message.id"
            class="agent-message"
            :class="`agent-message--${message.role}`"
          >
            <div class="agent-message__meta">
              <div class="agent-message__author">
                <span class="agent-message__avatar">
                  <Bot v-if="message.role === 'assistant'" :size="16" />
                  <span v-else>我</span>
                </span>
                <strong>{{ message.role === "assistant" ? "社区智能体" : "我" }}</strong>
              </div>
              <span>{{ workbench.workflowLabel(message.workflow) }}</span>
            </div>

            <AgentTracePanel
              v-if="message.role === 'assistant' && message.trace"
              :stages="message.trace.stages"
              :tools="message.trace.tools"
              :citations="message.trace.citations"
              :selected-model="message.trace.selectedModel"
              :degraded-notes="message.trace.degradedNotes"
              :streaming="message.status === 'streaming'"
            />

            <CommunityAgentAttachmentRenderer
              v-if="message.role === 'assistant' && message.attachments.length"
              :attachments="message.attachments"
            />

            <div
              v-if="message.role === 'user' || message.text || message.status !== 'completed'"
              class="agent-message__bubble"
              :data-role="message.role"
              :data-status="message.status"
            >
              <AgentMarkdownContent
                v-if="message.role === 'assistant' && message.text"
                :content="message.text"
                variant="bubble"
                :streaming="message.status === 'streaming'"
              />
              <p v-else>{{ message.text || (message.role === "assistant" ? "正在整理结果..." : "") }}</p>
            </div>
          </article>
        </div>
        
        <!-- 添加底部间距，为固定的输入框留出空间 -->
        <div class="agent-chat-spacer"></div>
      </div>
    </section>

    <!-- 将输入框放在页面内容区域，不再固定 -->
    <footer class="agent-composer">
      <div class="agent-composer__quick">
        <button
          v-for="action in quickSuggestions"
          :key="action.workflow"
          type="button"
          class="agent-quick-pill"
          @click="workbench.submit(action.workflow, action.prompt)"
        >
          <Sparkles :size="14" />
          {{ action.label }}
        </button>
      </div>

      <label class="agent-composer__field">
        <textarea
          v-model="workbench.question.value"
          rows="3"
          :placeholder="
            workbench.selectedScope.value === 'elder'
              ? '例如：请分析这位老人过去一周的风险变化、异常原因和建议动作。'
              : '例如：请总结社区过去一天的高风险对象、告警热点和排班建议。'
          "
        />
      </label>

      <div class="agent-composer__footer">
        <div class="agent-badge-row">
          <span v-for="badge in headerBadges" :key="`footer-${badge}`" class="summary-badge">{{ badge }}</span>
        </div>

        <div class="agent-composer__actions">
          <button 
            type="button" 
            class="agent-stop-btn" 
            :class="{ 'agent-stop-btn--active': workbench.running.value }"
            :disabled="!workbench.running.value" 
            @click="workbench.cancel"
          >
            <Square :size="15" />
            停止
          </button>
          <button
            type="button"
            class="agent-start-btn"
            :class="{ 'agent-start-btn--running': workbench.running.value }"
            :disabled="workbench.running.value || !workbench.canAnalyze.value"
            @click="submitFreeChat"
          >
            <SendHorizontal :size="16" />
            {{ workbench.running.value ? "分析中..." : "开始分析" }}
          </button>
        </div>
      </div>
    </footer>
  </section>
</template>

<style scoped>
.agent-page,
.agent-shell,
.agent-chat-surface,
.agent-message-list {
  display: grid;
  gap: 24px;
}

.agent-page {
  min-height: calc(100vh - 48px);
  align-content: start;
  padding-bottom: 40px;
  max-width: 100%;
  overflow-x: hidden;
}

.agent-shell {
  display: grid;
  grid-template-columns: 1fr;
  gap: 24px;
  padding: 32px;
  border-radius: 24px;
  background: #ffffff;
  border: 2px solid #e2e8f0;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
}

.agent-controls {
  display: flex;
  flex-direction: column;
  gap: 16px;
  align-items: stretch;
}

.agent-toggle-group {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  border-radius: 16px;
  padding: 6px;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border: 2px solid #e2e8f0;
}

.agent-toggle {
  border: none;
  min-width: 140px;
  border-radius: 12px;
  padding: 14px 24px;
  background: transparent;
  color: #64748b;
  font-weight: 600;
  font-size: 0.95rem;
  cursor: pointer;
  transition: all 200ms ease;
  white-space: nowrap;
}

.agent-toggle:hover {
  background: rgba(255, 255, 255, 0.6);
  color: #475569;
}

.agent-toggle--active {
  background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
  color: #1e40af;
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08);
  font-weight: 700;
}

.agent-select {
  min-width: 240px;
  display: grid;
  gap: 10px;
}

.agent-select--wide {
  min-width: min(420px, 100%);
}

.agent-select span {
  color: #475569;
  font-size: 0.9rem;
  font-weight: 600;
}

.agent-select select {
  width: 100%;
  min-height: 52px;
  padding: 0 18px;
  border-radius: 12px;
  border: 2px solid #cbd5e1;
  background: #ffffff;
  color: #0f172a;
  font-size: 0.95rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 200ms ease;
}

.agent-select select:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.ghost-btn {
  padding: 12px 20px;
  border-radius: 12px;
  border: 2px solid #cbd5e1;
  background: #ffffff;
  color: #475569;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 200ms ease;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.ghost-btn:hover:not(:disabled) {
  border-color: #3b82f6;
  color: #1e40af;
  background: #eff6ff;
  transform: translateY(-1px);
}

.ghost-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.agent-chat-surface {
  padding: 12px 4px 0;
  min-height: 50vh;
  display: grid;
  gap: 24px;
}

.agent-chat-surface__head {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  align-items: center;
  padding-bottom: 16px;
  border-bottom: 2px solid #e2e8f0;
}

.agent-badge-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.summary-badge {
  padding: 10px 18px;
  border-radius: 999px;
  background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%);
  color: #1e40af;
  font-size: 0.85rem;
  font-weight: 700;
  border: 2px solid #3b82f6;
  white-space: nowrap;
  box-shadow: 0 2px 6px rgba(59, 130, 246, 0.15);
}

.agent-sample-status {
  color: #64748b;
  font-size: 0.9rem;
  font-weight: 500;
}

.feedback-banner {
  padding: 18px 24px;
  border-radius: 16px;
  font-size: 0.95rem;
  margin: 0;
}

.feedback-error {
  background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
  color: #991b1b;
  border: 2px solid #fca5a5;
}

.agent-message-list {
  padding-top: 8px;
}

.agent-chat-spacer {
  height: 0;
}

.agent-empty-state {
  min-height: 400px;
  display: grid;
  place-content: center;
  gap: 20px;
  text-align: center;
  padding: 40px 20px;
}

.agent-empty-state__icon {
  width: 72px;
  height: 72px;
  margin: 0 auto;
  border-radius: 20px;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%);
  color: #1e40af;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.2);
}

.agent-empty-state h2 {
  margin: 0;
  color: #0f172a;
  font-size: clamp(1.5rem, 2.1vw, 2rem);
  font-weight: 700;
}

.agent-empty-state p {
  margin: 0;
  color: #64748b;
  max-width: 600px;
  line-height: 1.8;
  font-size: 1rem;
}

.agent-empty-state__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  justify-content: center;
  margin-top: 12px;
}

.agent-suggestion-chip {
  border: 2px solid #cbd5e1;
  border-radius: 999px;
  padding: 12px 20px;
  background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
  color: #475569;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  transition: all 200ms ease;
  font-weight: 600;
  font-size: 0.9rem;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
}

.agent-suggestion-chip:hover {
  transform: translateY(-2px);
  border-color: #3b82f6;
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
  color: #1e40af;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.15);
}

.agent-message {
  display: grid;
  gap: 16px;
  max-width: 100%;
}

.agent-message--user {
  justify-self: end;
}

.agent-message__meta {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  color: #64748b;
  font-size: 0.9rem;
  font-weight: 500;
}

.agent-message__author {
  display: flex;
  align-items: center;
  gap: 12px;
}

.agent-message__author strong {
  color: #0f172a;
  font-weight: 700;
}

.agent-message__avatar {
  width: 36px;
  height: 36px;
  border-radius: 999px;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, #f1f5f9 0%, #e2e8f0 100%);
  color: #475569;
  font-size: 0.85rem;
  font-weight: 700;
  border: 2px solid #cbd5e1;
}

.agent-message__bubble {
  padding: 24px 28px;
  border-radius: 20px;
  border: 2px solid #e2e8f0;
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.06);
}

.agent-message__bubble[data-role="assistant"] {
  background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
}

.agent-message__bubble[data-role="assistant"][data-status="streaming"] {
  border-color: #3b82f6;
  box-shadow: 0 4px 16px rgba(59, 130, 246, 0.15);
}

.agent-message__bubble[data-role="user"] {
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
  color: #1e40af;
  border-color: #3b82f6;
  box-shadow: 0 4px 16px rgba(59, 130, 246, 0.15);
}

.agent-message__bubble p {
  margin: 0;
  white-space: pre-wrap;
  line-height: 1.8;
  font-size: 1rem;
}

/* 输入框样式 - 不再固定 */
.agent-composer {
  display: grid;
  gap: 14px;
  padding: 20px;
  margin-top: 24px;
  border-radius: 20px;
  border: 2px solid #e2e8f0;
  background: #ffffff;
  box-shadow: 0 4px 16px rgba(15, 23, 42, 0.08);
}

.agent-quick-pill {
  border: 2px solid #cbd5e1;
  border-radius: 999px;
  padding: 10px 16px;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  color: #64748b;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  transition: all 200ms ease;
  font-weight: 600;
  font-size: 0.85rem;
}

.agent-quick-pill:hover {
  transform: translateY(-1px);
  border-color: #3b82f6;
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
  color: #1e40af;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.15);
}

.agent-composer__field textarea {
  width: 100%;
  min-height: 120px;
  max-height: min(32vh, 300px);
  resize: vertical;
  border-radius: 16px;
  border: 2px solid #cbd5e1;
  background: #ffffff;
  color: #0f172a;
  padding: 16px 20px;
  font: inherit;
  line-height: 1.7;
  font-size: 0.95rem;
  box-shadow: inset 0 2px 8px rgba(15, 23, 42, 0.04);
  transition: all 200ms ease;
}

.agent-composer__field textarea:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1), inset 0 2px 8px rgba(15, 23, 42, 0.04);
}

.agent-composer__footer {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  align-items: center;
}

.agent-composer__actions {
  display: flex;
  gap: 12px;
}

.agent-composer__quick {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

/* 美化停止按钮 */
.agent-stop-btn {
  min-width: 110px;
  height: 52px;
  border: 2px solid #e2e8f0;
  border-radius: 16px;
  padding: 0 24px;
  background: #ffffff;
  color: #64748b;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  cursor: pointer;
  transition: all 200ms ease;
  font-size: 0.95rem;
}

.agent-stop-btn:hover:not(:disabled) {
  border-color: #f87171;
  background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
  color: #dc2626;
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(248, 113, 113, 0.25);
}

.agent-stop-btn--active {
  border-color: #f87171;
  background: linear-gradient(135deg, #fee2e2 0%, #fecaca 100%);
  color: #dc2626;
  animation: pulse-stop 2s infinite;
}

.agent-stop-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  transform: none;
}

/* 美化开始分析按钮 */
.agent-start-btn {
  min-width: 160px;
  height: 52px;
  border: none;
  border-radius: 16px;
  padding: 0 28px;
  background: linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%);
  color: #ffffff;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  cursor: pointer;
  transition: all 200ms ease;
  font-size: 0.95rem;
  box-shadow: 0 6px 16px rgba(59, 130, 246, 0.35);
}

.agent-start-btn:hover:not(:disabled) {
  background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%);
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(59, 130, 246, 0.45);
}

.agent-start-btn--running {
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
  animation: pulse-running 2s infinite;
}

.agent-start-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.2);
}

/* 动画效果 */
@keyframes pulse-stop {
  0%, 100% {
    box-shadow: 0 6px 16px rgba(248, 113, 113, 0.25);
  }
  50% {
    box-shadow: 0 8px 24px rgba(248, 113, 113, 0.4);
  }
}

@keyframes pulse-running {
  0%, 100% {
    box-shadow: 0 6px 16px rgba(16, 185, 129, 0.35);
  }
  50% {
    box-shadow: 0 8px 24px rgba(16, 185, 129, 0.5);
  }
}

@media (max-width: 980px) {
  .agent-shell {
    padding: 24px;
  }

  .agent-controls {
    flex-direction: row;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
  }

  .agent-chat-surface__head,
  .agent-composer__footer {
    flex-direction: column;
    align-items: stretch;
  }

  .agent-message {
    max-width: 100%;
  }

  .agent-message--user {
    justify-self: stretch;
  }

  .agent-select,
  .agent-select--wide {
    min-width: 100%;
  }

  .agent-composer__actions {
    width: 100%;
    justify-content: stretch;
  }

  .agent-stop-btn,
  .agent-start-btn {
    flex: 1;
  }
}
</style>
