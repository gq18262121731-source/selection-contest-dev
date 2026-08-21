const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), "utf8");

const routing = read("src/composables/useHashRouting.ts");
const navigation = read("src/components/layout/PrimaryNav.vue");
const workspaceNavigation = read("src/components/robot/RobotWorkspaceNav.vue");
const shell = read("src/components/layout/AppShell.vue");
const app = read("src/App.vue");
const api = read("src/api/robotNavigationApi.ts");
const websocket = read("src/composables/useRobotWebSocket.ts");
const statusComposable = read("src/composables/useRobotStatus.ts");
const statusPage = read("src/views/RobotStatusPage.vue");
const robotPresentation = read("src/utils/robotPresentation.ts");
const videoComposable = read("src/composables/useGo2VideoBridge.ts");
const videoPanel = read("src/components/robot/Go2VideoPanel.vue");
const followPage = read("src/views/RobotFollowPage.vue");
const taskCenterPage = read("src/views/RobotTaskCenterPage.vue");
const ts = require("typescript");

const policyPath = path.join(root, "src/api/robotContractPolicy.ts");
const policyCompiled = ts.transpileModule(read("src/api/robotContractPolicy.ts"), {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020,
    strict: true,
  },
  fileName: policyPath,
});
const policyModule = { exports: {} };
new Function("exports", "module", "require", policyCompiled.outputText)(
  policyModule.exports,
  policyModule,
  require,
);
const { validateRobotEnvelope, RobotContractError } = policyModule.exports;

const validEnvelope = validateRobotEnvelope({
  success: true,
  code: "OK",
  message: "ok",
  timestamp: "2026-07-23T00:00:00Z",
  data: { provider: "mock", real_motion_enabled: false },
}, "/robot/navigation/state");
assert.equal(validEnvelope.data.provider, "mock");
assert.throws(
  () => validateRobotEnvelope({
    success: true,
    code: "OK",
    message: "ok",
    timestamp: "2026-07-23T00:00:00Z",
    data: { provider: "real", real_motion_enabled: false },
  }, "/robot/navigation/state"),
  (error) => error instanceof RobotContractError
    && error.code === "ROBOT_INTERFACE_SAFETY_CONTRACT_VIOLATION",
);
assert.throws(
  () => validateRobotEnvelope({
    success: true,
    code: "OK",
    message: "ok",
    timestamp: "2026-07-23T00:00:00Z",
    data: { provider: "mock", real_motion_enabled: true },
  }, "/robot/navigation/state"),
  (error) => error instanceof RobotContractError
    && error.code === "ROBOT_INTERFACE_SAFETY_CONTRACT_VIOLATION",
);

assert.match(routing, /"robot-status": "#\/robot-status"/, "Hash route must expose #/robot-status");
assert.match(
  routing,
  /role === "family"\) return \["family"\]/,
  "Family role must remain restricted to the family page",
);
assert.match(
  routing,
  /"robot-tasks", "robot-status", "robot-navigation", "robot-follow"/,
  "Community/admin allow-list must include robot-status",
);
assert.match(navigation, /label: "机器人任务"/, "Primary navigation must retain one robot workspace entry");
for (const page of ["robot-status", "robot-navigation", "robot-follow"]) {
  assert.doesNotMatch(
    navigation,
    new RegExp(`page:\\s*"${page}"\\s+as PageKey`),
    `${page} must not remain a separate primary navigation entry`,
  );
}
for (const [page, label] of [
  ["robot-tasks", "机器人任务"],
  ["robot-status", "机器人状态"],
  ["robot-navigation", "建图巡航"],
  ["robot-follow", "机器狗跟随"],
]) {
  assert.match(workspaceNavigation, new RegExp(`page:\\s*"${page}"`));
  assert.match(workspaceNavigation, new RegExp(`label:\\s*"${label}"`));
}
assert.match(workspaceNavigation, /aria-current/, "Robot workspace navigation must expose the active page");
assert.match(shell, /<RobotWorkspaceNav/, "App shell must render the robot workspace navigation");
assert.match(shell, /"robot-emergency"/, "Emergency detail must remain inside the robot workspace context");
assert.match(app, /activePage === 'robot-status'/, "App must render RobotStatusPage for robot-status");

for (const endpoint of [
  "/robot/status",
  "/robot/status/diagnostics",
  "/robot/navigation/capabilities",
  "/robot/navigation/state",
]) {
  assert.ok(api.includes(endpoint), `REST client is missing ${endpoint}`);
}
assert.match(api, /requestJson/, "Robot REST client must reuse the existing requestJson helper");
assert.match(api, /validateRobotEnvelope/, "Runtime robot contract validation is required");
assert.doesNotMatch(api, /8090/, "Robot REST client must never address go2-gateway:8090");

assert.match(websocket, /new Map<string, SharedRobotSocket>/, "WebSocket connections must be shared by path");
assert.match(websocket, /sharedSockets\.delete/, "Last subscriber must release the shared connection");
assert.match(websocket, /socket\?\.close\(1000, "page unmounted"\)/, "Unmount must close the WebSocket");
assert.match(websocket, /RETRY_DELAYS_MS/, "Reconnect must use bounded backoff");
assert.match(websocket, /refreshSnapshot/, "Reconnect must refresh the REST snapshot");
assert.doesNotMatch(websocket, /8090\/ws/, "WebSocket client must not hardcode an 8090 connection");

