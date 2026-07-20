const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const ts = require("typescript");

const sourcePath = path.resolve(__dirname, "../src/composables/go2VideoBridgePolicy.ts");
const source = fs.readFileSync(sourcePath, "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020,
    strict: true,
  },
  fileName: sourcePath,
});
const moduleUnderTest = { exports: {} };
new Function("exports", "module", "require", compiled.outputText)(
  moduleUnderTest.exports,
  moduleUnderTest,
  require,
);

const {
  deriveVideoStreamState,
  getRecoveryDelay,
  normalizeGo2BridgeStatus,
} = moduleUnderTest.exports;

const legacy = normalizeGo2BridgeStatus({
  success: true,
  data: {
    connectionMode: "Go2 STA / WebRTC",
    robotIp: "192.168.8.248",
    connected: true,
    hasFrame: true,
    captureFps: 8.2,
    latestFrame: {
      capturedAt: "2026-07-19T14:00:00+08:00",
      width: 1280,
      height: 720,
    },
  },
});
assert.equal(legacy.apiVersion, null);
assert.equal(legacy.data.resolution.width, 1280);
assert.equal(legacy.data.source.networkMode, "STA");
assert.equal(deriveVideoStreamState(legacy.data), "ready");

const stalled = normalizeGo2BridgeStatus({
  success: true,
  ok: true,
  apiVersion: "1",
  serviceId: "go2-wireless-camera",
  data: {
    serviceState: "running",
    videoState: "stalled",
    connected: true,
    hasFrame: false,
    lastErrorCode: "FRAME_STALLED",
    lastError: "视频帧已停止更新",
  },
});
assert.equal(stalled.data.error.code, "FRAME_STALLED");
assert.equal(deriveVideoStreamState(stalled.data), "stalled");

assert.equal(normalizeGo2BridgeStatus(null), null);
assert.equal(getRecoveryDelay(1, [2000, 4000, 8000]), 2000);
assert.equal(getRecoveryDelay(3, [2000, 4000, 8000]), 8000);
assert.equal(getRecoveryDelay(99, [2000, 4000, 8000]), 8000);

console.log("GO2_VIDEO_POLICY_TESTS_OK");
