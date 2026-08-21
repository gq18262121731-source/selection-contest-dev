import { API_BASE, requestJson } from "./client";
import {
  assertMockRobotContract,
  RobotContractError,
  validateApiEnvelope,
} from "./robotContractPolicy";
import type {
  ApiEnvelope,
  MockDialogueResultRequest,
  MockDialogueStartRequest,
  MockReturnCompleteRequest,
  RobotDialogueTurn,
  RobotEmergencyAcknowledgeRequest,
  RobotEmergencyCase,
  RobotEmergencyDispatchRequest,
  RobotEmergencyIncidentBundle,
  RobotEmergencyResolveRequest,
} from "../types/robot";

function jsonInit(body: unknown, signal?: AbortSignal): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  };
}

function requireRecord(value: unknown, endpoint: string, label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new RobotContractError(
      "ROBOT_API_INVALID_ENVELOPE",
      endpoint,
      `${label}结构无效`,
    );
  }
  return value as Record<string, unknown>;
}

function requireIncident(
  value: Record<string, unknown>,
  incidentId: string,
  endpoint: string,
) {
  if (value.incident_id !== incidentId) {
    throw new RobotContractError(
      "ROBOT_API_INVALID_ENVELOPE",
      endpoint,
      "应急数据 incident_id 与当前页面不一致",
    );
  }
}

export function validateEmergencyCase(
  value: unknown,
  incidentId: string,
  endpoint: string,
): RobotEmergencyCase {
  const record = requireRecord(value, endpoint, "应急案例");
  assertMockRobotContract(record, endpoint);
  requireIncident(record, incidentId, endpoint);
  if (
    typeof record.case_id !== "string"
    || typeof record.execution_state !== "string"
    || typeof record.status !== "string"
    || typeof record.control_owner !== "string"
  ) {
    throw new RobotContractError(
      "ROBOT_API_INVALID_ENVELOPE",
      endpoint,
      "应急案例缺少必要状态字段",
    );
  }
  return record as unknown as RobotEmergencyCase;
}

export function validateEmergencyDialogue(
  value: unknown,
  incidentId: string,
  endpoint: string,
): RobotDialogueTurn[] {
  if (!Array.isArray(value)) {
    throw new RobotContractError(
      "ROBOT_API_INVALID_ENVELOPE",
      endpoint,
      "应急对话列表结构无效",
    );
  }
  return value.map((item, index) => {
    const itemEndpoint = `${endpoint}[${index}]`;
    const record = requireRecord(item, itemEndpoint, "应急对话");
    assertMockRobotContract(record, itemEndpoint);
    requireIncident(record, incidentId, itemEndpoint);
    if (typeof record.turn_id !== "string" || typeof record.role !== "string") {
      throw new RobotContractError(
        "ROBOT_API_INVALID_ENVELOPE",
        itemEndpoint,
        "应急对话缺少必要字段",
      );
    }
    return record as unknown as RobotDialogueTurn;
  });
}

export function validateEmergencyBundle(
  value: unknown,
  incidentId: string,
  endpoint: string,
): RobotEmergencyIncidentBundle {
  const record = requireRecord(value, endpoint, "应急详情");
  assertMockRobotContract(record, endpoint);
  requireIncident(record, incidentId, endpoint);
  const emergencyCase = validateEmergencyCase(record.emergency_case, incidentId, `${endpoint}#case`);
  const dialogueTurns = validateEmergencyDialogue(
    record.dialogue_turns,
    incidentId,
    `${endpoint}#dialogue`,
  );
  if (!Array.isArray(record.navigation_events)) {
    throw new RobotContractError(
      "ROBOT_API_INVALID_ENVELOPE",
      endpoint,
      "应急导航事件列表结构无效",
    );
  }
  record.navigation_events.forEach((event, index) => {
    const eventEndpoint = `${endpoint}#events[${index}]`;
    const eventRecord = requireRecord(event, eventEndpoint, "应急导航事件");
    assertMockRobotContract(eventRecord, eventEndpoint);
    if (eventRecord.incident_id !== null) requireIncident(eventRecord, incidentId, eventEndpoint);
  });
  return {
    ...(record as unknown as RobotEmergencyIncidentBundle),
    emergency_case: emergencyCase,
    dialogue_turns: dialogueTurns,
  };
}