assert.match(statusComposable, /path: "\/ws\/robot\/status"/, "Status page must use one status WebSocket path");
assert.match(statusComposable, /\.slice\(0, 20\)/, "Status timeline must remain bounded at 20 entries");
assert.match(statusComposable, /Promise\.allSettled/, "Four REST cards must degrade independently");
assert.match(statusPage, /MOCK_ENVIRONMENT_NOTICE/, "Status page must render the shared Mock warning");
assert.match(
  robotPresentation,
  /当前为模拟导航环境，真实机器人运动控制已禁用。/,
  "The shared Mock warning must use the frozen competition wording",
);
assert.match(statusPage, /real_motion_enabled=false/, "Real motion disabled invariant must be visible");
assert.match(statusPage, /暂无当前机器人任务/, "Current-task empty state must be present");

assert.match(videoPanel, /useGo2VideoBridge/, "Video panel must reuse the existing video bridge composable");
assert.match(videoComposable, /onBeforeUnmount/, "Video bridge must clean up on unmount");
assert.match(videoComposable, /clearPollTimer\(\)/, "Video bridge poll timer must be cleared");
assert.match(videoComposable, /activeRequest\?\.abort\(\)/, "Video bridge request must be aborted on unmount");
assert.match(followPage, /function requestFollowTask\(\)/, "Follow requests must be recorded explicitly");
assert.match(followPage, /function cancelFollowRequest\(\)/, "Local follow requests must be reversible");
assert.match(followPage, /请求未发送至机器人/, "Follow request state must not claim robot execution");
assert.doesNotMatch(followPage, />开始跟随</, "The page must not present a local marker as a start control");

const capabilityPolicyPath = path.join(root, "src/utils/robotCapabilityStatus.ts");
const capabilityPolicyCompiled = ts.transpileModule(read("src/utils/robotCapabilityStatus.ts"), {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020,
    strict: true,
  },
  fileName: capabilityPolicyPath,
});
const capabilityPolicyModule = { exports: {} };
new Function("exports", "module", "require", capabilityPolicyCompiled.outputText)(
  capabilityPolicyModule.exports,
  capabilityPolicyModule,
  require,
);
const { normalizeRobotCapabilityStatus } = capabilityPolicyModule.exports;
assert.equal(normalizeRobotCapabilityStatus(undefined).status, "UNKNOWN");
assert.equal(normalizeRobotCapabilityStatus(null).status, "UNKNOWN");
assert.equal(normalizeRobotCapabilityStatus(true).status, "READY");
assert.equal(normalizeRobotCapabilityStatus(false).status, "NOT_READY");

const followPolicyPath = path.join(root, "src/utils/robotFollowPolicy.ts");
const followPolicyCompiled = ts.transpileModule(read("src/utils/robotFollowPolicy.ts"), {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020,
    strict: true,
  },
  fileName: followPolicyPath,
});
const followPolicyModule = { exports: {} };
new Function("exports", "module", "require", followPolicyCompiled.outputText)(
  followPolicyModule.exports,
  followPolicyModule,
  require,
);
const {
  INITIAL_ROBOT_FOLLOW_TASK,
  recordLocalFollowRequest,
  clearLocalFollowRequest,
  applyRobotFollowState,
} = followPolicyModule.exports;
const requestedFollow = recordLocalFollowRequest(new Date("2026-07-27T00:00:00Z"));
assert.equal(requestedFollow.state, "REQUESTED");
assert.equal(requestedFollow.source, "local-intent");
assert.match(requestedFollow.reason, /尚未发送至机器人/);
assert.equal(clearLocalFollowRequest().state, "IDLE");
assert.throws(
  () => applyRobotFollowState(INITIAL_ROBOT_FOLLOW_TASK, "EXECUTING", "invalid"),
  /Invalid robot follow transition/,
);

assert.match(taskCenterPage, /taskListController\?\.abort\(\)/, "Task list refresh must cancel stale requests");
assert.match(taskCenterPage, /taskDetailController\?\.abort\(\)/, "Task selection must cancel stale detail requests");
assert.match(
  taskCenterPage,
  /requestId !== taskDetailRequestId[\s\S]*selectedTaskId\.value !== taskId/,
  "Task detail commits must verify both request generation and selected task",
);
assert.match(taskCenterPage, /未收到机器人运动状态数据/, "Missing motion state must explain UNKNOWN");
assert.doesNotMatch(
  taskCenterPage,
  /motionReady\s*\?\s*["']Ready["']/,
  "Missing motion state must never fall back to Ready",
);

const newSources = [
  "src/types/robot.ts",
  "src/api/robotNavigationApi.ts",
  "src/api/robotContractPolicy.ts",
  "src/composables/useRobotWebSocket.ts",
  "src/composables/useRobotStatus.ts",
  "src/views/RobotStatusPage.vue",
  "src/utils/robotCapabilityStatus.ts",
  "src/utils/robotFollowPolicy.ts",
].map(read).join("\n");
assert.doesNotMatch(newSources, /:\s*any\b|as\s+any\b|<any>/, "New robot status sources must not introduce any");

console.log("ROBOT_STATUS_CONTRACT_TESTS_OK");
