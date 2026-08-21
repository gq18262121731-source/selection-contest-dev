import type { RobotMapPoint } from "../types/robot";

export interface RobotRouteValidation {
  valid: boolean;
  code: string | null;
  message: string;
}

export function validateRobotRoutePointIds(
  pointIds: string[],
  points: RobotMapPoint[],
): RobotRouteValidation {
  if (pointIds.length < 1) {
    return { valid: false, code: "ROUTE_REQUIRES_PATROL_POINT", message: "巡逻路线至少需要一个有效巡逻点" };
  }
  if (new Set(pointIds).size !== pointIds.length) {
    return { valid: false, code: "ROUTE_POINT_DUPLICATED", message: "同一路线不能重复添加点位" };
  }
  const byId = new Map(points.map((point) => [point.point_id, point]));
  const missing = pointIds.find((pointId) => !byId.has(pointId));
  if (missing) {
    return { valid: false, code: "ROUTE_POINT_NOT_FOUND", message: `路线点位 ${missing} 不存在` };
  }
  const invalid = pointIds.find((pointId) => byId.get(pointId)?.status !== "valid");
  if (invalid) {
    return { valid: false, code: "ROUTE_POINT_INVALID", message: "失效点位不能加入巡逻路线" };
  }
  const nonPatrol = pointIds.find((pointId) => byId.get(pointId)?.point_type !== "patrol");
  if (nonPatrol) {
    return { valid: false, code: "ROUTE_POINT_TYPE_INVALID", message: "路线只能包含有效巡逻点" };
  }
  return { valid: true, code: null, message: "路线校验通过" };
}

export function createRobotRequestId(prefix = "robot-ui"): string {
  const id = typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `${prefix}-${id}`;
}
