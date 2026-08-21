import { API_BASE, requestJson } from "./client";
import type {
  ApiEnvelope,
  LegacyRobotStatus,
  MockRobotContract,
  RobotDiagnostics,
  RobotMap,
  RobotMapOperationResult,
  RobotMapPoint,
  RobotMapPreviewRequest,
  RobotMapSaveRequest,
  RobotMappingStartRequest,
  RobotMappingStopRequest,
  RobotNavigationCapability,
  RobotNavigationState,
  RobotNavigationTask,
  RobotPatrolRoute,
  RobotPointUpdateRequest,
  RobotPointWriteRequest,
  RobotRouteDetail,
  RobotRouteWriteRequest,
} from "../types/robot";
import {
  assertMockRobotContract,
  RobotContractError,
  validateApiEnvelope,
  validateRobotEnvelope,
} from "./robotContractPolicy";

export { RobotContractError } from "./robotContractPolicy";

function jsonInit(method: string, body: unknown, signal?: AbortSignal): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  };
}

async function requestEnvelope<T>(
  endpoint: string,
  init?: RequestInit,
  validate?: (data: T, endpoint: string) => void,
): Promise<ApiEnvelope<T>> {
  const payload = await requestJson<unknown>(`${API_BASE}${endpoint}`, init);
  const envelope = validateApiEnvelope<T>(payload, endpoint);
  validate?.(envelope.data, endpoint);
  return envelope;
}

function validateMock(data: MockRobotContract, endpoint: string) {
  assertMockRobotContract(data, endpoint);
}

function validateMockList(data: MockRobotContract[], endpoint: string) {
  if (!Array.isArray(data)) {
    throw new RobotContractError("ROBOT_API_INVALID_ENVELOPE", endpoint, "机器人接口列表结构无效");
  }
  data.forEach((item, index) => assertMockRobotContract(item, `${endpoint}[${index}]`));
}

function validateMapOperation(data: RobotMapOperationResult, endpoint: string) {
  if (!data || typeof data !== "object") {
    throw new RobotContractError("ROBOT_API_INVALID_ENVELOPE", endpoint, "地图操作响应结构无效");
  }
  assertMockRobotContract(data.map, `${endpoint}#map`);
  assertMockRobotContract(data.gateway, `${endpoint}#gateway`);
}

function validateRouteDetail(data: RobotRouteDetail, endpoint: string) {
  if (!data || typeof data !== "object" || !Array.isArray(data.points)) {
    throw new RobotContractError("ROBOT_API_INVALID_ENVELOPE", endpoint, "巡逻路线详情结构无效");
  }
  assertMockRobotContract(data.route, `${endpoint}#route`);
  data.points.forEach((item, index) => assertMockRobotContract(item, `${endpoint}#points[${index}]`));
}

async function getValidatedEnvelope<T extends MockRobotContract>(
  endpoint: string,
  signal?: AbortSignal,
): Promise<ApiEnvelope<T>> {
  const payload = await requestJson<unknown>(`${API_BASE}${endpoint}`, { signal });
  return validateRobotEnvelope<T>(payload, endpoint);
}

