const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const { chromium } = require("playwright");

const frontendRoot = path.resolve(__dirname, "..");
const projectRoot = path.resolve(frontendRoot, "..", "..");
const manifestPath = path.join(
  projectRoot,
  "artifacts",
  "robot_mock_acceptance",
  "runtime",
  "process-manifest.json",
);
const durationMinutes = Number(process.env.ROBOT_SOAK_DURATION_MINUTES || "45");
const sampleIntervalSeconds = Math.max(5, Number(process.env.ROBOT_SOAK_SAMPLE_INTERVAL_SECONDS || "30"));
const cycleIntervalSeconds = Math.max(30, Number(process.env.ROBOT_SOAK_CYCLE_INTERVAL_SECONDS || "300"));
const ownsStack = process.env.ROBOT_SOAK_OWNS_STACK === "true";
const allowOwnedRestart = ownsStack
  && process.env.ROBOT_SOAK_RESTART_OWNED_STACK !== "false"
  && durationMinutes >= 5;
const artifactRoot = process.env.ROBOT_SOAK_ARTIFACT_DIR
  || path.join(projectRoot, "artifacts", "robot_mock_soak", new Date().toISOString().replace(/[:.]/g, "-"));
const screenshotRoot = path.join(artifactRoot, "screenshots");

assert.ok(Number.isFinite(durationMinutes) && durationMinutes > 0, "duration must be positive");
fs.mkdirSync(screenshotRoot, { recursive: true });

function readManifest() {
  return JSON.parse(fs.readFileSync(manifestPath, "utf8").replace(/^\uFEFF/, ""));
}

let manifest = readManifest();
let gatewayBase = manifest.gateway_base_url;
let backendBase = manifest.backend_base_url;
let frontendBase = manifest.frontend_base_url;
const apiBase = () => `${backendBase}/api/v1`;
const samples = [];
const consoleErrors = [];
const forbiddenRequests = [];
const operations = [];
const startedAt = Date.now();
const deadline = startedAt + durationMinutes * 60 * 1000;
let activeBrowser = null;
let activeContext = null;

function assertMockManifest() {
  assert.equal(manifest.provider, "mock");
  assert.equal(manifest.real_motion_enabled, false);
  assert.equal(manifest.robot_ip_contact_allowed, false);
  for (const base of [gatewayBase, backendBase, frontendBase]) {
    const url = new URL(base);
    assert.ok(["127.0.0.1", "localhost"].includes(url.hostname), `non-loopback service: ${base}`);
  }
  assert.notEqual(manifest.database, manifest.formal_database);
}

function validateMockContract(value, label) {
  const stack = [value];
  let declarations = 0;
  while (stack.length) {
    const current = stack.pop();
    if (!current || typeof current !== "object") continue;
    if (Object.prototype.hasOwnProperty.call(current, "provider")) {
      declarations += 1;
      assert.equal(current.provider, "mock", `${label}: provider`);
    }
    if (Object.prototype.hasOwnProperty.call(current, "real_motion_enabled")) {
      declarations += 1;
      assert.equal(current.real_motion_enabled, false, `${label}: real_motion_enabled`);
    }
    for (const child of Object.values(current)) {
      if (child && typeof child === "object") stack.push(child);
    }
  }
  assert.ok(declarations > 0, `${label}: missing Mock contract`);
}

