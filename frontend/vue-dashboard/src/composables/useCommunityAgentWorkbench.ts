import { computed, ref, watch } from "vue";
import {
  ApiError,
  api,
  streamCommunityAnalysis,
  type AgentAnswerCompletedEvent,
  type AgentAttachment,
  type AgentCitation,
  type AgentElderSubject,
  type AgentProvider,
  type AgentStageEvent,
  type AgentStreamEvent,
  type AgentToolEvent,
  type AnalysisScope,
  type ChatCapabilities,
  type CommunityAnalysisPayload,
  type CommunityWorkflow,
  type DemoDataStatus,
  type WindowKind,
} from "../api/client";
import { getStoredSessionToken } from "./useSessionAuth";

const WORKBENCH_STORAGE_KEY = "community-agent-workbench-v5";

type WorkbenchSession = {
  id: string;
  question: string;
  startedAt: string;
  finalAnswer: string;
  selectedModel: string;
  workflow: CommunityWorkflow;
  status: "running" | "completed" | "error";
  scope: AnalysisScope;
  subjectLabel: string;
};

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
  attachments: AgentAttachment[];
  updatedAt: string;
};

type MessageTrace = {
  stages: StageRecord[];
  tools: ToolRecord[];
  citations: AgentCitation[];
  selectedModel: string;
  degradedNotes: string[];
  scope?: AnalysisScope | "device";
  window?: WindowKind;
  subject?: Record<string, unknown> | null;
};

type AgentMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  createdAt: string;
  workflow: CommunityWorkflow;
  attachments: AgentAttachment[];
  status: "streaming" | "completed" | "error";
  trace: MessageTrace | null;
};

type QuickAction = {
  workflow: CommunityWorkflow;
  label: string;
  prompt: string;
};

type PersistedState = {
  selectedWindow: WindowKind;
  selectedScope: AnalysisScope;
  selectedProvider: AgentProvider;
  selectedElderId: string;
};

function fallbackError(error: unknown): string {
  if (error instanceof ApiError) return error.detail;
  if (error instanceof Error) return error.message;
  return String(error);
}

function stageLabel(stage: string): string {
  return {
    scope_resolve: "分析对象识别",
    window_resolve: "分析窗口确认",
    data_load: "数据读取",
    model_analysis: "评分与异常分析",
    rag_retrieve: "知识检索与重排序",
    tool_loop: "工具结果整合",
    synthesis: "答案与建议生成",
    artifact_render: "图表与报告整理",
    session_persist: "会话收尾",
  }[stage] ?? stage;
}

function stageSummaryFallback(stage: string, status: StageRecord["status"]): string {
  if (status === "running") return "正在处理相关上下文。";
  return {
    scope_resolve: "已完成分析对象识别。",
    window_resolve: "已确认分析窗口。",
    data_load: "已完成窗口数据读取。",
    model_analysis: "已完成评分、异常检测与群体分析。",
    rag_retrieve: "已完成知识检索与重排序。",
    tool_loop: "已完成工具结果整合。",
    synthesis: "已生成初步结论。",
    artifact_render: "已整理图表与报告。",
    session_persist: "已完成本次会话收尾。",
  }[stage] ?? "当前步骤已完成。";
}

function workflowLabel(workflow: CommunityWorkflow): string {
  return {
    overview: "社区概览",
    risk_ranking: "高风险排序",
    alert_digest: "告警摘要",
    device_focus: "设备分析",
    elder_focus: "老人分析",
    community_report: "社区报告",
    elder_report: "老人报告",
    report_generation: "报告生成",
    free_chat: "自由问答",
  }[workflow];
}

function chunkText(text: string, size = 48): string[] {
  const chunks: string[] = [];
  for (let index = 0; index < text.length; index += size) {
    chunks.push(text.slice(index, index + size));
  }
  return chunks;
}