export const robotNavigationApi = {
  getRobotStatus: (signal?: AbortSignal) =>
    requestJson<LegacyRobotStatus>(`${API_BASE}/robot/status`, { signal }),
  getRobotDiagnostics: (signal?: AbortSignal) =>
    getValidatedEnvelope<RobotDiagnostics>("/robot/status/diagnostics", signal),
  getNavigationCapabilities: (signal?: AbortSignal) =>
    getValidatedEnvelope<RobotNavigationCapability>("/robot/navigation/capabilities", signal),
  getNavigationState: (signal?: AbortSignal) =>
    getValidatedEnvelope<RobotNavigationState>("/robot/navigation/state", signal),

  startMapping: (body: RobotMappingStartRequest, signal?: AbortSignal) =>
    requestEnvelope<RobotMapOperationResult>(
      "/robot/navigation/mapping/start",
      jsonInit("POST", body, signal),
      validateMapOperation,
    ),
  stopMapping: (body: RobotMappingStopRequest, signal?: AbortSignal) =>
    requestEnvelope<RobotMapOperationResult>(
      "/robot/navigation/mapping/stop",
      jsonInit("POST", body, signal),
      validateMapOperation,
    ),
  previewMap: (body: RobotMapPreviewRequest, signal?: AbortSignal) =>
    requestEnvelope<RobotMap>(
      "/robot/navigation/maps/preview",
      jsonInit("POST", body, signal),
      validateMock,
    ),
  saveMap: (body: RobotMapSaveRequest, signal?: AbortSignal) =>
    requestEnvelope<RobotMapOperationResult>(
      "/robot/navigation/maps/save",
      jsonInit("POST", body, signal),
      validateMapOperation,
    ),
  listMaps: (signal?: AbortSignal) =>
    requestEnvelope<RobotMap[]>("/robot/navigation/maps", { signal }, validateMockList),
  getActiveMap: (signal?: AbortSignal) =>
    requestEnvelope<RobotMap>("/robot/navigation/maps/active", { signal }, validateMock),

  listPoints: (mapId?: string, signal?: AbortSignal) => {
    const query = mapId ? `?map_id=${encodeURIComponent(mapId)}` : "";
    return requestEnvelope<RobotMapPoint[]>(
      `/robot/navigation/points${query}`,
      { signal },
      validateMockList,
    );
  },
  createPoint: (body: RobotPointWriteRequest, signal?: AbortSignal) =>
    requestEnvelope<RobotMapPoint>(
      "/robot/navigation/points",
      jsonInit("POST", body, signal),
      validateMock,
    ),
  updatePoint: (pointId: string, body: RobotPointUpdateRequest, signal?: AbortSignal) =>
    requestEnvelope<RobotMapPoint>(
      `/robot/navigation/points/${encodeURIComponent(pointId)}`,
      jsonInit("PUT", body, signal),
      validateMock,
    ),
  deletePoint: (pointId: string, requestId: string, signal?: AbortSignal) =>
    requestEnvelope<RobotMapPoint>(
      `/robot/navigation/points/${encodeURIComponent(pointId)}?request_id=${encodeURIComponent(requestId)}`,
      { method: "DELETE", signal },
      validateMock,
    ),

  listRoutes: (mapId?: string, signal?: AbortSignal) => {
    const query = mapId ? `?map_id=${encodeURIComponent(mapId)}` : "";
    return requestEnvelope<RobotPatrolRoute[]>(
      `/robot/navigation/routes${query}`,
      { signal },
      validateMockList,
    );
  },
  createRoute: (body: RobotRouteWriteRequest, signal?: AbortSignal) =>
    requestEnvelope<RobotPatrolRoute>(
      "/robot/navigation/routes",
      jsonInit("POST", body, signal),
      validateMock,
    ),
  getRouteDetail: (routeId: string, signal?: AbortSignal) =>
    requestEnvelope<RobotRouteDetail>(
      `/robot/navigation/routes/${encodeURIComponent(routeId)}`,
      { signal },
      validateRouteDetail,
    ),
  startPatrol: (
    routeId: string,
    body: { request_id: string; source_event_id?: string; trace_id?: string },
    signal?: AbortSignal,
  ) =>
    requestEnvelope<RobotNavigationTask>(
      `/robot/navigation/routes/${encodeURIComponent(routeId)}/start`,
      jsonInit("POST", body, signal),
      validateMock,
    ),
  pauseTask: (taskId: string, requestId: string, signal?: AbortSignal) =>
    requestEnvelope<RobotNavigationTask>(
      `/robot/navigation/tasks/${encodeURIComponent(taskId)}/pause`,
      jsonInit("POST", { request_id: requestId }, signal),
      validateMock,
    ),
  resumeTask: (taskId: string, requestId: string, signal?: AbortSignal) =>
    requestEnvelope<RobotNavigationTask>(
      `/robot/navigation/tasks/${encodeURIComponent(taskId)}/resume`,
      jsonInit("POST", { request_id: requestId }, signal),
      validateMock,
    ),
  stopTask: (taskId: string, requestId: string, signal?: AbortSignal) =>
    requestEnvelope<RobotNavigationTask>(
      `/robot/navigation/tasks/${encodeURIComponent(taskId)}/stop`,
      jsonInit("POST", { request_id: requestId }, signal),
      validateMock,
    ),
  acquireManualControl: (taskId: string, requestId: string, signal?: AbortSignal) =>
    requestEnvelope<RobotNavigationTask>(
      `/robot/navigation/tasks/${encodeURIComponent(taskId)}/manual-acquire`,
      jsonInit("POST", { request_id: requestId }, signal),
      validateMock,
    ),
  releaseManualControl: (taskId: string, requestId: string, signal?: AbortSignal) =>
    requestEnvelope<RobotNavigationTask>(
      `/robot/navigation/tasks/${encodeURIComponent(taskId)}/manual-release`,
      jsonInit("POST", { request_id: requestId }, signal),
      validateMock,
    ),
};
