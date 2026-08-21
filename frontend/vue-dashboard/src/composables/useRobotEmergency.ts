import { computed, onBeforeUnmount, ref } from "vue";
import { ApiError } from "../api/client";
import {
  robotEmergencyApi,
  validateEmergencyBundle,
  validateEmergencyCase,
} from "../api/robotEmergencyApi";
import { RobotContractError } from "../api/robotContractPolicy";
import { robotNavigationApi } from "../api/robotNavigationApi";
import type {
  RobotAlarmExtension,
  RobotConnectionState,
  RobotContractIssue,
  RobotDialogueIntent,
  RobotDialogueTurn,
  RobotEmergencyCase,
  RobotEmergencyIncidentBundle,
  RobotSafetyInterlock,
  RobotStatusEvent,
} from "../types/robot";
import {
  canResolveEmergencyReturn,
  emergencyAlarmStorageKey,
  getMockDialogueFixture,
  isValidRobotEmergencyIncidentId,
} from "../utils/robotEmergencyPolicy";

export type EmergencyOperation =
  | "acknowledge"
  | "dispatch"
  | "resume"
  | "start-dialogue"
  | "dialogue-result"
  | "resolve-return"
  | "complete-return";

export type EmergencyOperationFeedback = {
  kind: "success" | "error";
  message: string;
  code?: string;
  blockedBy?: string[];
};