async function jsonRequest(base, endpoint, { method = "GET", body, expected = [200, 201] } = {}) {
  const response = await fetch(`${base}${endpoint}`, {
    method,
    headers: body ? { "content-type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const payload = await response.json();
  assert.ok(expected.includes(response.status), `${method} ${endpoint}: ${response.status}`);
  if (response.ok && endpoint.includes("/robot/")) validateMockContract(payload, endpoint);
  return payload;
}

async function waitForBackend(timeoutMs = 30000) {
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    try {
      const response = await fetch(`${apiBase()}/robot/navigation/state`);
      if (response.ok) return;
    } catch {
      // Expected while an owned stack is restarting.
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error("backend did not recover");
}

function runPowerShell(scriptName, args = []) {
  const result = spawnSync(
    "powershell.exe",
    [
      "-NoProfile",
      "-ExecutionPolicy",
      "Bypass",
      "-File",
      path.join(projectRoot, "scripts", scriptName),
      ...args,
    ],
    { cwd: projectRoot, encoding: "utf8", timeout: 180000, maxBuffer: 4 * 1024 * 1024 },
  );
  if (result.status !== 0) throw new Error(`${scriptName}: ${result.stderr || result.stdout}`);
}

function processMetrics() {
  const ids = manifest.processes
    .map((entry) => Number(entry.pid))
    .filter((value) => Number.isInteger(value) && value > 0);
  if (!ids.length) return [];
  const command = [
    `$ids = @(${ids.join(",")})`,
    "$rows = Get-Process -Id $ids -ErrorAction SilentlyContinue | Select-Object Id,ProcessName,WorkingSet64,PrivateMemorySize64,HandleCount",
    "@($rows) | ConvertTo-Json -Compress",
  ].join("; ");
  const result = spawnSync(
    "powershell.exe",
    ["-NoProfile", "-Command", command],
    { encoding: "utf8", timeout: 10000 },
  );
  if (result.status !== 0 || !result.stdout.trim()) return [];
  const parsed = JSON.parse(result.stdout);
  return Array.isArray(parsed) ? parsed : [parsed];
}

async function installSession(context) {
  await context.addInitScript(() => {
    localStorage.setItem("ai_health_demo_session_token", "robot-mock-soak-token");
    const metrics = {
      activeWebSockets: 0,
      openedWebSockets: 0,
      closedWebSockets: 0,
      pointCloudFrames: 0,
      webglContexts: 0,
    };
    Object.defineProperty(window, "__robotSoakMetrics", { value: metrics });

    const NativeWebSocket = window.WebSocket;
    window.WebSocket = class TrackedWebSocket extends NativeWebSocket {
      constructor(...args) {
        super(...args);
        metrics.activeWebSockets += 1;
        metrics.openedWebSockets += 1;
        let closed = false;
        this.addEventListener("message", () => {
          if (String(this.url).includes("/ws/robot/point-cloud")) metrics.pointCloudFrames += 1;
        });
        this.addEventListener("close", () => {
          if (closed) return;
          closed = true;
          metrics.activeWebSockets = Math.max(0, metrics.activeWebSockets - 1);
          metrics.closedWebSockets += 1;
        });
      }
    };

    const nativeGetContext = HTMLCanvasElement.prototype.getContext;
    const contexts = new WeakSet();
    HTMLCanvasElement.prototype.getContext = function trackedGetContext(type, ...args) {
      const context = nativeGetContext.call(this, type, ...args);
      if (context && ["webgl", "webgl2", "experimental-webgl"].includes(String(type)) && !contexts.has(context)) {
        contexts.add(context);
        metrics.webglContexts += 1;
      }
      return context;
    };
  });
  await context.route("http://127.0.0.1:8093/**", (route) =>
    route.fulfill({ status: 503, contentType: "application/json", body: '{"status":"mock_video_unavailable"}' }),
  );
  await context.routeWebSocket(/\/ws\/alarms$/, (webSocket) => {
    webSocket.send(JSON.stringify({ type: "alarm_snapshot", data: [], timestamp: new Date().toISOString() }));
  });
  await context.route("**/api/v1/**", (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname === "/api/v1/auth/me") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "robot-demo-admin",
          username: "robot-demo-admin",
          name: "比赛演示管理员",
          role: "admin",
          community_id: "robot-demo-community",
        }),
      });
    }
    if (pathname.startsWith("/api/v1/robot/")) return route.continue();
    if (pathname.startsWith("/api/v1/alarms")) {
      return route.fulfill({ status: 200, contentType: "application/json", body: "[]" });
    }
    return route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
  });
}

function observePage(page, label) {
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push({ at: new Date().toISOString(), label, text: message.text() });
  });
  page.on("pageerror", (error) => {
    consoleErrors.push({ at: new Date().toISOString(), label, text: String(error) });
  });
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (
      (url.port === "8090" || url.href.includes("/api/navigation"))
      && !url.href.startsWith(gatewayBase)
      && !url.href.startsWith(backendBase)
    ) {
      forbiddenRequests.push({ at: new Date().toISOString(), label, url: url.href });
    }
  });
}

async function openPage(context, hash, label) {
  const page = await context.newPage();
  observePage(page, label);
  await page.goto(`${frontendBase}/${hash}`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1200);
  return page;
}