async function requestEnvelope<T>(
  endpoint: string,
  init: RequestInit | undefined,
  validate: (value: unknown, endpoint: string) => T,
): Promise<ApiEnvelope<T>> {
  const payload = await requestJson<unknown>(`${API_BASE}${endpoint}`, init);
  const envelope = validateApiEnvelope<unknown>(payload, endpoint);
  return {
    ...envelope,
    data: validate(envelope.data, endpoint),
  };
}

function emergencyEndpoint(incidentId: string, suffix = "") {
  return `/robot/emergency/${encodeURIComponent(incidentId)}${suffix}`;
}

function validateCaseFor(incidentId: string) {
  return (value: unknown, endpoint: string) => validateEmergencyCase(value, incidentId, endpoint);
}

function validateBundleFor(incidentId: string) {
  return (value: unknown, endpoint: string) => validateEmergencyBundle(value, incidentId, endpoint);
}

function validateDialogueFor(incidentId: string) {
  return (value: unknown, endpoint: string) => validateEmergencyDialogue(value, incidentId, endpoint);
}

export const robotEmergencyApi = {
  getEmergencyCase: (incidentId: string, signal?: AbortSignal) =>
    requestEnvelope(
      emergencyEndpoint(incidentId),
      { signal },
      validateBundleFor(incidentId),
    ),
  getEmergencyDialogue: (incidentId: string, signal?: AbortSignal) =>
    requestEnvelope(
      emergencyEndpoint(incidentId, "/dialogue"),
      { signal },
      validateDialogueFor(incidentId),
    ),
  acknowledgeEmergency: (
    incidentId: string,
    body: RobotEmergencyAcknowledgeRequest,
    signal?: AbortSignal,
  ) =>
    requestEnvelope(
      emergencyEndpoint(incidentId, "/acknowledge"),
      jsonInit(body, signal),
      validateCaseFor(incidentId),
    ),
  dispatchEmergency: (
    incidentId: string,
    body: RobotEmergencyDispatchRequest,
    signal?: AbortSignal,
  ) =>
    requestEnvelope(
      emergencyEndpoint(incidentId, "/dispatch"),
      jsonInit(body, signal),
      validateCaseFor(incidentId),
    ),
  resumeEmergency: (incidentId: string, requestId: string, signal?: AbortSignal) =>
    requestEnvelope(
      emergencyEndpoint(incidentId, "/resume"),
      jsonInit({ request_id: requestId }, signal),
      validateCaseFor(incidentId),
    ),
  escalateEmergency: (
    incidentId: string,
    body: MockDialogueResultRequest,
    signal?: AbortSignal,
  ) =>
    requestEnvelope(
      emergencyEndpoint(incidentId, "/escalate"),
      jsonInit(body, signal),
      validateCaseFor(incidentId),
    ),
  resolveAndReturn: (
    incidentId: string,
    body: RobotEmergencyResolveRequest,
    signal?: AbortSignal,
  ) =>
    requestEnvelope(
      emergencyEndpoint(incidentId, "/resolve-and-return"),
      jsonInit(body, signal),
      validateCaseFor(incidentId),
    ),
  startMockDialogue: (
    incidentId: string,
    body: MockDialogueStartRequest,
    signal?: AbortSignal,
  ) =>
    requestEnvelope(
      emergencyEndpoint(incidentId, "/mock/dialogue/start"),
      jsonInit(body, signal),
      validateBundleFor(incidentId),
    ),
  completeMockReturn: (
    incidentId: string,
    body: MockReturnCompleteRequest,
    signal?: AbortSignal,
  ) =>
    requestEnvelope(
      emergencyEndpoint(incidentId, "/mock/return/complete"),
      jsonInit(body, signal),
      validateBundleFor(incidentId),
  ),
};