function normalizeAttachments(
  payload: {
    attachments?: AgentAttachment[];
    render_type?: AgentAttachment["render_type"];
    render_payload?: Record<string, unknown>;
    title?: string;
    summary?: string;
    tool_name?: string;
    request_id?: string;
  },
): AgentAttachment[] {
  if (Array.isArray(payload.attachments) && payload.attachments.length) return payload.attachments;
  if (!payload.render_type || !payload.render_payload) return [];
  return [
    {
      id: payload.request_id ?? `${payload.tool_name ?? "attachment"}-${Date.now()}`,
      title: payload.title ?? payload.tool_name ?? "结构化结果",
      summary: payload.summary,
      render_type: payload.render_type,
      render_payload: payload.render_payload,
      source_tool: payload.tool_name,
    },
  ];
}

function mergeAttachments(current: AgentAttachment[], incoming: AgentAttachment[]): AgentAttachment[] {
  const merged = [...current];
  const indexById = new Map(merged.map((item, index) => [item.id, index]));
  for (const attachment of incoming) {
    const index = indexById.get(attachment.id);
    if (index == null) {
      indexById.set(attachment.id, merged.length);
      merged.push(attachment);
      continue;
    }
    merged[index] = {
      ...merged[index],
      ...attachment,
      render_payload: {
        ...(merged[index].render_payload ?? {}),
        ...(attachment.render_payload ?? {}),
      },
    };
  }
  return merged;
}

function normalizeChildTools(raw: unknown): TraceChildTool[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((item): item is Record<string, unknown> => typeof item === "object" && item !== null)
    .map((item) => ({
      name: String(item.name ?? "child_tool"),
      title: String(item.title ?? item.name ?? "子工具"),
      summary: String(item.summary ?? ""),
      status: String(item.status ?? "completed"),
    }));
}

function safeReadState(): PersistedState | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(WORKBENCH_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<PersistedState>;
    return {
      selectedWindow: parsed.selectedWindow === "week" ? "week" : "day",
      selectedScope: parsed.selectedScope === "elder" ? "elder" : "community",
      selectedProvider:
        parsed.selectedProvider === "tongyi" || parsed.selectedProvider === "ollama" ? parsed.selectedProvider : "auto",
      selectedElderId: typeof parsed.selectedElderId === "string" ? parsed.selectedElderId : "",
    };
  } catch {
    return null;
  }
}

function safeWriteState(state: PersistedState) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(WORKBENCH_STORAGE_KEY, JSON.stringify(state));
}