async function createCompletedEmergency() {
  await jsonRequest(gatewayBase, "/api/navigation/mock/scenario", {
    method: "POST",
    body: { request_id: `soak-scenario-safe-${Date.now()}`, scenario: "safe_response" },
  });
  const incidentId = `robot-demo-soak-safe-${Date.now()}`;
  const base = `${apiBase()}/robot/emergency/${incidentId}`;
  await jsonRequest("", `${base}/dispatch`, {
    method: "POST",
    body: {
      request_id: `${incidentId}-dispatch`,
      area_id: "elderly_activity_area",
      area_name: "养老活动区",
      alarm_id: `${incidentId}-alarm`,
      camera_id: "camera_01",
      risk_level: "critical",
      fall_probability: 0.96,
    },
  });
  await jsonRequest("", `${base}/mock/dialogue/start`, {
    method: "POST",
    body: { request_id: `${incidentId}-dialogue`, mock_prompt_text: "您还好吗？需要帮助吗？" },
  });
  await jsonRequest("", `${base}/escalate`, {
    method: "POST",
    body: {
      request_id: `${incidentId}-result`,
      turn_id: `${incidentId}-turn`,
      intent: "safe_response",
      input_text: "我没事。",
      confidence: 0.95,
    },
  });
  await jsonRequest("", `${base}/acknowledge`, {
    method: "POST",
    body: { request_id: `${incidentId}-ack`, admin_id: "robot-demo-admin" },
  });
  await jsonRequest(gatewayBase, "/api/navigation/mock/scenario", {
    method: "POST",
    body: { request_id: `soak-scenario-return-${Date.now()}`, scenario: "return_home_success" },
  });
  await jsonRequest("", `${base}/resolve-and-return`, {
    method: "POST",
    body: { request_id: `${incidentId}-return`, resolution: "比赛演示管理员已确认老人安全。" },
  });
  await jsonRequest("", `${base}/mock/return/complete`, {
    method: "POST",
    body: { request_id: `${incidentId}-complete` },
  });
  operations.push({ at: new Date().toISOString(), type: "safe_response", incident_id: incidentId });
  return incidentId;
}

async function runPatrolCycle() {
  await jsonRequest(gatewayBase, "/api/navigation/mock/scenario", {
    method: "POST",
    body: { request_id: `soak-patrol-ready-${Date.now()}`, scenario: "robot_ready" },
  });
  const requestId = `robot-demo-soak-patrol-${Date.now()}`;
  const patrol = await jsonRequest(apiBase(), "/robot/navigation/routes/robot-demo-patrol-route/start", {
    method: "POST",
    body: {
      request_id: requestId,
      source_event_id: `${requestId}-source`,
      trace_id: `${requestId}-trace`,
    },
  });
  const taskId = patrol.data.task_id;
  await jsonRequest(apiBase(), `/robot/navigation/tasks/${taskId}/manual-acquire`, {
    method: "POST",
    body: { request_id: `${requestId}-manual-acquire` },
  });
  await jsonRequest(apiBase(), `/robot/navigation/tasks/${taskId}/manual-release`, {
    method: "POST",
    body: { request_id: `${requestId}-manual-release` },
  });
  await jsonRequest(gatewayBase, "/api/navigation/mock/scenario", {
    method: "POST",
    body: { request_id: `${requestId}-success`, scenario: "navigation_success" },
  });
  await jsonRequest(apiBase(), `/robot/navigation/tasks/${taskId}/resume`, {
    method: "POST",
    body: { request_id: `${requestId}-resume` },
  });
  operations.push({ at: new Date().toISOString(), type: "patrol", task_id: taskId });
}

