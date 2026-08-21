import { computed, onBeforeUnmount, ref, watch } from "vue";
import { robotNavigationApi, RobotContractError } from "../api/robotNavigationApi";
import type {
  LegacyRobotStatus,
  RobotContractIssue,
  RobotDiagnostics,
  RobotNavigationCapability,
  RobotNavigationState,
  RobotStatusEvent,
  RobotTimelineItem,
} from "../types/robot";
import { useRobotWebSocket } from "./useRobotWebSocket";

const EVENT_TITLES: Record<string, string> = {
  robot_status_snapshot: "状态快照已同步",
  navigation_snapshot: "导航状态已同步",
  navigation_upstream_error: "导航上游异常",
  emergency_stop_changed: "急停状态变化",
  control_owner_changed: "控制权变化",
  map_draft_created: "地图状态变化",
  map_preview_ready: "地图预览状态变化",
  navigation_started: "导航状态变化",
  navigation_resumed: "导航状态恢复",
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function getText(data: Record<string, unknown>, key: string): string | undefined {
  const value = data[key];
  return typeof value === "string" && value.trim() ? value : undefined;
}

function describeEvent(event: RobotStatusEvent): RobotTimelineItem {
  const code = getText(event.data, "code") ?? getText(event.data, "error_code");
  const message = getText(event.data, "message")
    ?? getText(event.data, "execution_state")
    ?? getText(event.data, "control_owner")
    ?? "机器人状态已更新";
  const isError = event.type.includes("error") || Boolean(code);
  return {
    id: `${event.sequence}-${event.type}`,
    type: event.type,
    title: EVENT_TITLES[event.type] ?? "机器人状态事件",
    message,
    timestamp: event.timestamp,
    severity: isError ? "error" : event.type.includes("resume") ? "success" : "info",
    code,
  };
}

export function useRobotStatus() {
  const legacyStatus = ref<LegacyRobotStatus | null>(null);
  const diagnostics = ref<RobotDiagnostics | null>(null);
  const capabilities = ref<RobotNavigationCapability | null>(null);
  const navigationState = ref<RobotNavigationState | null>(null);
  const events = ref<RobotTimelineItem[]>([]);
  const loading = ref(true);
  const refreshing = ref(false);
  const errors = ref<string[]>([]);
  const contractIssue = ref<RobotContractIssue | null>(null);
  const lastUpdatedAt = ref<string | null>(null);
  let activeController: AbortController | null = null;
  let disposed = false;

  function addTimelineItem(item: RobotTimelineItem) {
    const first = events.value[0];
    if (first && first.type === item.type && first.message === item.message) {
      events.value[0] = item;
      return;
    }
    events.value = [item, ...events.value].slice(0, 20);
  }

  function setContractIssue(error: RobotContractError) {
    contractIssue.value = {
      code: error.code,
      message: error.message,
      endpoint: error.endpoint,
    };
    addTimelineItem({
      id: `contract-${Date.now()}`,
      type: "contract_error",
      title: "接口安全契约异常",
      message: error.message,
      timestamp: new Date().toISOString(),
      severity: "error",
      code: error.code,
    });
  }

  async function refresh(options: { initial?: boolean } = {}) {
    activeController?.abort();
    const controller = new AbortController();
    activeController = controller;
    if (options.initial) loading.value = true;
    else refreshing.value = true;
    errors.value = [];
    contractIssue.value = null;

    const results = await Promise.allSettled([
      robotNavigationApi.getRobotStatus(controller.signal),
      robotNavigationApi.getRobotDiagnostics(controller.signal),
      robotNavigationApi.getNavigationCapabilities(controller.signal),
      robotNavigationApi.getNavigationState(controller.signal),
    ]);

    if (disposed || controller.signal.aborted) return;
    const labels = ["机器人基础状态", "机器人诊断", "导航能力", "导航状态"];
    results.forEach((result, index) => {
      if (result.status === "fulfilled") {
        if (index === 0) legacyStatus.value = result.value as LegacyRobotStatus;
        if (index === 1) diagnostics.value = result.value.data as RobotDiagnostics;
        if (index === 2) capabilities.value = result.value.data as RobotNavigationCapability;
        if (index === 3) navigationState.value = result.value.data as RobotNavigationState;
        return;
      }
      if (result.reason instanceof RobotContractError) {
        setContractIssue(result.reason);
      } else {
        const message = result.reason instanceof Error ? result.reason.message : "请求失败";
        errors.value.push(`${labels[index]}：${message}`);
      }
    });
    lastUpdatedAt.value = new Date().toISOString();
    loading.value = false;
    refreshing.value = false;
  }

  function applySnapshot(event: RobotStatusEvent) {
    if (event.type === "robot_status_snapshot") {
      const data = event.data;
      diagnostics.value = data as unknown as RobotDiagnostics;
      const navigation = data.navigation;
      if (isRecord(navigation)) navigationState.value = navigation as unknown as RobotNavigationState;
    } else if (event.type === "navigation_snapshot") {
      navigationState.value = event.data as unknown as RobotNavigationState;
    }
    lastUpdatedAt.value = event.timestamp;
    addTimelineItem(describeEvent(event));
  }

  function applyEvent(event: RobotStatusEvent) {
    const data = event.data;
    if (event.type === "navigation_snapshot") {
      navigationState.value = data as unknown as RobotNavigationState;
    } else if (navigationState.value) {
      const knownUpdates: Partial<RobotNavigationState> = {};
      if (typeof data.execution_state === "string") {
        knownUpdates.execution_state = data.execution_state as RobotNavigationState["execution_state"];
      }
      if (typeof data.control_owner === "string") {
        knownUpdates.control_owner = data.control_owner as RobotNavigationState["control_owner"];
      }
      navigationState.value = { ...navigationState.value, ...knownUpdates };
    }
    lastUpdatedAt.value = event.timestamp;
    addTimelineItem(describeEvent(event));
  }

  const socket = useRobotWebSocket({
    path: "/ws/robot/status",
    onSnapshot: applySnapshot,
    onEvent: applyEvent,
    refreshSnapshot: () => refresh(),
    onContractError: setContractIssue,
  });

  watch(socket.connectionState, (next, previous) => {
    if (next === "reconnecting" && previous !== "reconnecting") {
      addTimelineItem({
        id: `reconnect-${Date.now()}`,
        type: "websocket_reconnecting",
        title: "实时连接正在恢复",
        message: "状态流已断开，系统将按有限退避自动重连。",
        timestamp: new Date().toISOString(),
        severity: "warning",
      });
    }
    if (next === "connected" && previous === "reconnecting") {
      addTimelineItem({
        id: `reconnected-${Date.now()}`,
        type: "websocket_reconnected",
        title: "实时连接已恢复",
        message: "已重新连接，并触发 REST 快照校准。",
        timestamp: new Date().toISOString(),
        severity: "success",
      });
    }
  });

  onBeforeUnmount(() => {
    disposed = true;
    activeController?.abort();
    activeController = null;
  });

  void refresh({ initial: true });

  return {
    capabilities,
    connectionState: socket.connectionState,
    contractIssue,
    diagnostics,
    errors,
    events,
    lastUpdatedAt,
    legacyStatus,
    loading,
    navigationState,
    reconnect: socket.reconnect,
    refresh,
    refreshing,
    hasData: computed(() => Boolean(diagnostics.value || navigationState.value || legacyStatus.value)),
  };
}
