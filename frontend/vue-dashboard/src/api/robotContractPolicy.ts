import type { ApiEnvelope, MockRobotContract } from "../types/robot";

export class RobotContractError extends Error {
  readonly code: "ROBOT_API_INVALID_ENVELOPE" | "ROBOT_INTERFACE_SAFETY_CONTRACT_VIOLATION";
  readonly endpoint: string;

  constructor(
    code: "ROBOT_API_INVALID_ENVELOPE" | "ROBOT_INTERFACE_SAFETY_CONTRACT_VIOLATION",
    endpoint: string,
    message: string,
  ) {
    super(message);
    this.name = "RobotContractError";
    this.code = code;
    this.endpoint = endpoint;
  }
}

export function isRobotRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function assertMockRobotContract(
  value: unknown,
  endpoint: string,
): asserts value is Record<string, unknown> & MockRobotContract {
  if (!isRobotRecord(value)) {
    throw new RobotContractError("ROBOT_API_INVALID_ENVELOPE", endpoint, "机器人接口响应结构无效");
  }
  if (value.provider !== "mock" || value.real_motion_enabled !== false) {
    throw new RobotContractError(
      "ROBOT_INTERFACE_SAFETY_CONTRACT_VIOLATION",
      endpoint,
      "接口安全契约异常：仅允许 provider=mock 且 real_motion_enabled=false",
    );
  }
}

export function validateApiEnvelope<T>(payload: unknown, endpoint: string): ApiEnvelope<T> {
  if (
    !isRobotRecord(payload)
    || payload.success !== true
    || typeof payload.code !== "string"
    || typeof payload.message !== "string"
    || typeof payload.timestamp !== "string"
    || !("data" in payload)
  ) {
    throw new RobotContractError("ROBOT_API_INVALID_ENVELOPE", endpoint, "机器人接口 envelope 结构无效");
  }
  return payload as unknown as ApiEnvelope<T>;
}

export function validateRobotEnvelope<T extends MockRobotContract>(
  payload: unknown,
  endpoint: string,
): ApiEnvelope<T> {
  const envelope = validateApiEnvelope<T>(payload, endpoint);
  assertMockRobotContract(envelope.data, endpoint);
  return envelope;
}
