import type {
  Go2BridgeStatus,
  Go2BridgeStatusEnvelope,
  VideoStreamState,
} from "../types/go2VideoBridge";

type UnknownRecord = Record<string, unknown>;

function asRecord(value: unknown): UnknownRecord | null {
  return value !== null && typeof value === "object" ? value as UnknownRecord : null;
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function asNullableString(value: unknown): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

function asNumber(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function asNullableNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function normalizeResolution(value: unknown): Go2BridgeStatus["resolution"] {
  const record = asRecord(value);
  if (!record) return null;
  const width = asNumber(record.width);
  const height = asNumber(record.height);
  return width > 0 && height > 0 ? { width, height } : null;
}

function normalizeSource(value: unknown): Go2BridgeStatus["source"] {
  const record = asRecord(value);
  if (!record) return null;
  return {
    device: asString(record.device, "Go2"),
    networkMode: asString(record.networkMode),
    transport: asString(record.transport, "WebRTC"),
    robotIp: asString(record.robotIp),
  };
}

export function normalizeGo2BridgeStatus(payload: unknown): Go2BridgeStatusEnvelope | null {
  const envelope = asRecord(payload);
  const rawData = asRecord(envelope?.data);
  if (!envelope || !rawData) return null;

  const latestFrame = asRecord(rawData.latestFrame);
  const error = asRecord(rawData.error);
  const legacyResolution = latestFrame
    ? normalizeResolution({ width: latestFrame.width, height: latestFrame.height })
    : null;
  const lastErrorCode = asNullableString(rawData.lastErrorCode ?? error?.code);
  const lastError = asNullableString(rawData.lastError ?? error?.message);
  const connectionMode = asString(rawData.connectionMode);
  const robotIp = asString(rawData.robotIp);
  const captureFps = asNumber(rawData.captureFps);

  return {
    success: envelope.success !== false,
    ok: envelope.ok !== false,
    apiVersion: asNullableString(envelope.apiVersion),
    serviceVersion: asNullableString(envelope.serviceVersion),
    serviceId: asNullableString(envelope.serviceId),
    timestamp: asNullableString(envelope.timestamp),
    data: {
      serviceState: asString(rawData.serviceState, "running"),
      videoState: asString(rawData.videoState),
      startedAt: asNullableString(rawData.startedAt),
      connectionMode,
      robotIp,
      connected: rawData.connected === true,
      hasFrame: rawData.hasFrame === true,
      lastFrameAt: asNullableString(rawData.lastFrameAt ?? latestFrame?.capturedAt),
      frameAgeMs: asNullableNumber(rawData.frameAgeMs),
      frameCount: asNumber(rawData.frameCount),
      captureFps,
      fps: asNumber(rawData.fps, captureFps),
      resolution: normalizeResolution(rawData.resolution) ?? legacyResolution,
      source: normalizeSource(rawData.source) ?? {
        device: "Go2",
        networkMode: connectionMode.includes("STA") ? "STA" : connectionMode.includes("AP") ? "AP" : "",
        transport: "WebRTC",
        robotIp,
      },
      clientCount: asNumber(rawData.clientCount),
      errorCount: asNumber(rawData.errorCount),
      reconnectCount: asNumber(rawData.reconnectCount),
      lastErrorCode,
      lastError,
      error: lastErrorCode ? { code: lastErrorCode, message: lastError } : null,
    },
  };
}

export function deriveVideoStreamState(status: Go2BridgeStatus): VideoStreamState {
  if (status.hasFrame) return "ready";
  if (status.videoState === "stalled" || status.lastErrorCode === "FRAME_STALLED") return "stalled";
  if (status.connected || status.videoState === "no-frame") return "no-frame";
  if (status.lastErrorCode && status.lastErrorCode !== "RECONNECTING") return "error";
  return "connecting";
}

export function getRecoveryDelay(failureCount: number, delays: readonly number[]): number {
  if (delays.length === 0) return 30_000;
  const index = Math.min(Math.max(0, failureCount - 1), delays.length - 1);
  return delays[index] ?? delays[delays.length - 1] ?? 30_000;
}