export function useCommunityAgentWorkbench(deviceMacs: () => string[], selectedDeviceMac: () => string) {
  const restoredState = safeReadState();

  const sessions = ref<WorkbenchSession[]>([]);
  const messages = ref<AgentMessage[]>([]);
  const question = ref("");
  const selectedWindow = ref<WindowKind>(restoredState?.selectedWindow ?? "day");
  const selectedScope = ref<AnalysisScope>(restoredState?.selectedScope ?? "community");
  const selectedProvider = ref<AgentProvider>(restoredState?.selectedProvider ?? "auto");
  const selectedElderId = ref(restoredState?.selectedElderId ?? "");
  const elderSubjects = ref<AgentElderSubject[]>([]);
  const demoDataStatus = ref<DemoDataStatus | null>(null);
  const capabilities = ref<ChatCapabilities | null>(null);
  const citations = ref<AgentCitation[]>([]);
  const artifactIds = ref<string[]>([]);
  const running = ref(false);
  const loadingContext = ref(false);
  const refreshingSamples = ref(false);
  const errorText = ref("");
  const finalAnswer = ref("");
  const streamingAnswer = ref("");
  const currentSessionId = ref("");
  const activeRunId = ref("");
  const currentWorkflow = ref<CommunityWorkflow>("free_chat");
  const selectedModel = ref("");
  const degradedNotes = ref<string[]>([]);
  const stageRecords = ref<StageRecord[]>([]);
  const toolRecords = ref<ToolRecord[]>([]);
  const answerScope = ref<AnalysisScope | "device">("community");
  const answerWindow = ref<WindowKind>("day");
  const answerSubject = ref<Record<string, unknown> | null>(null);
  const abortController = ref<AbortController | null>(null);

  const selectedElder = computed(
    () => elderSubjects.value.find((item) => item.elder_id === selectedElderId.value) ?? null,
  );

  const selectedSubjectLabel = computed(() => {
    if (selectedScope.value === "community") return "整个社区";
    if (!selectedElder.value) return "未选择老人";
    return `${selectedElder.value.elder_name} / ${selectedElder.value.apartment}`;
  });

  const communitySamplesReady = computed(() => Boolean(demoDataStatus.value?.enabled && demoDataStatus.value.subject_count));

  const canAnalyze = computed(() => {
    if (selectedScope.value === "elder") return Boolean(selectedElder.value);
    return Boolean(deviceMacs().length || communitySamplesReady.value || elderSubjects.value.length);
  });

  const quickActions = computed<QuickAction[]>(() => {
    if (selectedScope.value === "elder") {
      return [
        {
          workflow: "elder_focus",
          label: "老人风险分析",
          prompt: "请围绕当前老人最近的体征变化、健康评分、异常信号和处置优先级进行分析。",
        },
        {
          workflow: "elder_report",
          label: "生成老人报告",
          prompt: "请生成当前老人对应分析窗口内的结构化健康分析报告，并给出跟进行动。",
        },
        {
          workflow: "alert_digest",
          label: "告警摘要",
          prompt: "请汇总当前老人分析窗口内的告警、异常趋势和需要回访的重点。",
        },
      ];
    }
    return [
      {
        workflow: "overview",
        label: "社区概览",
        prompt: "请总结当前社区分析窗口内的整体风险态势、设备状态和需要重点值守的方向。",
      },
      {
        workflow: "risk_ranking",
        label: "高风险排序",
        prompt: "请按优先级列出当前社区最需要关注的对象，并说明排序原因。",
      },
      {
        workflow: "community_report",
        label: "生成社区报告",
        prompt: "请生成当前社区分析窗口内的结构化运营分析报告，包括重点对象、告警热点和建议动作。",
      },
      {
        workflow: "alert_digest",
        label: "告警热点",
        prompt: "请总结当前社区分析窗口内的告警热点、趋势变化和建议处置顺序。",
      },
    ];
  });

  const providerSummary = computed(() => {
    const caps = capabilities.value;
    return {
      tongyiReady: Boolean(caps?.providers.tongyi.chat_configured),
      ollamaReady: Boolean(caps?.providers.ollama.configured),
      retrievalReady: Boolean(caps?.retrieval.vector_enabled || caps?.retrieval.bm25_enabled),
      rerankReady: Boolean(caps?.retrieval.rerank_enabled),
    };
  });

  const runtimeInfo = computed(() => ({
    selectedModel: selectedModel.value || "待选择",
    provider: selectedProvider.value,
    selectedScope: selectedScope.value,
    subjectLabel: selectedSubjectLabel.value,
    deviceCount: deviceMacs().length,
    elderCount: elderSubjects.value.length,
    communitySamplesReady: communitySamplesReady.value,
    demoStatus: demoDataStatus.value,
    degradedNotes: degradedNotes.value,
    capabilities: capabilities.value,
    providerSummary: providerSummary.value,
  }));

  watch(
    [selectedWindow, selectedScope, selectedProvider, selectedElderId],
    () => {
      safeWriteState({
        selectedWindow: selectedWindow.value,
        selectedScope: selectedScope.value,
        selectedProvider: selectedProvider.value,
        selectedElderId: selectedElderId.value,
      });
    },
    { deep: true },
  );

  watch(
    selectedScope,
    (scope) => {
      if (scope !== "elder") return;
      if (!selectedElderId.value && elderSubjects.value.length) {
        selectedElderId.value = elderSubjects.value[0].elder_id;
      }
    },
    { immediate: true },
  );

  async function loadContext() {
    const token = getStoredSessionToken();
    loadingContext.value = true;
    try {
      const subjectPromise = token
        ? api.getAgentElders(token).catch(() => [] as AgentElderSubject[])
        : Promise.resolve([] as AgentElderSubject[]);
      const [subjects, sampleStatus, capabilityReport] = await Promise.all([
        subjectPromise,
        api.getDemoDataStatus().catch(() => null),
        api.getChatCapabilities().catch(() => null),
      ]);
      elderSubjects.value = subjects;
      demoDataStatus.value = sampleStatus;
      capabilities.value = capabilityReport;
      if (selectedScope.value === "elder" && !selectedElderId.value && subjects.length) {
        selectedElderId.value = subjects[0].elder_id;
      }
    } finally {
      loadingContext.value = false;
    }
  }

  void loadContext();

  function updateMessage(messageId: string, updater: (message: AgentMessage) => AgentMessage) {
    if (!messageId) return;
    messages.value = messages.value.map((item) => (item.id === messageId ? updater(item) : item));
  }

  function setMessageText(messageId: string, text: string) {
    updateMessage(messageId, (message) => ({ ...message, text }));
  }

  function setMessageStatus(messageId: string, status: AgentMessage["status"]) {
    updateMessage(messageId, (message) => ({ ...message, status }));
  }

  function mergeMessageAttachments(messageId: string, attachments: AgentAttachment[]) {
    if (!attachments.length) return;
    updateMessage(messageId, (message) => ({
      ...message,
      attachments: mergeAttachments(message.attachments, attachments),
    }));
  }

  function currentAssistantMessageId() {
    return activeRunId.value ? `${activeRunId.value}-assistant` : "";
  }

  function createEmptyTrace(): MessageTrace {
    return {
      stages: [],
      tools: [],
      citations: [],
      selectedModel: "",
      degradedNotes: [],
      scope: selectedScope.value,
      window: selectedWindow.value,
      subject: null,
    };
  }

  function updateMessageTrace(messageId: string, updater: (trace: MessageTrace) => MessageTrace) {
    updateMessage(messageId, (message) => ({
      ...message,
      trace: updater(message.trace ?? createEmptyTrace()),
    }));
  }

  function createConversationSeed(prompt: string, workflow: CommunityWorkflow) {
    const timestamp = new Date().toISOString();
    const runId = activeRunId.value;
    messages.value = [
      ...messages.value,
      {
        id: `${runId}-user`,
        role: "user",
        text: prompt,
        createdAt: timestamp,
        workflow,
        attachments: [],
        status: "completed",
        trace: null,
      },
      {
        id: currentAssistantMessageId(),
        role: "assistant",
        text: "",
        createdAt: timestamp,
        workflow,
        attachments: [],
        status: "streaming",
        trace: createEmptyTrace(),
      },
    ];
  }

  function syncTraceMeta() {
    updateMessageTrace(currentAssistantMessageId(), (trace) => ({
      ...trace,
      selectedModel: selectedModel.value || trace.selectedModel,
      degradedNotes: degradedNotes.value.length ? [...degradedNotes.value] : trace.degradedNotes,
      scope: answerScope.value,
      window: answerWindow.value,
      subject: answerSubject.value,
    }));
  }

  function updateStage(event: AgentStageEvent) {
    const next: StageRecord = {
      stage: event.stage,
      label: event.label ?? stageLabel(event.stage),
      detail: event.detail ?? event.summary ?? stageSummaryFallback(event.stage, event.status),
      summary: event.summary ?? event.detail ?? stageSummaryFallback(event.stage, event.status),
      status: event.status,
      updatedAt: event.timestamp ?? new Date().toISOString(),
      elapsedMs: event.elapsed_ms ?? null,
      group: event.group ?? "trace",
    };
    const existing = stageRecords.value.find((item) => item.stage === event.stage);
    if (existing) {
      Object.assign(existing, next);
      stageRecords.value = [...stageRecords.value];
    } else {
      stageRecords.value = [...stageRecords.value, next];
    }
    updateMessageTrace(currentAssistantMessageId(), (trace) => {
      const stages = [...trace.stages];
      const index = stages.findIndex((item) => item.stage === next.stage);
      if (index >= 0) stages[index] = next;
      else stages.push(next);
      return { ...trace, stages };
    });
  }

  function normalizeToolEvent(event: AgentToolEvent, existing?: ToolRecord): ToolRecord {
    const attachments = normalizeAttachments({
      attachments: event.attachments,
      render_type: event.render_type,
      render_payload: event.render_payload,
      title: event.title,
      summary: event.summary,
      tool_name: event.tool_name,
      request_id: event.request_id,
    });
    return {
      requestId: event.request_id,
      toolName: event.tool_name,
      title: event.title ?? existing?.title ?? event.tool_name,
      toolKind: event.tool_kind ?? existing?.toolKind ?? "analysis",
      source: event.source ?? existing?.source ?? "internal_tool",
      status: event.status ?? (event.type === "tool.started" ? "running" : "completed"),
      success: event.success ?? existing?.success ?? (event.type === "tool.finished" ? true : null),
      summary: event.summary ?? event.error_message ?? existing?.summary ?? "",
      inputPreview: event.input_preview ?? existing?.inputPreview ?? "",
      outputPreview: event.output_preview ?? existing?.outputPreview ?? "",
      childTools: normalizeChildTools(event.child_tools ?? existing?.childTools ?? []),
      attachments: mergeAttachments(existing?.attachments ?? [], attachments),
      updatedAt: event.timestamp ?? new Date().toISOString(),
    };
  }

  function updateTool(event: AgentToolEvent) {
    const existing = toolRecords.value.find((item) => item.requestId === event.request_id);
    const nextRecord = normalizeToolEvent(event, existing);
    toolRecords.value = [
      ...toolRecords.value.filter((item) => item.requestId !== nextRecord.requestId),
      nextRecord,
    ];
    updateMessageTrace(currentAssistantMessageId(), (trace) => {
      const tools = [...trace.tools.filter((item) => item.requestId !== nextRecord.requestId), nextRecord];
      return { ...trace, tools };
    });
    mergeMessageAttachments(currentAssistantMessageId(), nextRecord.attachments);
  }

  function resetRunState() {
    errorText.value = "";
    finalAnswer.value = "";
    streamingAnswer.value = "";
    citations.value = [];
    artifactIds.value = [];
    answerScope.value = selectedScope.value;
    answerWindow.value = selectedWindow.value;
    answerSubject.value = null;
    stageRecords.value = [];
    toolRecords.value = [];
    degradedNotes.value = [];
    selectedModel.value = "";
    currentSessionId.value = "";
  }

  function clearConversationState() {
    closeCurrentRun();
    sessions.value = [];
    messages.value = [];
    question.value = "";
    resetRunState();
    safeWriteState({
      selectedWindow: selectedWindow.value,
      selectedScope: selectedScope.value,
      selectedProvider: selectedProvider.value,
      selectedElderId: selectedElderId.value,
    });
  }

  clearConversationState();

  function appendSession(status: WorkbenchSession["status"]) {
    const sessionId = currentSessionId.value || activeRunId.value;
    if (!sessionId) return;
    sessions.value = [
      {
        id: sessionId,
        question: question.value.trim() || finalAnswer.value || "社区智能体分析",
        startedAt: new Date().toISOString(),
        finalAnswer: finalAnswer.value,
        selectedModel: selectedModel.value || selectedProvider.value,
        workflow: currentWorkflow.value,
        status,
        scope: selectedScope.value,
        subjectLabel: selectedSubjectLabel.value,
      },
      ...sessions.value.filter((item) => item.id !== sessionId),
    ].slice(0, 12);
  }

  function closeCurrentRun() {
    abortController.value?.abort();
    abortController.value = null;
    running.value = false;
  }

  function handleCompletedAnswer(event: AgentAnswerCompletedEvent) {
    finalAnswer.value = event.answer;
    streamingAnswer.value = event.answer;
    citations.value = event.citations ?? [];
    artifactIds.value = event.artifact_ids ?? [];
    answerScope.value = event.scope ?? selectedScope.value;
    answerWindow.value = event.window ?? selectedWindow.value;
    answerSubject.value = event.subject ?? null;
    setMessageText(currentAssistantMessageId(), event.answer);
    setMessageStatus(currentAssistantMessageId(), "completed");
    mergeMessageAttachments(currentAssistantMessageId(), event.attachments ?? []);
    updateMessageTrace(currentAssistantMessageId(), (trace) => ({
      ...trace,
      citations: event.citations ?? trace.citations,
      scope: event.scope ?? trace.scope,
      window: event.window ?? trace.window,
      subject: event.subject ?? trace.subject,
    }));
  }

  function handleEvent(event: AgentStreamEvent) {
    switch (event.type) {
      case "session.started":
        currentSessionId.value = event.session_id;
        selectedModel.value = event.selected_model ?? selectedModel.value;
        degradedNotes.value = event.degraded_notes ?? degradedNotes.value;
        syncTraceMeta();
        break;
      case "stage.changed":
        updateStage(event);
        break;
      case "tool.started":
      case "tool.finished":
        updateTool(event);
        break;
      case "answer.delta":
        streamingAnswer.value += event.delta;
        setMessageText(currentAssistantMessageId(), streamingAnswer.value);
        break;
      case "answer.completed":
        handleCompletedAnswer(event);
        break;
      case "session.completed":
        selectedModel.value = event.selected_model ?? selectedModel.value;
        degradedNotes.value = event.degraded_notes ?? degradedNotes.value;
        running.value = false;
        setMessageStatus(currentAssistantMessageId(), "completed");
        syncTraceMeta();
        appendSession("completed");
        break;
      case "session.error":
        errorText.value = event.error;
        running.value = false;
        setMessageStatus(currentAssistantMessageId(), "error");
        setMessageText(currentAssistantMessageId(), `分析失败：${event.error}`);
        appendSession("error");
        break;
      case "trace.note":
        break;
    }
  }

  async function runFallback(payload: CommunityAnalysisPayload) {
    updateStage({
      type: "stage.changed",
      stage: "synthesis",
      status: "running",
      label: "答案与建议生成",
      detail: "已切换到同步结果整理模式。",
      summary: "已切换到同步结果整理模式。",
      timestamp: new Date().toISOString(),
      elapsed_ms: null,
      group: "trace",
    });
    const result = await api.analyzeCommunity(payload);
    for (const chunk of chunkText(result.answer ?? "")) {
      handleEvent({
        type: "answer.delta",
        session_id: currentSessionId.value || activeRunId.value,
        delta: chunk,
        timestamp: new Date().toISOString(),
      });
    }
    handleEvent({
      type: "answer.completed",
      session_id: currentSessionId.value || activeRunId.value,
      answer: result.answer ?? "",
      references: result.references,
      analysis: result.analysis,
      attachments: result.attachments,
      citations: result.citations,
      artifact_ids: result.artifact_ids,
      scope: result.scope === "device" ? "elder" : result.scope,
      window: result.window,
      subject: result.subject ?? null,
      timestamp: new Date().toISOString(),
    });
    handleEvent({
      type: "session.completed",
      session_id: currentSessionId.value || activeRunId.value,
      selected_model: result.selected_model ?? selectedModel.value ?? selectedProvider.value,
      degraded_notes: Array.isArray(result.degraded) ? result.degraded : ["stream_endpoint_fallback_to_sync"],
      timestamp: new Date().toISOString(),
    });
  }

  function buildHistoryPayload() {
    return messages.value
      .slice(-8)
      .map((item) => ({ role: item.role, content: item.text.trim() }))
      .filter((item) => item.content.length > 0);
  }

  function buildPayload(prompt: string, workflow: CommunityWorkflow): CommunityAnalysisPayload {
    const focusDevice = selectedDeviceMac() || deviceMacs()[0] || "";
    const elderDeviceMacs = selectedElder.value?.device_macs ?? (focusDevice ? [focusDevice] : []);
    return {
      question: prompt,
      role: "community",
      mode: selectedProvider.value,
      history_minutes: selectedWindow.value === "week" ? 7 * 24 * 60 : 24 * 60,
      per_device_limit: selectedWindow.value === "week" ? 360 : 180,
      device_macs: selectedScope.value === "elder" ? elderDeviceMacs : deviceMacs(),
      workflow,
      focus_device_mac: focusDevice || undefined,
      history: buildHistoryPayload(),
      scope: selectedScope.value,
      subject_elder_id: selectedScope.value === "elder" ? selectedElderId.value : null,
      window: selectedWindow.value,
      provider: selectedProvider.value,
      include_report:
        workflow === "community_report" || workflow === "elder_report" || workflow === "report_generation",
    };
  }

  async function submit(workflow: CommunityWorkflow = "free_chat", presetQuestion?: string) {
    if (!canAnalyze.value) {
      errorText.value =
        selectedScope.value === "elder" ? "请先选择要分析的老人。" : "当前还没有可用于分析的社区样本。";
      return;
    }

    const prompt = (presetQuestion ?? question.value).trim() || quickActions.value[0]?.prompt;
    if (!prompt) {
      errorText.value = "请输入问题后再开始分析。";
      return;
    }

    closeCurrentRun();
    resetRunState();
    running.value = true;
    currentWorkflow.value = workflow;
    activeRunId.value = `frontend-${Date.now()}`;
    abortController.value = new AbortController();
    question.value = prompt;
    const payload = buildPayload(prompt, workflow);
    createConversationSeed(prompt, workflow);

    try {
      await streamCommunityAnalysis(payload, {
        signal: abortController.value.signal,
        onEvent: handleEvent,
      });
    } catch (error) {
      if (abortController.value?.signal.aborted) {
        errorText.value = "本次分析已取消。";
        running.value = false;
        setMessageStatus(currentAssistantMessageId(), "error");
        setMessageText(currentAssistantMessageId(), "本次分析已取消。");
        appendSession("error");
        return;
      }
      try {
        await runFallback(payload);
      } catch (fallbackErrorValue) {
        errorText.value = fallbackError(fallbackErrorValue || error);
        running.value = false;
        setMessageStatus(currentAssistantMessageId(), "error");
        setMessageText(currentAssistantMessageId(), `分析失败：${errorText.value}`);
        appendSession("error");
      }
    } finally {
      abortController.value = null;
    }
  }

  async function refreshCommunitySamples() {
    refreshingSamples.value = true;
    try {
      await api.refreshDemoData().catch(() => null);
      await loadContext();
    } finally {
      refreshingSamples.value = false;
    }
  }

  return {
    answerScope,
    answerSubject,
    answerWindow,
    artifactIds,
    capabilities,
    canAnalyze,
    cancel: closeCurrentRun,
    citations,
    currentWorkflow,
    degradedNotes,
    demoDataStatus,
    elderSubjects,
    errorText,
    loadContext,
    loadingContext,
    messages,
    question,
    quickActions,
    refreshCommunitySamples,
    refreshingSamples,
    running,
    runtimeInfo,
    selectedElder,
    selectedElderId,
    selectedModel,
    selectedProvider,
    selectedScope,
    selectedSubjectLabel,
    selectedWindow,
    sessions,
    stageRecords,
    submit,
    toolRecords,
    workflowLabel,
    clearConversationState,
  };
}
