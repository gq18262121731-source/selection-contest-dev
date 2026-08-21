import { computed, onBeforeUnmount, ref } from "vue";
import { ApiError } from "../api/client";
import { RobotContractError, robotNavigationApi } from "../api/robotNavigationApi";
import type {
  RobotContractIssue,
  RobotMap,
  RobotMapPoint,
  RobotMapPointType,
  RobotNavigationState,
  RobotNavigationTask,
  RobotPatrolRoute,
  RobotRouteDetail,
  RobotStatusEvent,
  RobotTimelineItem,
} from "../types/robot";
import { createRobotRequestId, validateRobotRoutePointIds } from "../utils/robotNavigationPolicy";
import { useRobotWebSocket } from "./useRobotWebSocket";

type MappingContext = {
  mapId: string;
  sessionId: string;
};

function eventSeverity(type: string): RobotTimelineItem["severity"] {
  if (/failed|error|blocked|violation/i.test(type)) return "error";
  if (/paused|warning|manual/i.test(type)) return "warning";
  if (/saved|arrived|completed|created/i.test(type)) return "success";
  return "info";
}

function errorMessage(error: unknown): { code: string; message: string } {
  if (error instanceof RobotContractError) return { code: error.code, message: error.message };
  if (error instanceof ApiError) {
    const blockedBy = Array.isArray(error.data?.blocked_by)
      ? error.data.blocked_by.filter((item): item is string => typeof item === "string")
      : [];
    const blockedMessage = blockedBy.length ? `（${blockedBy.join("、")}）` : "";
    return {
      code: error.code ?? `HTTP_${error.status}`,
      message: `${error.detail}${blockedMessage}`,
    };
  }
  if (error instanceof Error) return { code: "ROBOT_UI_OPERATION_FAILED", message: error.message };
  return { code: "ROBOT_UI_OPERATION_FAILED", message: "操作失败，请稍后重试" };
}

function readString(value: unknown, key: string): string | null {
  if (!value || typeof value !== "object") return null;
  const candidate = (value as Record<string, unknown>)[key];
  return typeof candidate === "string" && candidate ? candidate : null;
}

