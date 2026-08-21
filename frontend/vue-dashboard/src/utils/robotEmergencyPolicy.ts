import type { AlarmRecord } from "../api/client";
import type {
  RobotAlarmExtension,
  RobotDialogueIntent,
  RobotEmergencyCase,
  RobotSafetyInterlock,
} from "../types/robot";

export const ROBOT_EMERGENCY_HASH = "#/robot-emergency";
export const ROBOT_EMERGENCY_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$/;

const intentCopy: Record<RobotDialogueIntent, {
  input: string;
  confidence: number;
  label: string;
}> = {
  safe_response: { input: "我没事，不需要帮助。", confidence: 0.96, label: "我没事" },
  need_help: { input: "我摔倒了，需要帮助。", confidence: 0.98, label: "需要帮助" },
  no_response: { input: "15 秒内无有效回应", confidence: 1, label: "无回应" },
  uncertain: { input: "模拟输入不清晰，无法可靠判断。", confidence: 0.42, label: "无法判断" },
};

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function textValue(...values: unknown[]): string | null {
  const found = values.find((value) => typeof value === "string" && value.trim());
  return typeof found === "string" ? found.trim() : null;
}

function numberValue(...values: unknown[]): number | null {
  for (const value of values) {
    const parsed = typeof value === "number" ? value : Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

export function isValidRobotEmergencyIncidentId(value: unknown): value is string {
  return typeof value === "string" && ROBOT_EMERGENCY_ID_PATTERN.test(value.trim());
}

export function buildRobotEmergencyHash(incidentId: string): string {
  if (!isValidRobotEmergencyIncidentId(incidentId)) {
    throw new Error("INVALID_ROBOT_EMERGENCY_INCIDENT_ID");
  }
  return `${ROBOT_EMERGENCY_HASH}?incidentId=${encodeURIComponent(incidentId.trim())}`;
}

export function parseRobotEmergencyIncidentId(hash: string): string | null {
  const [path, rawQuery = ""] = hash.split("?", 2);
  if (path !== ROBOT_EMERGENCY_HASH) return null;
  const params = new URLSearchParams(rawQuery);
  const incidentId = params.get("incidentId");
  if (!isValidRobotEmergencyIncidentId(incidentId)) return null;
  return incidentId.trim();
}

export function extractRobotAlarmExtension(alarm: AlarmRecord): RobotAlarmExtension | null {
  const metadata = asRecord(alarm.metadata);
  const event = asRecord(metadata?.event) ?? asRecord(metadata?.raw_event) ?? metadata;
  const incidentId = textValue(event?.incident_id, metadata?.incident_id);
  if (!isValidRobotEmergencyIncidentId(incidentId)) return null;
  return {
    incident_id: incidentId,
    robot_task_id: textValue(event?.robot_task_id, metadata?.robot_task_id),
    alarm_id: alarm.id,
    camera_id: textValue(event?.camera_id, metadata?.camera_id),
    area_id: textValue(event?.area_id, metadata?.area_id),
    area_name: textValue(event?.area_name, metadata?.area_name),
    event_type: textValue(event?.event_type, metadata?.event_type, event?.type),
    occurred_at: textValue(event?.occurred_at, event?.timestamp, alarm.created_at),
    risk_level: textValue(event?.risk_level, event?.risk, metadata?.risk_level),
    fall_probability: numberValue(
      event?.fall_probability,
      event?.fall_prob,
      event?.fall_score,
      alarm.anomaly_probability,
    ),
  };
}

export function emergencyAlarmStorageKey(incidentId: string): string {
  return `robot-emergency:alarm:${incidentId}`;
}

export function getMockDialogueFixture(intent: RobotDialogueIntent) {
  return intentCopy[intent];
}

export function canResolveEmergencyReturn(
  emergencyCase: RobotEmergencyCase | null,
  interlock: RobotSafetyInterlock | null,
): { allowed: boolean; blockedBy: string[] } {
  const blockedBy: string[] = [];
  if (!emergencyCase || emergencyCase.dialogue_intent !== "safe_response") {
    blockedBy.push("SAFE_RESPONSE_REQUIRED");
  }
  if (emergencyCase?.execution_state !== "waiting_admin_confirmation") {
    blockedBy.push("WAITING_ADMIN_CONFIRMATION_REQUIRED");
  }
  if (!emergencyCase?.acknowledged_by) blockedBy.push("ADMIN_ACKNOWLEDGEMENT_REQUIRED");
  if (emergencyCase?.control_owner === "MANUAL") blockedBy.push("MANUAL_CONTROL_ACTIVE");
  if (!interlock?.passed) {
    blockedBy.push(...(interlock?.blocked_by.length ? interlock.blocked_by : ["SAFETY_INTERLOCK_UNAVAILABLE"]));
  }
  return { allowed: blockedBy.length === 0, blockedBy: [...new Set(blockedBy)] };
}