async function verifyResponsive(context, incidentId) {
  const viewports = [
    { name: "1366x768", width: 1366, height: 768 },
    { name: "1920x1080", width: 1920, height: 1080 },
    { name: "430x932", width: 430, height: 932 },
  ];
  const routes = [
    { name: "robot-status", hash: "#/robot-status" },
    { name: "robot-navigation", hash: "#/robot-navigation" },
    { name: "robot-emergency", hash: `#/robot-emergency?incidentId=${incidentId}` },
  ];
  for (const viewport of viewports) {
    for (const route of routes) {
      const page = await context.newPage();
      observePage(page, `responsive-${route.name}-${viewport.name}`);
      await page.setViewportSize(viewport);
      await page.goto(`${frontendBase}/${route.hash}`, { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(900);
      const result = await page.evaluate(() => ({
        overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        mockNotice: document.body.innerText.includes(
          "当前为模拟导航环境，真实机器人运动控制已禁用。",
        ),
        visibleButtons: [...document.querySelectorAll("button")].filter((button) => {
          const rect = button.getBoundingClientRect();
          return rect.width > 0 && rect.height > 0;
        }).length,
      }));
      assert.ok(
        result.overflow <= 16,
        `${route.name} ${viewport.name} severe horizontal overflow: ${result.overflow}`,
      );
      assert.equal(result.mockNotice, true, `${route.name} ${viewport.name} missing Mock notice`);
      assert.ok(result.visibleButtons > 0, `${route.name} ${viewport.name} has no visible action`);
      await page.screenshot({
        path: path.join(screenshotRoot, `${route.name}-${viewport.name}.png`),
        fullPage: true,
      });
      await page.close();
    }
  }
}

async function samplePages(pages) {
  const pageMetrics = {};
  for (const [label, page] of Object.entries(pages)) {
    if (!page || page.isClosed()) continue;
    pageMetrics[label] = await page.evaluate(() => {
      const metrics = window.__robotSoakMetrics || {};
      return {
        active_websockets: metrics.activeWebSockets ?? null,
        opened_websockets: metrics.openedWebSockets ?? null,
        closed_websockets: metrics.closedWebSockets ?? null,
        point_cloud_frames: metrics.pointCloudFrames ?? null,
        webgl_contexts_created: metrics.webglContexts ?? null,
        canvas_count: document.querySelectorAll("canvas").length,
        heap_bytes: performance.memory?.usedJSHeapSize ?? null,
        horizontal_overflow_px:
          document.documentElement.scrollWidth - document.documentElement.clientWidth,
        mock_notice_visible: document.body.innerText.includes(
          "当前为模拟导航环境，真实机器人运动控制已禁用。",
        ),
      };
    });
  }
  const state = await jsonRequest(apiBase(), "/robot/navigation/state");
  const tasksResponse = await fetch(`${apiBase()}/robot/tasks?limit=500`);
  const tasksPayload = await tasksResponse.json();
  const tasks = Array.isArray(tasksPayload.tasks) ? tasksPayload.tasks : [];
  const taskIds = tasks.map((task) => task.task_id);
  return {
    at: new Date().toISOString(),
    elapsed_seconds: Math.round((Date.now() - startedAt) / 1000),
    pages: pageMetrics,
    processes: processMetrics(),
    backend: {
      provider: state.data.provider,
      real_motion_enabled: state.data.real_motion_enabled,
      task_count: tasks.length,
      duplicate_task_ids: taskIds.length - new Set(taskIds).size,
      subscriber_count: state.data.subscriber_count ?? null,
      asyncio_task_count: state.data.asyncio_task_count ?? null,
    },
  };
}

async function interactWithPointCloud(page) {
  const canvas = page.locator("canvas").first();
  if (!(await canvas.count())) return;
  const box = await canvas.boundingBox();
  if (!box) return;
  await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.5);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.62, box.y + box.height * 0.55, { steps: 5 });
  await page.mouse.up();
  await page.mouse.wheel(0, -120);
}

async function restartOwnedStackOnce(pages) {
  runPowerShell("stop_robot_mock_demo.ps1");
  await new Promise((resolve) => setTimeout(resolve, 1000));
  runPowerShell("start_robot_mock_demo.ps1", [
    "-GatewayPort", String(manifest.ports.gateway),
    "-BackendPort", String(manifest.ports.backend),
    "-FrontendPort", String(manifest.ports.frontend),
    "-KeepDemoData",
  ]);
  manifest = readManifest();
  gatewayBase = manifest.gateway_base_url;
  backendBase = manifest.backend_base_url;
  frontendBase = manifest.frontend_base_url;
  assertMockManifest();
  await waitForBackend();
  await new Promise((resolve) => setTimeout(resolve, 4500));
  for (const page of Object.values(pages)) {
    if (!page.isClosed()) await page.reload({ waitUntil: "domcontentloaded" });
  }
  operations.push({ at: new Date().toISOString(), type: "owned_stack_restart" });
}

