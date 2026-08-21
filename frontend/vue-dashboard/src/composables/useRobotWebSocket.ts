import { onBeforeUnmount, readonly, ref, type Ref } from "vue";
import { WS_BASE } from "../api/client";
import { assertMockRobotContract, RobotContractError } from "../api/robotContractPolicy";
import type { RobotConnectionState, RobotStatusEvent } from "../types/robot";

type RobotWebSocketOptions = {
  path: string;
  onSnapshot: (event: RobotStatusEvent) => void;
  onEvent: (event: RobotStatusEvent) => void;
  refreshSnapshot: () => void | Promise<void>;
  onContractError?: (error: RobotContractError) => void;
};

type SharedRobotSocket = {
  path: string;
  socket: WebSocket | null;
  subscribers: Set<RobotWebSocketOptions>;
  connectionState: Ref<RobotConnectionState>;
  reconnectAttempts: Ref<number>;
  reconnectTimer: number | null;
  generation: number;
  closed: boolean;
  securityBlocked: boolean;
};

const sharedSockets = new Map<string, SharedRobotSocket>();
const RETRY_DELAYS_MS = [1000, 2000, 4000, 8000, 15000] as const;

export function buildRobotWebSocketUrl(path: string): string {
  const base = new URL(WS_BASE, window.location.origin);
  if (base.port === "8090") {
    throw new Error("ROBOT_DIRECT_GATEWAY_CONNECTION_FORBIDDEN");
  }
  base.protocol = base.protocol === "https:" || base.protocol === "wss:" ? "wss:" : "ws:";
  base.pathname = path.startsWith("/") ? path : `/${path}`;
  base.search = "";
  base.hash = "";
  return base.toString();
}

function isStatusEvent(value: unknown, endpoint: string): value is RobotStatusEvent {
  assertMockRobotContract(value, endpoint);
  const payload = value as Record<string, unknown>;
  if (
    typeof payload.type !== "string"
    || typeof payload.sequence !== "number"
    || typeof payload.timestamp !== "string"
    || typeof payload.data !== "object"
    || payload.data === null
    || Array.isArray(payload.data)
  ) {
    throw new RobotContractError(
      "ROBOT_API_INVALID_ENVELOPE",
      endpoint,
      "机器人 WebSocket 消息结构无效",
    );
  }
  return true;
}

function reportContractError(entry: SharedRobotSocket, error: RobotContractError) {
  entry.securityBlocked = true;
  entry.generation += 1;
  if (entry.reconnectTimer !== null) {
    window.clearTimeout(entry.reconnectTimer);
    entry.reconnectTimer = null;
  }
  const socket = entry.socket;
  entry.socket = null;
  socket?.close(1008, "mock safety contract violation");
  entry.connectionState.value = "error";
  entry.subscribers.forEach((subscriber) => subscriber.onContractError?.(error));
}

function scheduleReconnect(entry: SharedRobotSocket) {
  if (entry.closed || entry.securityBlocked || entry.subscribers.size === 0 || entry.reconnectTimer !== null) return;
  entry.connectionState.value = "reconnecting";
  const index = Math.min(entry.reconnectAttempts.value, RETRY_DELAYS_MS.length - 1);
  const delay = RETRY_DELAYS_MS[index];
  entry.reconnectAttempts.value += 1;
  entry.reconnectTimer = window.setTimeout(() => {
    entry.reconnectTimer = null;
    connectSharedSocket(entry);
  }, delay);
}