function requestId(prefix: string): string {
  const suffix = typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${suffix}`;
}

function readBootstrapAlarm(incidentId: string): RobotAlarmExtension | null {
  try {
    const raw = window.sessionStorage.getItem(emergencyAlarmStorageKey(incidentId));
    if (!raw) return null;
    const value = JSON.parse(raw) as RobotAlarmExtension;
    return value.incident_id === incidentId ? value : null;
  } catch {
    return null;
  }
}

function errorFeedback(error: unknown): EmergencyOperationFeedback {
  if (error instanceof ApiError) {
    const blockedBy = Array.isArray(error.data?.blocked_by)
      ? error.data.blocked_by.filter((item): item is string => typeof item === "string")
      : undefined;
    return {
      kind: "error",
      message: error.detail,
      code: error.code ?? `HTTP_${error.status}`,
      blockedBy,
    };
  }
  if (error instanceof RobotContractError) {
    return { kind: "error", message: error.message, code: error.code };
  }
  return {
    kind: "error",
    message: error instanceof Error ? error.message : "应急操作失败",
    code: "ROBOT_EMERGENCY_OPERATION_FAILED",
  };
}

export function useRobotEmergency(incidentId: string | null, adminId: string) {
  const validIncidentId = isValidRobotEmergencyIncidentId(incidentId) ? incidentId : null;
  const bundle = ref<RobotEmergencyIncidentBundle | null>(null);
  const dialogueTurns = ref<RobotDialogueTurn[]>([]);
  const safetyInterlock = ref<RobotSafetyInterlock | null>(null);
  const bootstrapAlarm = ref<RobotAlarmExtension | null>(
    validIncidentId ? readBootstrapAlarm(validIncidentId) : null,
  );
  const loading = ref(false);
  const refreshing = ref(false);
  const notFound = ref(false);
  const loadError = ref<EmergencyOperationFeedback | null>(null);
  const operationFeedback = ref<EmergencyOperationFeedback | null>(null);
  const activeOperation = ref<EmergencyOperation | null>(null);
  const contractIssue = ref<RobotContractIssue | null>(null);
  const connectionState = ref<RobotConnectionState>("idle");
  const lastUpdatedAt = ref<string | null>(null);
  const liveEvents = ref<RobotStatusEvent[]>([]);
  let loadController: AbortController | null = null;
  let operationController: AbortController | null = null;
  let refreshTimer: number | null = null;

  const emergencyCase = computed(() => bundle.value?.emergency_case ?? null);
  const mockContractSafe = computed(
    () => !contractIssue.value
      && (!bundle.value || (
        bundle.value.provider === "mock"
        && bundle.value.real_motion_enabled === false
        && bundle.value.emergency_case.provider === "mock"
        && bundle.value.emergency_case.real_motion_enabled === false
      )),
  );
  const returnEvaluation = computed(() =>
    canResolveEmergencyReturn(emergencyCase.value, safetyInterlock.value),
  );
  const operationsDisabled = computed(
    () => !validIncidentId || !mockContractSafe.value || Boolean(activeOperation.value),
  );

  function applyBundle(next: RobotEmergencyIncidentBundle) {
    bundle.value = next;
    dialogueTurns.value = next.dialogue_turns;
    notFound.value = false;
    lastUpdatedAt.value = next.emergency_case.updated_at;
  }

  function applyCase(next: RobotEmergencyCase) {
    if (!bundle.value) return;
    bundle.value = {
      ...bundle.value,
      emergency_case: next,
      robot_task_id: next.robot_task_id,
    };
    lastUpdatedAt.value = next.updated_at;
  }

  function registerContractError(error: RobotContractError) {
    contractIssue.value = {
      code: error.code,
      message: error.message,
      endpoint: error.endpoint,
    };
    operationFeedback.value = errorFeedback(error);
    connectionState.value = "error";
  }

  async function refresh(options: { initial?: boolean } = {}) {
    if (!validIncidentId || contractIssue.value) return;
    loadController?.abort();
    const controller = new AbortController();
    loadController = controller;
    if (options.initial) loading.value = true;
    else refreshing.value = true;
    loadError.value = null;
    try {
      const [caseResult, dialogueResult, navigationResult] = await Promise.allSettled([
        robotEmergencyApi.getEmergencyCase(validIncidentId, controller.signal),
        robotEmergencyApi.getEmergencyDialogue(validIncidentId, controller.signal),
        robotNavigationApi.getNavigationState(controller.signal),
      ]);
      if (caseResult.status === "rejected") throw caseResult.reason;
      applyBundle(caseResult.value.data);
      if (dialogueResult.status === "fulfilled") {
        dialogueTurns.value = dialogueResult.value.data;
        if (bundle.value) bundle.value = { ...bundle.value, dialogue_turns: dialogueResult.value.data };
      } else if (dialogueResult.reason instanceof RobotContractError) {
        throw dialogueResult.reason;
      } else if (!(dialogueResult.reason instanceof DOMException && dialogueResult.reason.name === "AbortError")) {
        loadError.value = errorFeedback(dialogueResult.reason);
      }
      if (navigationResult.status === "fulfilled") {
        safetyInterlock.value = navigationResult.value.data.safety_interlock ?? null;
      } else if (navigationResult.reason instanceof RobotContractError) {
        throw navigationResult.reason;
      } else if (!(navigationResult.reason instanceof DOMException && navigationResult.reason.name === "AbortError")) {
        loadError.value = errorFeedback(navigationResult.reason);
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return;
      if (error instanceof RobotContractError) {
        registerContractError(error);
        return;
      }
      if (error instanceof ApiError && error.status === 404) {
        notFound.value = true;
        bundle.value = null;
        dialogueTurns.value = [];
      } else {
        loadError.value = errorFeedback(error);
      }
    } finally {
      if (loadController === controller) loadController = null;
      loading.value = false;
      refreshing.value = false;
    }
  }

  async function runOperation(
    operation: EmergencyOperation,
    execute: (signal: AbortSignal) => Promise<unknown>,
    successMessage: string,
  ) {
    if (!validIncidentId || operationsDisabled.value) return false;
    activeOperation.value = operation;
    operationFeedback.value = null;
    operationController?.abort();
    const controller = new AbortController();
    operationController = controller;
    try {
      await execute(controller.signal);
      operationFeedback.value = { kind: "success", message: successMessage };
      await refresh();
      return true;
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return false;
      if (error instanceof RobotContractError) registerContractError(error);
      else operationFeedback.value = errorFeedback(error);
      return false;
    } finally {
      if (operationController === controller) operationController = null;
      activeOperation.value = null;
    }
  }

  function acknowledge() {
    if (!validIncidentId) return Promise.resolve(false);
    return runOperation(
      "acknowledge",
      (signal) => robotEmergencyApi.acknowledgeEmergency(
        validIncidentId,
        { request_id: requestId("emergency-ack"), admin_id: adminId },
        signal,
      ),
      "已记录管理员知晓；告警和机器人任务均未自动解除。",
    );
  }

  function dispatch() {
    if (!validIncidentId) return Promise.resolve(false);
    const source = emergencyCase.value ?? bootstrapAlarm.value;
    const areaId = source?.area_id?.trim();
    const areaName = source?.area_name?.trim();
    if (!areaId || !areaName) {
      operationFeedback.value = {
        kind: "error",
        code: "AREA_MAPPING_NOT_FOUND",
        message: "缺少 area_id 或 area_name，无法创建机器人应急任务，请人工处置。",
      };
      return Promise.resolve(false);
    }
    return runOperation(
      "dispatch",
      (signal) => robotEmergencyApi.dispatchEmergency(
        validIncidentId,
        {
          request_id: requestId("emergency-dispatch"),
          area_id: areaId,
          area_name: areaName,
          alarm_id: source?.alarm_id ?? undefined,
          camera_id: source?.camera_id ?? undefined,
          risk_level: source?.risk_level ?? "critical",
          fall_probability: source?.fall_probability ?? undefined,
        },
        signal,
      ),
      "Mock 机器人应急任务已派发，真实运动保持禁用。",
    );
  }

  function resume() {
    if (!validIncidentId) return Promise.resolve(false);
    return runOperation(
      "resume",
      (signal) => robotEmergencyApi.resumeEmergency(
        validIncidentId,
        requestId("emergency-resume"),
        signal,
      ),
      "已通过后端重新执行安全联锁并请求继续 Mock 导航。",
    );
  }

  function startDialogue() {
    if (!validIncidentId) return Promise.resolve(false);
    return runOperation(
      "start-dialogue",
      (signal) => robotEmergencyApi.startMockDialogue(
        validIncidentId,
        {
          request_id: requestId("mock-dialogue-start"),
          mock_prompt_text: "您还好吗？需要帮助吗？",
        },
        signal,
      ),
      "已由后端推进至 Mock 等待回应状态；未生成或播放真实音频。",
    );
  }

  function submitDialogueResult(intent: RobotDialogueIntent) {
    if (!validIncidentId) return Promise.resolve(false);
    const fixture = getMockDialogueFixture(intent);
    const turnId = requestId(`mock-dialogue-${intent}`);
    return runOperation(
      "dialogue-result",
      (signal) => robotEmergencyApi.escalateEmergency(
        validIncidentId,
        {
          request_id: turnId,
          turn_id: turnId,
          intent,
          input_text: fixture.input,
          confidence: fixture.confidence,
        },
        signal,
      ),
      intent === "safe_response"
        ? "已记录安全回应，等待管理员确认；机器人保持原地。"
        : "已通过后端升级高优先级人工处置；机器人保持原地且禁止返航。",
    );
  }

  function resolveAndReturn() {
    if (!validIncidentId) return Promise.resolve(false);
    if (!returnEvaluation.value.allowed) {
      operationFeedback.value = {
        kind: "error",
        code: "SAFE_RETURN_PRECONDITION_FAILED",
        message: "返航前置条件未满足。",
        blockedBy: returnEvaluation.value.blockedBy,
      };
      return Promise.resolve(false);
    }
    return runOperation(
      "resolve-return",
      (signal) => robotEmergencyApi.resolveAndReturn(
        validIncidentId,
        {
          request_id: requestId("emergency-return"),
          resolution: "管理员确认老人安全并请求 Mock 返航",
        },
        signal,
      ),
      "后端已进入 Mock 返航中；尚未完成应急闭环。",
    );
  }

  function completeReturn() {
    if (!validIncidentId) return Promise.resolve(false);
    return runOperation(
      "complete-return",
      (signal) => robotEmergencyApi.completeMockReturn(
        validIncidentId,
        { request_id: requestId("mock-return-complete") },
        signal,
      ),
      "Mock 返航已由后端完成，应急案例已闭环。",
    );
  }

  function scheduleEventRefresh() {
    if (refreshTimer !== null) window.clearTimeout(refreshTimer);
    refreshTimer = window.setTimeout(() => {
      refreshTimer = null;
      void refresh();
    }, 120);
  }

  function acceptWebSocketSnapshot(event: RobotStatusEvent) {
    if (!validIncidentId) return;
    const next = validateEmergencyBundle(
      event.data,
      validIncidentId,
      `/ws/robot/emergency/${validIncidentId}#${event.type}`,
    );
    applyBundle(next);
  }

  function acceptWebSocketEvent(event: RobotStatusEvent) {
    if (!validIncidentId) return;
    const endpoint = `/ws/robot/emergency/${validIncidentId}#${event.type}`;
    const data = event.data as Record<string, unknown>;
    if ("emergency_case" in data) {
      applyBundle(validateEmergencyBundle(data, validIncidentId, endpoint));
    } else {
      applyCase(validateEmergencyCase(data, validIncidentId, endpoint));
    }
    if (!liveEvents.value.some((item) => item.sequence === event.sequence)) {
      liveEvents.value = [...liveEvents.value, event].slice(-50);
    }
    lastUpdatedAt.value = event.timestamp;
    scheduleEventRefresh();
  }

  function setConnectionState(state: RobotConnectionState) {
    connectionState.value = state;
  }

  onBeforeUnmount(() => {
    loadController?.abort();
    operationController?.abort();
    if (refreshTimer !== null) window.clearTimeout(refreshTimer);
  });

  if (validIncidentId) void refresh({ initial: true });

  return {
    activeOperation,
    bootstrapAlarm,
    bundle,
    connectionState,
    contractIssue,
    dialogueTurns,
    emergencyCase,
    lastUpdatedAt,
    liveEvents,
    loadError,
    loading,
    mockContractSafe,
    notFound,
    operationFeedback,
    operationsDisabled,
    refreshing,
    returnEvaluation,
    safetyInterlock,
    acceptWebSocketEvent,
    acceptWebSocketSnapshot,
    acknowledge,
    completeReturn,
    dispatch,
    refresh,
    registerContractError,
    resolveAndReturn,
    resume,
    setConnectionState,
    startDialogue,
    submitDialogueResult,
  };
}
