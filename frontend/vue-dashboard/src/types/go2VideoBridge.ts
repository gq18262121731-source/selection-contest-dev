export type BridgeServiceState = "unknown" | "checking" | "offline" | "starting" | "online" | "error";

export type VideoStreamState = "unknown" | "connecting" | "ready" | "no-frame" | "stalled" | "error";

export type Go2VideoErrorCode =
  | "ROBOT_UNREACHABLE"
  | "WEBRTC_CONNECT_FAILED"
  | "WEBRTC_DISCONNECTED"
  | "NO_FRAME_TIMEOUT"
  | "FRAME_STALLED"
  | "JPEG_ENCODE_FAILED"
  | "STREAM_INTERNAL_ERROR"
  | "RECONNECTING"
  | string;

export type Go2BridgeError = {
  code: Go2VideoErrorCode;
  message: string | null;
};

export type Go2BridgeResolution = {
  width: number;
  height: number;
};

export type Go2BridgeSource = {
  device: string;
  networkMode: string;
  transport: string;
  robotIp: string;
};

export type Go2BridgeStatus = {
  serviceState: string;
  videoState: string;
  startedAt: string | null;
  connectionMode: string;
  robotIp: string;
  connected: boolean;
  hasFrame: boolean;
  lastFrameAt: string | null;
  frameAgeMs: number | null;
  frameCount: number;
  captureFps: number;
  fps: number;
  resolution: Go2BridgeResolution | null;
  source: Go2BridgeSource | null;
  clientCount: number;
  errorCount: number;
  reconnectCount: number;
  lastErrorCode: Go2VideoErrorCode | null;
  lastError: string | null;
  error: Go2BridgeError | null;
};

export type Go2BridgeStatusEnvelope = {
  success: boolean;
  ok: boolean;
  apiVersion: string | null;
  serviceVersion: string | null;
  serviceId: string | null;
  timestamp: string | null;
  data: Go2BridgeStatus;
};

export type Go2BridgeDiagnostics = {
  updatedAt: Date | null;
  lastFrameAt: Date | null;
  frameAgeMs: number | null;
  fps: number;
  resolution: string;
  connectionMode: string;
  robotIp: string;
  reconnectCount: number;
  serviceVersion: string;
};
