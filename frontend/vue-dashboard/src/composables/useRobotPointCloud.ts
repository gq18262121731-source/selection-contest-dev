import { onBeforeUnmount, onMounted, readonly, ref, shallowRef } from "vue";
import { RobotContractError } from "../api/robotContractPolicy";
import type {
  RobotContractIssue,
  RobotPointCloudFrame,
  RobotPointCloudConnectionState,
  RobotPointCloudStreamInfo,
} from "../types/robot";
import { buildRobotWebSocketUrl } from "./useRobotWebSocket";
import { validateRobotPointCloudMessage } from "./robotPointCloudPolicy";

const RETRY_DELAYS_MS = [1000, 2000, 4000, 8000, 15000] as const;

export function useRobotPointCloud() {
  const connectionState = ref<RobotPointCloudConnectionState>("idle");
  const streamInfo = ref<RobotPointCloudStreamInfo | null>(null);
  const latestFrame = shallowRef<RobotPointCloudFrame | null>(null);
  const streamError = ref<{ code: string; message: string } | null>(null);
  const contractIssue = ref<RobotContractIssue | null>(null);
  const stale = ref(false);
  let socket: WebSocket | null = null;
  let retryTimer: number | null = null;
  let staleTimer: number | null = null;
  let attempts = 0;
  let stopped = false;
  let securityBlocked = false;
  let generation = 0;

  function clearTimers() {
    if (retryTimer !== null) window.clearTimeout(retryTimer);
    if (staleTimer !== null) window.clearTimeout(staleTimer);
    retryTimer = null;
    staleTimer = null;
  }

  function armStaleTimer() {
    if (staleTimer !== null) window.clearTimeout(staleTimer);
    const expectedInterval = streamInfo.value?.target_fps ? 1000 / streamInfo.value.target_fps : 1000;
    staleTimer = window.setTimeout(() => {
      stale.value = true;
    }, Math.max(5000, expectedInterval * 4));
  }

  function blockForContract(error: RobotContractError) {
    securityBlocked = true;
    generation += 1;
    clearTimers();
    const active = socket;
    socket = null;
    active?.close(1008, "mock point-cloud safety contract violation");
    connectionState.value = "error";
    contractIssue.value = { code: error.code, message: error.message, endpoint: error.endpoint };
    streamError.value = { code: error.code, message: error.message };
  }

  function scheduleReconnect() {
    if (stopped || securityBlocked || retryTimer !== null) return;
    connectionState.value = "reconnecting";
    const delay = RETRY_DELAYS_MS[Math.min(attempts, RETRY_DELAYS_MS.length - 1)];
    attempts += 1;
    retryTimer = window.setTimeout(() => {
      retryTimer = null;
      connect();
    }, delay);
  }

  function connect() {
    if (
      stopped
      || securityBlocked
      || socket?.readyState === WebSocket.OPEN
      || socket?.readyState === WebSocket.CONNECTING
    ) {
      return;
    }
    const currentGeneration = ++generation;
    connectionState.value = attempts ? "reconnecting" : "connecting";
    try {
      socket = new WebSocket(buildRobotWebSocketUrl("/ws/robot/point-cloud"));
    } catch (error) {
      streamError.value = {
        code: "POINT_CLOUD_CONNECTION_FORBIDDEN",
        message: error instanceof Error ? error.message : "点云连接地址无效",
      };
      connectionState.value = "error";
      return;
    }
    const currentSocket = socket;
    currentSocket.onopen = () => {
      if (generation !== currentGeneration || socket !== currentSocket) return;
      connectionState.value = "connected";
      attempts = 0;
      streamError.value = null;
      currentSocket.send(JSON.stringify({ type: "sync" }));
    };
    currentSocket.onmessage = (event) => {
      if (generation !== currentGeneration || socket !== currentSocket) return;
      try {
        const payload = validateRobotPointCloudMessage(JSON.parse(String(event.data)));
        if (payload.type === "point_cloud_stream_info") {
          streamInfo.value = payload;
          streamError.value = null;
          stale.value = payload.stream_status === "stale";
          armStaleTimer();
        } else if (payload.type === "point_cloud_frame") {
          latestFrame.value = payload;
          streamError.value = null;
          stale.value = false;
          armStaleTimer();
        } else if (payload.type === "error") {
          streamError.value = { code: payload.code, message: payload.message };
        }
      } catch (error) {
        blockForContract(
          error instanceof RobotContractError
            ? error
            : new RobotContractError(
                "ROBOT_API_INVALID_ENVELOPE",
                "/ws/robot/point-cloud",
                "Mock 点云消息无法解析",
              ),
        );
      }
    };
    currentSocket.onerror = () => {
      if (generation === currentGeneration) connectionState.value = "error";
    };
    currentSocket.onclose = () => {
      if (generation !== currentGeneration || socket !== currentSocket) return;
      socket = null;
      if (stopped || securityBlocked) return;
      scheduleReconnect();
    };
  }

  function reconnect() {
    if (stopped || securityBlocked) return;
    generation += 1;
    if (retryTimer !== null) window.clearTimeout(retryTimer);
    retryTimer = null;
    const active = socket;
    socket = null;
    active?.close(1000, "manual reconnect");
    attempts = 1;
    connect();
  }

  onMounted(connect);
  onBeforeUnmount(() => {
    stopped = true;
    generation += 1;
    clearTimers();
    const active = socket;
    socket = null;
    active?.close(1000, "page unmounted");
    connectionState.value = "disconnected";
  });

  return {
    connectionState: readonly(connectionState),
    contractIssue: readonly(contractIssue),
    latestFrame: readonly(latestFrame),
    reconnect,
    stale: readonly(stale),
    streamError: readonly(streamError),
    streamInfo: readonly(streamInfo),
  };
}
