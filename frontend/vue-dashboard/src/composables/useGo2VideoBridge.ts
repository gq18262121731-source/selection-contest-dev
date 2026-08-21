import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { GO2_VIDEO_BRIDGE } from "../config/go2VideoBridge";
import type {
  BridgeServiceState,
  Go2BridgeDiagnostics,
  Go2BridgeStatusEnvelope,
  VideoStreamState,
} from "../types/go2VideoBridge";
import {
  deriveVideoStreamState,
  getRecoveryDelay,
  normalizeGo2BridgeStatus,
} from "./go2VideoBridgePolicy";

type BridgeViewState = "checking" | "offline" | "launching" | "connecting" | "ready" | "failed";
type VideoViewState = "connecting" | "online" | "error";

const ERROR_MESSAGES: Record<string, string> = {
  ROBOT_UNREACHABLE: "无法连接 Go2，请确认机器狗和桥接电脑处于同一 STA-L 网络。",
  WEBRTC_CONNECT_FAILED: "Go2 WebRTC 连接失败，请检查无线网络和设备密钥。",
  WEBRTC_DISCONNECTED: "Go2 WebRTC 连接已断开，系统正在自动重连。",
  NO_FRAME_TIMEOUT: "视频服务已连接 Go2，但尚未收到有效画面。",
  FRAME_STALLED: "视频帧已停止更新，系统正在自动恢复。",
  JPEG_ENCODE_FAILED: "视频帧编码失败，请查看本机视频服务日志。",
  RECONNECTING: "视频服务正在重新连接 Go2。",
};