async function main() {
  assertMockManifest();
  await waitForBackend();
  const incidentId = await createCompletedEmergency();
  const executablePath = [
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  ].find((candidate) => fs.existsSync(candidate));
  const browser = await chromium.launch({
    headless: true,
    executablePath,
    args: ["--enable-precise-memory-info"],
  });
  activeBrowser = browser;
  const context = await browser.newContext({ viewport: { width: 1366, height: 768 } });
  activeContext = context;
  await installSession(context);
  await verifyResponsive(context, incidentId);

  const pages = {
    status: await openPage(context, "#/robot-status", "robot-status"),
    navigation: await openPage(context, "#/robot-navigation", "robot-navigation"),
    emergency: await openPage(context, `#/robot-emergency?incidentId=${incidentId}`, "robot-emergency"),
    follow: await openPage(context, "#/robot-follow", "robot-follow"),
  };

  let nextCycleAt = Date.now();
  let restartCompleted = false;
  let cycle = 0;
  while (Date.now() < deadline) {
    if (Date.now() >= nextCycleAt) {
      cycle += 1;
      for (const page of Object.values(pages)) {
        if (!page.isClosed()) {
          await page.bringToFront();
          await page.waitForTimeout(150);
        }
      }
      await interactWithPointCloud(pages.navigation);
      await runPatrolCycle();
      if (cycle % 2 === 0) {
        await pages.follow.close();
        pages.follow = await openPage(context, "#/robot-follow", `robot-follow-${cycle}`);
      }
      nextCycleAt = Date.now() + cycleIntervalSeconds * 1000;
    }

    if (
      allowOwnedRestart
      && !restartCompleted
      && Date.now() - startedAt >= (durationMinutes * 60 * 1000) / 2
    ) {
      await restartOwnedStackOnce(pages);
      restartCompleted = true;
    }

    samples.push(await samplePages(pages));
    fs.writeFileSync(
      path.join(artifactRoot, "samples.json"),
      JSON.stringify(samples, null, 2),
      "utf8",
    );
    await new Promise((resolve) =>
      setTimeout(resolve, Math.min(sampleIntervalSeconds * 1000, Math.max(0, deadline - Date.now()))),
    );
  }

  for (const page of Object.values(pages)) {
    if (!page.isClosed()) await page.close();
  }
  await context.close();
  activeContext = null;
  await browser.close();
  activeBrowser = null;

  const heapSamples = samples.flatMap((sample) =>
    Object.values(sample.pages).map((page) => page.heap_bytes).filter(Number.isFinite),
  );
  const wsSamples = samples.flatMap((sample) =>
    Object.values(sample.pages).map((page) => page.active_websockets).filter(Number.isFinite),
  );
  const webglSamples = samples.flatMap((sample) =>
    Object.values(sample.pages).map((page) => page.webgl_contexts_created).filter(Number.isFinite),
  );
  const firstHeap = heapSamples[0] ?? null;
  const lastHeap = heapSamples.at(-1) ?? null;
  const summary = {
    provider: "mock",
    real_motion_enabled: false,
    duration_minutes_requested: durationMinutes,
    duration_seconds_actual: Math.round((Date.now() - startedAt) / 1000),
    sample_count: samples.length,
    operation_count: operations.length,
    operations,
    browser_heap_first_bytes: firstHeap,
    browser_heap_last_bytes: lastHeap,
    browser_heap_delta_bytes:
      firstHeap === null || lastHeap === null ? null : lastHeap - firstHeap,
    active_websocket_min: wsSamples.length ? Math.min(...wsSamples) : null,
    active_websocket_max: wsSamples.length ? Math.max(...wsSamples) : null,
    webgl_contexts_created_max: webglSamples.length ? Math.max(...webglSamples) : null,
    console_error_count: consoleErrors.length,
    console_errors: consoleErrors,
    forbidden_request_count: forbiddenRequests.length,
    forbidden_requests: forbiddenRequests,
    owned_stack_restart_tested: restartCompleted,
    sqlite_locked_detected: consoleErrors.some((item) => /database is locked|sqlite.*locked/i.test(item.text)),
    duplicate_task_ids_detected: samples.some((sample) => sample.backend.duplicate_task_ids > 0),
    subscriber_count_note: "若后端未暴露 subscriber_count，则记录为 null，不据此伪造通过。",
    asyncio_task_count_note: "若后端未暴露 asyncio_task_count，则记录为 null，不据此伪造通过。",
    completed_at: new Date().toISOString(),
  };
  assert.equal(forbiddenRequests.length, 0, "browser attempted a forbidden direct robot address");
  assert.equal(summary.sqlite_locked_detected, false, "SQLite lock error detected");
  assert.equal(summary.duplicate_task_ids_detected, false, "duplicate robot task IDs detected");
  assert.ok((summary.active_websocket_max ?? 0) <= 8, "active WebSocket count exceeded the expected page bound");
  assert.ok((summary.webgl_contexts_created_max ?? 0) <= 2, "WebGL context count grew unexpectedly");
  fs.writeFileSync(path.join(artifactRoot, "summary.json"), JSON.stringify(summary, null, 2), "utf8");
  process.stdout.write(`${JSON.stringify(summary, null, 2)}\n`);
}

main().catch(async (error) => {
  if (activeContext) {
    await activeContext.close().catch(() => undefined);
    activeContext = null;
  }
  if (activeBrowser) {
    await activeBrowser.close().catch(() => undefined);
    activeBrowser = null;
  }
  fs.writeFileSync(
    path.join(artifactRoot, "failure.json"),
    JSON.stringify({
      provider: "mock",
      real_motion_enabled: false,
      message: error instanceof Error ? error.message : String(error),
      stack: error instanceof Error ? error.stack : null,
      samples,
      consoleErrors,
      forbiddenRequests,
      failed_at: new Date().toISOString(),
    }, null, 2),
    "utf8",
  );
  console.error(error);
  process.exitCode = 1;
});
