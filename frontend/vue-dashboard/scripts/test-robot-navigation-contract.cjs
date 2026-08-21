const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const ts = require("typescript");

const root = path.resolve(__dirname, "..");
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), "utf8");

function compile(relativePath, customRequire = require) {
  const output = ts.transpileModule(read(relativePath), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
      strict: true,
    },
    fileName: path.join(root, relativePath),
  }).outputText;
  const module = { exports: {} };
  new Function("exports", "module", "require", output)(module.exports, module, customRequire);
  return module.exports;
}

const contract = compile("src/api/robotContractPolicy.ts");
const coordinates = compile("src/utils/robotMapCoordinates.ts");
const routePolicy = compile("src/utils/robotNavigationPolicy.ts");
const pointCloudPolicy = compile(
  "src/composables/robotPointCloudPolicy.ts",
  (request) => {
    if (request === "../api/robotContractPolicy") return contract;
    return require(request);
  },
);

const viewport = { ...coordinates.DEFAULT_ROBOT_MAP_VIEWPORT, zoom: 1.4, panX: 37, panY: -19 };
for (const world of [{ x: 0, y: 0 }, { x: -4.25, y: 2.5 }, { x: 5.8, y: -3.2 }]) {
  const screen = coordinates.worldToRobotMapScreen(world, viewport);
  const restored = coordinates.robotMapScreenToWorld(screen, viewport);
  assert.ok(Math.abs(restored.x - world.x) < 1e-9, "world/screen X conversion must be reversible");
  assert.ok(Math.abs(restored.y - world.y) < 1e-9, "world/screen Y conversion must be reversible");
}
assert.equal(coordinates.clampRobotMapZoom(99), 3);
assert.equal(coordinates.clampRobotMapZoom(-1), 0.6);

const points = [
  {
    point_id: "p1", map_id: "m1", name: "A", point_type: "patrol", status: "valid",
    x: 0, y: 0, yaw: 0, metadata: {}, created_at: "", updated_at: "",
    provider: "mock", real_motion_enabled: false,
  },
  {
    point_id: "p2", map_id: "m1", name: "B", point_type: "patrol", status: "valid",
    x: 1, y: 1, yaw: 0, metadata: {}, created_at: "", updated_at: "",
    provider: "mock", real_motion_enabled: false,
  },
  {
    point_id: "p3", map_id: "m1", name: "C", point_type: "patrol", status: "invalid",
    x: 2, y: 2, yaw: 0, metadata: {}, created_at: "", updated_at: "",
    provider: "mock", real_motion_enabled: false,
  },
];
assert.equal(routePolicy.validateRobotRoutePointIds(["p1"], points).valid, true);
assert.equal(routePolicy.validateRobotRoutePointIds(["p1", "p1"], points).code, "ROUTE_POINT_DUPLICATED");
assert.equal(routePolicy.validateRobotRoutePointIds(["p1", "p3"], points).code, "ROUTE_POINT_INVALID");

const validFrame = {
  type: "point_cloud_frame",
  sequence: 1,
  timestamp: "2026-07-23T00:00:00Z",
  provider: "mock",
  real_motion_enabled: false,
  frame_id: "mock_lidar",
  coordinate_frame: "map",
  scenario: "classroom_default",
  point_count: 2,
  points: [[0, 0, 0, 0.4], [1, 2, 0.2, 0.8]],
  robot_pose: { x: 0, y: 0, z: 0, yaw: 0 },
  target_pose: null,
  navigation_state: "idle",
  control_owner: "NONE",
};
assert.equal(pointCloudPolicy.validateRobotPointCloudMessage(validFrame).type, "point_cloud_frame");
assert.throws(
  () => pointCloudPolicy.validateRobotPointCloudMessage({ ...validFrame, provider: "real" }),
  (error) => error.code === "ROBOT_INTERFACE_SAFETY_CONTRACT_VIOLATION",
);
assert.throws(
  () => pointCloudPolicy.validateRobotPointCloudMessage({ ...validFrame, real_motion_enabled: true }),
  (error) => error.code === "ROBOT_INTERFACE_SAFETY_CONTRACT_VIOLATION",
);
assert.throws(
  () => pointCloudPolicy.validateRobotPointCloudMessage({ ...validFrame, point_count: 3 }),
  (error) => error.code === "ROBOT_API_INVALID_ENVELOPE",
);
assert.throws(
  () => pointCloudPolicy.validateRobotPointCloudMessage({
    ...validFrame,
    points: [[Number.NaN, 0, 0, 1], [1, 2, 0.2, 0.8]],
  }),
  (error) => error.code === "ROBOT_API_INVALID_ENVELOPE",
);

const routing = read("src/composables/useHashRouting.ts");
const nav = read("src/components/layout/PrimaryNav.vue");
const workspaceNav = read("src/components/robot/RobotWorkspaceNav.vue");
const app = read("src/App.vue");
const api = read("src/api/robotNavigationApi.ts");
const navigationSocket = read("src/composables/useRobotWebSocket.ts");
const pointCloudSocket = read("src/composables/useRobotPointCloud.ts");
const navigationPage = read("src/views/RobotNavigationPage.vue");
const taskPanel = read("src/components/robot/NavigationTaskPanel.vue");
const threeViewer = read("src/components/robot/PointCloudViewer.vue");

assert.match(routing, /"robot-navigation": "#\/robot-navigation"/);
assert.doesNotMatch(nav, /label: "建图巡航"/);
assert.match(workspaceNav, /label: "建图巡航"/);
assert.match(app, /activePage === 'robot-navigation'/);
for (const endpoint of [
  "/robot/navigation/mapping/start",
  "/robot/navigation/mapping/stop",
  "/robot/navigation/maps/preview",
  "/robot/navigation/maps/save",
  "/robot/navigation/points",
  "/robot/navigation/routes",
  "/manual-acquire",
  "/manual-release",
]) {
  assert.ok(api.includes(endpoint), `REST client is missing ${endpoint}`);
}
assert.match(api, /request_id/);
assert.doesNotMatch(api, /8090/);
assert.match(navigationSocket, /securityBlocked/);
assert.match(navigationSocket, /mock safety contract violation/);
assert.match(pointCloudSocket, /buildRobotWebSocketUrl\("\/ws\/robot\/point-cloud"\)/);
assert.match(pointCloudSocket, /securityBlocked/);
assert.match(threeViewer, /BufferGeometry/);
assert.match(threeViewer, /\.dispose\(\)/);
assert.match(navigationPage, /real_motion_enabled=false/);
assert.match(taskPanel, /释放控制权后不会自动恢复/);

const scopedSources = [
  api,
  navigationPage,
  taskPanel,
  read("src/composables/useRobotNavigation.ts"),
].join("\n");
assert.doesNotMatch(scopedSources, /robot_service\.move|cmd_vel|linear_velocity|angular_velocity/);

console.log("ROBOT_NAVIGATION_CONTRACT_TESTS_OK");
