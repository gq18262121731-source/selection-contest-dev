const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const ts = require("typescript");

const root = path.resolve(__dirname, "..");
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), "utf8");

function compile(relativePath) {
  const output = ts.transpileModule(read(relativePath), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
      strict: true,
    },
    fileName: path.join(root, relativePath),
  }).outputText;
  const module = { exports: {} };
  new Function("exports", "module", "require", output)(module.exports, module, require);
  return module.exports;
}

const policy = compile("src/utils/robotEmergencyPolicy.ts");

assert.equal(
  policy.parseRobotEmergencyIncidentId("#/robot-emergency?incidentId=fall_2026-07-23%3A001"),
  "fall_2026-07-23:001",
);
assert.equal(policy.parseRobotEmergencyIncidentId("#/robot-emergency"), null);
assert.equal(policy.parseRobotEmergencyIncidentId("#/robot-emergency?incidentId=%20"), null);
assert.equal(policy.parseRobotEmergencyIncidentId("#/robot-emergency?incidentId=bad%2Fid"), null);
assert.equal(
  policy.buildRobotEmergencyHash("incident_001"),
  "#/robot-emergency?incidentId=incident_001",
);
assert.throws(() => policy.buildRobotEmergencyHash("../unsafe"));

const alarm = {
  id: "alarm-1",
  device_mac: "CAMERA",
  alarm_type: "fall_detected",
  alarm_level: 4,
  alarm_layer: "community",
  message: "fall",
  acknowledged: false,
  created_at: "2026-07-23T00:00:00Z",
  anomaly_probability: 0.93,
  metadata: {
    event: {
      event_type: "fall_confirmed",
      incident_id: "incident-1",
      camera_id: "cam-1",
      area_id: "living-room",
      area_name: "客厅",
    },
  },
};
assert.deepEqual(policy.extractRobotAlarmExtension(alarm), {
  incident_id: "incident-1",
  robot_task_id: null,
  alarm_id: "alarm-1",
  camera_id: "cam-1",
  area_id: "living-room",
  area_name: "客厅",
  event_type: "fall_confirmed",
  occurred_at: "2026-07-23T00:00:00Z",
  risk_level: null,
  fall_probability: 0.93,
});
assert.equal(
  policy.extractRobotAlarmExtension({ ...alarm, metadata: { event: { event_type: "fall_confirmed" } } }),
  null,
);

const safeCase = {
  dialogue_intent: "safe_response",
  execution_state: "waiting_admin_confirmation",
  acknowledged_by: "admin-1",
  control_owner: "NONE",
};
const safeInterlock = {
  passed: true,
  blocked_by: [],
};
assert.equal(policy.canResolveEmergencyReturn(safeCase, safeInterlock).allowed, true);
assert.deepEqual(
  policy.canResolveEmergencyReturn({ ...safeCase, control_owner: "MANUAL" }, safeInterlock).blockedBy,
  ["MANUAL_CONTROL_ACTIVE"],
);
assert.ok(
  policy.canResolveEmergencyReturn(
    { ...safeCase, dialogue_intent: "need_help", execution_state: "help_requested" },
    safeInterlock,
  ).blockedBy.includes("SAFE_RESPONSE_REQUIRED"),
);

const api = read("src/api/robotEmergencyApi.ts");
const composable = read("src/composables/useRobotEmergency.ts");
const routing = read("src/composables/useHashRouting.ts");
const app = read("src/App.vue");
const nav = read("src/components/layout/PrimaryNav.vue");
const shell = read("src/components/layout/AppShell.vue");
const overlay = read("src/components/layout/FallAlertOverlay.vue");
const page = read("src/views/RobotEmergencyPage.vue");
const realtime = read("src/components/robot/EmergencyRealtimeBridge.vue");
const dialoguePanel = read("src/components/robot/EmergencyDialoguePanel.vue");
const presentation = read("src/utils/robotPresentation.ts");

for (const endpoint of [
  "/acknowledge",
  "/dispatch",
  "/resume",
  "/escalate",
  "/resolve-and-return",
  "/mock/dialogue/start",
  "/mock/return/complete",
  "/dialogue",
]) {
  assert.ok(api.includes(endpoint), `emergency REST client is missing ${endpoint}`);
}
assert.match(api, /assertMockRobotContract/);
assert.match(api, /validateEmergencyBundle/);
assert.match(composable, /Promise\.allSettled/);
assert.match(composable, /AbortController/);
assert.match(composable, /activeOperation/);
assert.match(composable, /SAFE_RETURN_PRECONDITION_FAILED/);
assert.match(realtime, /useRobotWebSocket/);
assert.match(realtime, /\/ws\/robot\/emergency\//);
assert.match(routing, /parseRobotEmergencyIncidentId/);
assert.match(routing, /allowedPages\.value\.includes\("robot-emergency"\)/);
assert.match(routing, /role === "family"\) return \["family"\]/);
assert.match(app, /activePage === 'robot-emergency'/);
assert.doesNotMatch(nav, /page:\s*"robot-emergency"/);
assert.match(overlay, /进入应急处置/);
assert.match(overlay, /我已知晓/);
assert.match(overlay, /应急任务尚未建立/);
assert.match(shell, /sessionStorage\.setItem/);
assert.match(shell, /ackAlarm\(current\.id\)/);
assert.match(shell, /alarmReconnectTimer/, "Alarm reconnect timer must be tracked");
assert.match(shell, /clearTimeout\(alarmReconnectTimer\)/, "Alarm reconnect timer must be cleared");
assert.match(page, /Go2VideoPanel/);
assert.doesNotMatch(page, /camera.*(?:stream|snapshot)|bbox/i);
assert.match(page, /MOCK_ENVIRONMENT_NOTICE/);
assert.match(
  presentation,
  /当前为模拟导航环境，真实机器人运动控制已禁用。/,
);
assert.match(
  dialoguePanel,
  /当前语音识别、对话理解和语音合成为模拟结果。/,
);

const scopedSources = [api, composable, page, shell, overlay].join("\n");
assert.doesNotMatch(scopedSources, /:8090|robot_service\.move|cmd_vel|angular_velocity|target_state|robot_pose/);
assert.doesNotMatch(api, /provider\s*:|real_motion_enabled\s*:/);
assert.match(page, /provider=mock · real_motion_enabled=false/);

console.log("ROBOT_EMERGENCY_CONTRACT_TESTS_OK");
