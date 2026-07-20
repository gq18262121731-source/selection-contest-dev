export const GO2_VIDEO_BRIDGE = Object.freeze({
  statusUrl: "http://127.0.0.1:8093/status",
  streamUrl: "http://127.0.0.1:8093/stream.mjpg",
  launchUri: "go2bridge://start",
  requestTimeoutMs: 1500,
  videoLoadTimeoutMs: 8000,
  startupPollIntervalMs: 750,
  startupTimeoutMs: 15_000,
  healthyPollIntervalMs: 10_000,
  recoveryPollDelaysMs: [2000, 4000, 8000, 15_000, 30_000] as const,
});