export function useRobotNavigation() {
  const state = ref<RobotNavigationState | null>(null);
  const maps = ref<RobotMap[]>([]);
  const activeMap = ref<RobotMap | null>(null);
  const points = ref<RobotMapPoint[]>([]);
  const routes = ref<RobotPatrolRoute[]>([]);
  const selectedRoute = ref<RobotRouteDetail | null>(null);
  const timeline = ref<RobotTimelineItem[]>([]);
  const loading = ref(false);
  const activeOperation = ref<string | null>(null);
  const operationError = ref<{ code: string; message: string } | null>(null);
  const contractIssue = ref<RobotContractIssue | null>(null);
  const mappingContext = ref<MappingContext | null>(null);
  let refreshController: AbortController | null = null;
  let eventRefreshTimer: number | null = null;
  const seenEventKeys = new Set<string>();

  const currentTask = computed<RobotNavigationTask | null>(() => {
    const candidate = state.value?.active_task ?? state.value?.current_task;
    if (!candidate || candidate.provider !== "mock" || candidate.real_motion_enabled !== false) return null;
    return candidate as RobotNavigationTask;
  });

  function pushTimeline(item: Omit<RobotTimelineItem, "id">) {
    timeline.value = [
      { ...item, id: createRobotRequestId("timeline") },
      ...timeline.value,
    ].slice(0, 30);
  }

  function scheduleEventRefresh() {
    if (eventRefreshTimer !== null) return;
    eventRefreshTimer = window.setTimeout(() => {
      eventRefreshTimer = null;
      void refresh();
    }, 120);
  }

  function handleContractError(error: RobotContractError) {
    contractIssue.value = { code: error.code, message: error.message, endpoint: error.endpoint };
    operationError.value = { code: error.code, message: error.message };
    pushTimeline({
      type: "contract_violation",
      title: "Mock 安全契约异常",
      message: error.message,
      timestamp: new Date().toISOString(),
      severity: "error",
      code: error.code,
    });
  }

  async function refresh() {
    refreshController?.abort();
    const controller = new AbortController();
    refreshController = controller;
    loading.value = true;
    operationError.value = null;
    try {
      const [stateResult, mapsResult, activeMapResult] = await Promise.allSettled([
        robotNavigationApi.getNavigationState(controller.signal),
        robotNavigationApi.listMaps(controller.signal),
        robotNavigationApi.getActiveMap(controller.signal),
      ]);
      if (stateResult.status === "fulfilled") state.value = stateResult.value.data;
      else throw stateResult.reason;
      if (mapsResult.status === "fulfilled") maps.value = mapsResult.value.data;
      else throw mapsResult.reason;
      if (activeMapResult.status === "fulfilled") activeMap.value = activeMapResult.value.data;
      else if (!(activeMapResult.reason instanceof ApiError && activeMapResult.reason.status === 404)) {
        throw activeMapResult.reason;
      } else {
        activeMap.value = null;
      }

      const mapId = activeMap.value?.map_id ?? mappingContext.value?.mapId;
      if (mapId) {
        const [pointResult, routeResult] = await Promise.all([
          robotNavigationApi.listPoints(mapId, controller.signal),
          robotNavigationApi.listRoutes(mapId, controller.signal),
        ]);
        points.value = pointResult.data;
        routes.value = routeResult.data;
      } else {
        points.value = [];
        routes.value = [];
      }
    } catch (error) {
      if (controller.signal.aborted) return;
      if (error instanceof RobotContractError) handleContractError(error);
      else operationError.value = errorMessage(error);
    } finally {
      if (refreshController === controller) loading.value = false;
    }
  }

  async function runOperation<T>(key: string, operation: () => Promise<T>): Promise<T | null> {
    if (activeOperation.value) {
      operationError.value = {
        code: "ROBOT_OPERATION_IN_PROGRESS",
        message: `操作 ${activeOperation.value} 尚未完成，请勿重复提交`,
      };
      return null;
    }
    activeOperation.value = key;
    operationError.value = null;
    try {
      const result = await operation();
      await refresh();
      return result;
    } catch (error) {
      if (error instanceof RobotContractError) handleContractError(error);
      else operationError.value = errorMessage(error);
      return null;
    } finally {
      activeOperation.value = null;
    }
  }

  async function startMapping(sessionName: string) {
    return runOperation("mapping-start", async () => {
      const response = await robotNavigationApi.startMapping({
        session_name: sessionName,
        request_id: createRobotRequestId("mapping-start"),
      });
      const gatewaySession = readString(response.data.gateway, "session_id");
      const metadataSession = readString(response.data.map.metadata, "mapping_session_id");
      mappingContext.value = {
        mapId: response.data.map.map_id,
        sessionId: gatewaySession ?? metadataSession ?? sessionName,
      };
      return response.data;
    });
  }

  async function stopMapping() {
    const context = mappingContext.value;
    if (!context) {
      operationError.value = { code: "MAPPING_CONTEXT_MISSING", message: "缺少本次 Mock 建图会话信息" };
      return null;
    }
    return runOperation("mapping-stop", async () => {
      const response = await robotNavigationApi.stopMapping({
        map_id: context.mapId,
        session_id: context.sessionId,
        request_id: createRobotRequestId("mapping-stop"),
      });
      return response.data;
    });
  }

  async function previewMap() {
    const mapId = mappingContext.value?.mapId;
    if (!mapId) return null;
    return runOperation("map-preview", async () => (
      await robotNavigationApi.previewMap({
        map_id: mapId,
        metadata: { source: "mock_frontend_preview" },
        request_id: createRobotRequestId("map-preview"),
      })
    ).data);
  }

  async function saveMap(name: string, replaceConfirmed: boolean) {
    const context = mappingContext.value;
    if (!context) return null;
    return runOperation("map-save", async () => (
      await robotNavigationApi.saveMap({
        map_id: context.mapId,
        session_id: context.sessionId,
        name,
        replace_confirmed: replaceConfirmed,
        request_id: createRobotRequestId("map-save"),
      })
    ).data);
  }

  async function savePoint(payload: {
    pointId?: string;
    name: string;
    pointType: RobotMapPointType;
    x: number;
    y: number;
    yaw: number;
    areaId?: string;
  }) {
    const mapId = activeMap.value?.map_id;
    if (!mapId) {
      operationError.value = { code: "MAP_NOT_ACTIVE", message: "没有激活地图，不能保存 Mock 点位" };
      return null;
    }
    const metadata = payload.areaId ? { area_id: payload.areaId } : {};
    if (payload.pointId) {
      return runOperation("point-update", async () => (
        await robotNavigationApi.updatePoint(payload.pointId!, {
          name: payload.name,
          point_type: payload.pointType,
          x: payload.x,
          y: payload.y,
          yaw: payload.yaw,
          metadata,
          request_id: createRobotRequestId("point-update"),
        })
      ).data);
    }
    return runOperation("point-create", async () => (
      await robotNavigationApi.createPoint({
        point_id: createRobotRequestId("point"),
        map_id: mapId,
        name: payload.name,
        point_type: payload.pointType,
        x: payload.x,
        y: payload.y,
        yaw: payload.yaw,
        metadata,
        request_id: createRobotRequestId("point-create"),
      })
    ).data);
  }

  async function invalidatePoint(pointId: string) {
    return runOperation("point-invalidate", async () => (
      await robotNavigationApi.deletePoint(pointId, createRobotRequestId("point-delete"))
    ).data);
  }

  async function saveRoute(name: string, pointIds: string[]) {
    const mapId = activeMap.value?.map_id;
    if (!mapId) {
      operationError.value = { code: "MAP_NOT_ACTIVE", message: "没有激活地图，不能保存巡逻路线" };
      return null;
    }
    const validation = validateRobotRoutePointIds(pointIds, points.value);
    if (!validation.valid) {
      operationError.value = { code: validation.code ?? "ROUTE_INVALID", message: validation.message };
      return null;
    }
    return runOperation("route-create", async () => (
      await robotNavigationApi.createRoute({
        route_id: createRobotRequestId("route"),
        map_id: mapId,
        name,
        point_ids: pointIds,
        metadata: { source: "mock_frontend_editor" },
        request_id: createRobotRequestId("route-create"),
      })
    ).data);
  }

  async function loadRoute(routeId: string) {
    const result = await runOperation("route-load", async () => (
      await robotNavigationApi.getRouteDetail(routeId)
    ).data);
    if (result) selectedRoute.value = result;
    return result;
  }

  async function startPatrol(routeId: string) {
    return runOperation("patrol-start", async () => (
      await robotNavigationApi.startPatrol(routeId, {
        request_id: createRobotRequestId("patrol-start"),
      })
    ).data);
  }

  async function taskOperation(
    action: "pause" | "resume" | "stop" | "manual-acquire" | "manual-release",
  ) {
    const taskId = state.value?.active_task_id ?? currentTask.value?.task_id;
    if (!taskId) {
      operationError.value = { code: "TASK_NOT_ACTIVE", message: "当前没有可操作的 Mock 导航任务" };
      return null;
    }
    return runOperation(`task-${action}`, async () => {
      const requestId = createRobotRequestId(`task-${action}`);
      if (action === "pause") return (await robotNavigationApi.pauseTask(taskId, requestId)).data;
      if (action === "resume") return (await robotNavigationApi.resumeTask(taskId, requestId)).data;
      if (action === "stop") return (await robotNavigationApi.stopTask(taskId, requestId)).data;
      if (action === "manual-acquire") {
        return (await robotNavigationApi.acquireManualControl(taskId, requestId)).data;
      }
      return (await robotNavigationApi.releaseManualControl(taskId, requestId)).data;
    });
  }

  function applyEvent(event: RobotStatusEvent) {
    if (event.type.endsWith("_snapshot")) {
      state.value = event.data as unknown as RobotNavigationState;
    } else {
      const eventKey = `${event.upstream_sequence ?? event.sequence}:${event.type}:${event.timestamp}`;
      if (seenEventKeys.has(eventKey)) return;
      seenEventKeys.add(eventKey);
      if (seenEventKeys.size > 120) {
        const oldestKey = seenEventKeys.values().next().value;
        if (oldestKey) seenEventKeys.delete(oldestKey);
      }
      const data = event.data;
      if (data.navigation && typeof data.navigation === "object") {
        state.value = data.navigation as RobotNavigationState;
      } else if (data.state && typeof data.state === "object") {
        state.value = data.state as RobotNavigationState;
      }
      pushTimeline({
        type: event.type,
        title: event.type.replace(/_/g, " "),
        message: readString(data, "message") ?? "Mock 导航状态已更新",
        timestamp: event.timestamp,
        severity: eventSeverity(event.type),
        code: readString(data, "error_code") ?? undefined,
      });
      scheduleEventRefresh();
    }
  }

  const navigationSocket = useRobotWebSocket({
    path: "/ws/robot/navigation",
    onSnapshot: applyEvent,
    onEvent: applyEvent,
    refreshSnapshot: refresh,
    onContractError: handleContractError,
  });

  onBeforeUnmount(() => {
    refreshController?.abort();
    if (eventRefreshTimer !== null) {
      window.clearTimeout(eventRefreshTimer);
      eventRefreshTimer = null;
    }
    seenEventKeys.clear();
  });

  return {
    activeMap,
    activeOperation,
    connectionState: navigationSocket.connectionState,
    contractIssue,
    currentTask,
    invalidatePoint,
    loading,
    loadRoute,
    maps,
    operationError,
    points,
    previewMap,
    refresh,
    releaseManualControl: () => taskOperation("manual-release"),
    acquireManualControl: () => taskOperation("manual-acquire"),
    pauseTask: () => taskOperation("pause"),
    resumeTask: () => taskOperation("resume"),
    routes,
    saveMap,
    savePoint,
    saveRoute,
    selectedRoute,
    startMapping,
    startPatrol,
    state,
    stopMapping,
    stopTask: () => taskOperation("stop"),
    timeline,
  };
}