function connectSharedSocket(entry: SharedRobotSocket) {
  if (
    entry.closed
    || entry.securityBlocked
    || entry.subscribers.size === 0
    || entry.socket?.readyState === WebSocket.OPEN
    || entry.socket?.readyState === WebSocket.CONNECTING
  ) {
    return;
  }

  const generation = ++entry.generation;
  entry.connectionState.value = entry.reconnectAttempts.value > 0 ? "reconnecting" : "connecting";
  let socket: WebSocket;
  try {
    socket = new WebSocket(buildRobotWebSocketUrl(entry.path));
  } catch {
    entry.connectionState.value = "error";
    scheduleReconnect(entry);
    return;
  }
  entry.socket = socket;

  socket.onopen = () => {
    if (entry.closed || entry.generation !== generation || entry.socket !== socket) return;
    const isReconnect = entry.reconnectAttempts.value > 0;
    entry.connectionState.value = "connected";
    entry.reconnectAttempts.value = 0;
    if (isReconnect) {
      entry.subscribers.forEach((subscriber) => void subscriber.refreshSnapshot());
    }
  };

  socket.onmessage = (message) => {
    if (entry.closed || entry.generation !== generation || entry.socket !== socket) return;
    try {
      const payload: unknown = typeof message.data === "string" ? JSON.parse(message.data) : null;
      if (!isStatusEvent(payload, entry.path)) return;
      if (payload.type.endsWith("_snapshot")) {
        assertMockRobotContract(payload.data, `${entry.path}#${payload.type}`);
      }
      entry.subscribers.forEach((subscriber) => {
        if (payload.type.endsWith("_snapshot")) subscriber.onSnapshot(payload);
        else subscriber.onEvent(payload);
      });
    } catch (error) {
      const contractError = error instanceof RobotContractError
        ? error
        : new RobotContractError("ROBOT_API_INVALID_ENVELOPE", entry.path, "机器人 WebSocket 消息无法解析");
      reportContractError(entry, contractError);
    }
  };

  socket.onerror = () => {
    if (entry.generation === generation && entry.socket === socket) {
      entry.connectionState.value = "error";
    }
  };

  socket.onclose = () => {
    if (entry.generation !== generation || entry.socket !== socket) return;
    entry.socket = null;
    if (entry.closed || entry.subscribers.size === 0) {
      entry.connectionState.value = "disconnected";
      return;
    }
    scheduleReconnect(entry);
  };
}

function getSharedSocket(path: string): SharedRobotSocket {
  const existing = sharedSockets.get(path);
  if (existing) return existing;
  const entry: SharedRobotSocket = {
    path,
    socket: null,
    subscribers: new Set(),
    connectionState: ref("idle"),
    reconnectAttempts: ref(0),
    reconnectTimer: null,
    generation: 0,
    closed: false,
    securityBlocked: false,
  };
  sharedSockets.set(path, entry);
  return entry;
}

function releaseSharedSocket(entry: SharedRobotSocket, subscriber: RobotWebSocketOptions) {
  entry.subscribers.delete(subscriber);
  if (entry.subscribers.size > 0) return;
  entry.closed = true;
  entry.generation += 1;
  if (entry.reconnectTimer !== null) {
    window.clearTimeout(entry.reconnectTimer);
    entry.reconnectTimer = null;
  }
  const socket = entry.socket;
  entry.socket = null;
  socket?.close(1000, "page unmounted");
  entry.connectionState.value = "disconnected";
  sharedSockets.delete(entry.path);
}

export function useRobotWebSocket(options: RobotWebSocketOptions) {
  const entry = getSharedSocket(options.path);
  entry.closed = false;
  entry.subscribers.add(options);
  connectSharedSocket(entry);

  function reconnect() {
    if (entry.closed || entry.securityBlocked) return;
    entry.generation += 1;
    if (entry.reconnectTimer !== null) {
      window.clearTimeout(entry.reconnectTimer);
      entry.reconnectTimer = null;
    }
    const socket = entry.socket;
    entry.socket = null;
    socket?.close(1000, "manual reconnect");
    entry.reconnectAttempts.value = 1;
    connectSharedSocket(entry);
  }

  function disconnect() {
    releaseSharedSocket(entry, options);
  }

  onBeforeUnmount(() => releaseSharedSocket(entry, options));

  return {
    connectionState: readonly(entry.connectionState),
    reconnectAttempts: readonly(entry.reconnectAttempts),
    reconnect,
    disconnect,
  };
}

export function getActiveRobotWebSocketCount(path?: string): number {
  if (path) return sharedSockets.has(path) ? 1 : 0;
  return sharedSockets.size;
}