export function useGo2VideoBridge() {
  const serviceState = ref<BridgeServiceState>("unknown");
  const videoStreamState = ref<VideoStreamState>("unknown");
  const statusEnvelope = ref<Go2BridgeStatusEnvelope | null>(null);
  const videoSource = ref<string>(GO2_VIDEO_BRIDGE.streamUrl);
  const bridgeServiceMessage = ref("正在检查本机视频桥接服务。");

  let mounted = false;
  let generation = 0;
  let failureCount = 0;
  let startupDeadline = 0;
  let pollTimer: number | null = null;
  let videoLoadTimer: number | null = null;
  let activeRequest: AbortController | null = null;
  let wasReady = false;

  const bridgeServiceState = computed<BridgeViewState>(() => {
    if (serviceState.value === "checking" || serviceState.value === "unknown") return "checking";
    if (serviceState.value === "starting") return "launching";
    if (serviceState.value === "offline") return "offline";
    if (serviceState.value === "error") return "failed";
    if (videoStreamState.value === "ready") return "ready";
    return "connecting";
  });

  const videoState = computed<VideoViewState>(() => {
    if (videoStreamState.value === "ready") return "online";
    if (["no-frame", "stalled", "error"].includes(videoStreamState.value)) return "error";
    return "connecting";
  });

  const bridgeServiceLabel = computed(() => {
    if (bridgeServiceState.value === "ready") return "视频画面已就绪";
    if (bridgeServiceState.value === "launching") return "正在启动视频服务";
    if (bridgeServiceState.value === "connecting") return "正在连接机器狗视频";
    if (bridgeServiceState.value === "failed") return "视频服务异常";
    if (bridgeServiceState.value === "offline") return "视频服务未启动";
    return "正在检查本机服务";
  });

  const bridgeButtonLabel = computed(() => {
    if (serviceState.value === "online") return "视频服务已运行";
    if (["checking", "starting", "unknown"].includes(serviceState.value)) return "正在等待视频服务";
    return "启动本机视频服务";
  });

  const bridgeButtonDisabled = computed(() =>
    ["checking", "starting", "online", "unknown"].includes(serviceState.value),
  );

  const videoStatusLabel = computed(() => {
    if (videoStreamState.value === "ready") return "视频已连接";
    if (videoStreamState.value === "stalled") return "视频已停顿";
    if (videoStreamState.value === "no-frame") return "等待视频帧";
    if (videoStreamState.value === "error") return "视频不可用";
    return "正在连接视频";
  });

  const videoErrorReason = computed(() => {
    if (window.location.protocol === "https:") {
      return "当前社区端使用 HTTPS，但本机视频源是 HTTP，浏览器可能已阻止混合内容。";
    }
    const status = statusEnvelope.value?.data;
    if (status?.lastErrorCode && ERROR_MESSAGES[status.lastErrorCode]) {
      return ERROR_MESSAGES[status.lastErrorCode];
    }
    if (status?.lastError) return status.lastError;
    return "未能从 127.0.0.1:8093 读取画面。系统会继续自动检查，也可以手动重新连接。";
  });

  const diagnostics = computed<Go2BridgeDiagnostics>(() => {
    const envelope = statusEnvelope.value;
    const status = envelope?.data;
    return {
      updatedAt: envelope?.timestamp ? new Date(envelope.timestamp) : null,
      lastFrameAt: status?.lastFrameAt ? new Date(status.lastFrameAt) : null,
      frameAgeMs: status?.frameAgeMs ?? null,
      fps: status?.fps ?? 0,
      resolution: status?.resolution ? `${status.resolution.width}×${status.resolution.height}` : "-",
      connectionMode: status?.connectionMode || "-",
      robotIp: status?.robotIp || "-",
      reconnectCount: status?.reconnectCount ?? 0,
      serviceVersion: envelope?.serviceVersion || "兼容模式",
    };
  });

  function clearPollTimer() {
    if (pollTimer !== null) window.clearTimeout(pollTimer);
    pollTimer = null;
  }

  function clearVideoLoadTimer() {
    if (videoLoadTimer !== null) window.clearTimeout(videoLoadTimer);
    videoLoadTimer = null;
  }

  function scheduleCheck(delayMs: number) {
    if (!mounted) return;
    clearPollTimer();
    pollTimer = window.setTimeout(() => void checkNow("scheduled"), delayMs);
  }

  function scheduleNextCheck(isHealthy: boolean) {
    if (isHealthy) {
      failureCount = 0;
      scheduleCheck(GO2_VIDEO_BRIDGE.healthyPollIntervalMs);
      return;
    }

    failureCount += 1;
    const isStarting = startupDeadline > Date.now();
    scheduleCheck(isStarting
      ? GO2_VIDEO_BRIDGE.startupPollIntervalMs
      : getRecoveryDelay(failureCount, GO2_VIDEO_BRIDGE.recoveryPollDelaysMs));
  }

  function refreshVideo() {
    clearVideoLoadTimer();
    videoStreamState.value = "connecting";
    videoSource.value = `${GO2_VIDEO_BRIDGE.streamUrl}?t=${Date.now()}`;
    videoLoadTimer = window.setTimeout(() => {
      if (videoStreamState.value === "connecting") {
        videoStreamState.value = "error";
        bridgeServiceMessage.value = "视频服务已有新帧，但当前页面未能建立 MJPEG 连接，系统将继续检查。";
        scheduleNextCheck(false);
      }
    }, GO2_VIDEO_BRIDGE.videoLoadTimeoutMs);
  }

  async function fetchStatus(requestGeneration: number): Promise<Go2BridgeStatusEnvelope | null> {
    activeRequest?.abort();
    const controller = new AbortController();
    activeRequest = controller;
    const timeout = window.setTimeout(() => controller.abort(), GO2_VIDEO_BRIDGE.requestTimeoutMs);
    try {
      const response = await fetch(GO2_VIDEO_BRIDGE.statusUrl, {
        cache: "no-store",
        headers: { Accept: "application/json" },
        signal: controller.signal,
      });
      if (!response.ok || requestGeneration !== generation) return null;
      return normalizeGo2BridgeStatus(await response.json());
    } catch {
      return null;
    } finally {
      window.clearTimeout(timeout);
      if (activeRequest === controller) activeRequest = null;
    }
  }

  async function checkNow(reason: "mount" | "scheduled" | "manual" | "visible" | "online" | "launch") {
    if (!mounted) return;
    clearPollTimer();
    const requestGeneration = ++generation;
    if (reason === "mount" || serviceState.value === "unknown") serviceState.value = "checking";
    const envelope = await fetchStatus(requestGeneration);
    if (!mounted || requestGeneration !== generation) return;

    if (!envelope) {
      statusEnvelope.value = null;
      const isStarting = startupDeadline > Date.now();
      serviceState.value = isStarting ? "starting" : "offline";
      videoStreamState.value = "error";
      bridgeServiceMessage.value = isStarting
        ? "已调用本机助手，正在等待 8093 视频服务启动。"
        : "未检测到本机视频服务。系统会在后台继续检查，也可以点击按钮重新启动。";
      scheduleNextCheck(false);
      return;
    }

    statusEnvelope.value = envelope;
    serviceState.value = "online";
    const nextVideoState = deriveVideoStreamState(envelope.data);
    videoStreamState.value = nextVideoState;

    if (nextVideoState === "ready") {
      bridgeServiceMessage.value = "视频服务与 Go2 画面均正常。自动恢复不会改变网页跟随标记。";
      if (!wasReady) refreshVideo();
      wasReady = true;
      startupDeadline = 0;
      scheduleNextCheck(true);
      return;
    }

    wasReady = false;
    const errorCode = envelope.data.lastErrorCode;
    bridgeServiceMessage.value = errorCode && ERROR_MESSAGES[errorCode]
      ? ERROR_MESSAGES[errorCode]
      : envelope.data.connected
        ? "视频服务已连接 Go2，正在等待新的画面。"
        : "视频服务已运行，正在连接 Go2 无线视频。";
    scheduleNextCheck(false);
  }

  function launchLocalBridge() {
    if (bridgeButtonDisabled.value) return;
    startupDeadline = Date.now() + GO2_VIDEO_BRIDGE.startupTimeoutMs;
    failureCount = 0;
    serviceState.value = "starting";
    videoStreamState.value = "connecting";
    bridgeServiceMessage.value = "已请求打开 Go2 本机助手，正在当前页面等待视频服务。";
    window.location.href = GO2_VIDEO_BRIDGE.launchUri;
    void checkNow("launch");
  }

  function retryVideo() {
    wasReady = false;
    refreshVideo();
    void checkNow("manual");
  }

  function markVideoOnline() {
    clearVideoLoadTimer();
    videoStreamState.value = "ready";
  }

  function markVideoError() {
    clearVideoLoadTimer();
    videoStreamState.value = "error";
    wasReady = false;
    bridgeServiceMessage.value = "当前页面视频连接异常，系统会在后台继续检查并自动恢复。";
    scheduleNextCheck(false);
  }

  function handleVisibilityChange() {
    if (document.visibilityState === "visible") void checkNow("visible");
  }

  function handleOnline() {
    failureCount = 0;
    void checkNow("online");
  }

  onMounted(() => {
    mounted = true;
    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener("online", handleOnline);
    void checkNow("mount");
  });

  onBeforeUnmount(() => {
    mounted = false;
    generation += 1;
    clearPollTimer();
    clearVideoLoadTimer();
    activeRequest?.abort();
    activeRequest = null;
    document.removeEventListener("visibilitychange", handleVisibilityChange);
    window.removeEventListener("online", handleOnline);
  });

  return {
    bridgeButtonDisabled,
    bridgeButtonLabel,
    bridgeServiceLabel,
    bridgeServiceMessage,
    bridgeServiceState,
    diagnostics,
    launchLocalBridge,
    markVideoError,
    markVideoOnline,
    retryVideo,
    serviceState,
    statusEnvelope,
    videoErrorReason,
    videoSource,
    videoState,
    videoStatusLabel,
    videoStreamState,
  };
}
