import type { RobotCapabilityStatus } from "../types/robot";

export interface RobotCapabilityStatusView {
  status: RobotCapabilityStatus;
  label: string;
  reason: string;
}

const READY_VALUES = new Set(["READY", "ready"]);
const NOT_READY_VALUES = new Set(["NOT_READY", "not_ready", "blocked", "unavailable"]);

export function normalizeRobotCapabilityStatus(
  value: unknown,
  unknownReason = "未收到机器人能力状态数据",
): RobotCapabilityStatusView {
  if (value === true || (typeof value === "string" && READY_VALUES.has(value))) {
    return {
      status: "READY",
      label: "已就绪",
      reason: "已收到机器人能力状态并确认可用",
    };
  }

  if (value === false || (typeof value === "string" && NOT_READY_VALUES.has(value))) {
    return {
      status: "NOT_READY",
      label: "未就绪",
      reason: "机器人能力状态明确返回不可用",
    };
  }

  return {
    status: "UNKNOWN",
    label: "未验证",
    reason: unknownReason,
  };
}
