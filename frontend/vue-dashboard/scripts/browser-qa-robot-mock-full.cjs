const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { spawnSync } = require("node:child_process");
const { chromium } = require("playwright");

const frontendRoot = path.resolve(__dirname, "..");
const projectRoot = path.resolve(frontendRoot, "..", "..");
const artifactRoot = path.join(projectRoot, "artifacts", "robot_mock_acceptance");
const screenshotRoot = path.join(artifactRoot, "screenshots");
const evidenceRoot = path.join(artifactRoot, "evidence");
const runtimeRoot = path.join(artifactRoot, "runtime");
const manifestPath = path.join(runtimeRoot, "process-manifest.json");
const startScript = path.join(projectRoot, "scripts", "start_robot_mock_demo.ps1");
const stopScript = path.join(projectRoot, "scripts", "stop_robot_mock_demo.ps1");
const cleanupScript = path.join(projectRoot, "scripts", "cleanup_robot_mock_demo.py");
const browserCandidates = [
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
];

fs.mkdirSync(screenshotRoot, { recursive: true });
fs.mkdirSync(evidenceRoot, { recursive: true });

function readManifest() {
  return JSON.parse(fs.readFileSync(manifestPath, "utf8").replace(/^\uFEFF/, ""));
}

let manifest = readManifest();
let gatewayBase = manifest.gateway_base_url;
let backendBase = manifest.backend_base_url;
let frontendBase = manifest.frontend_base_url;
const apiBase = () => `${backendBase}/api/v1`;
const restEvidence = [];
const wsEvidence = [];
const checks = [];
const consoleErrors = [];
const pageWebSockets = [];

function recordCheck(name, passed, detail = null) {
  checks.push({ name, passed, detail, checked_at: new Date().toISOString() });
  assert.equal(passed, true, `${name}: ${detail ?? "failed"}`);
}

function validateMockContract(value, label) {
  const stack = [value];
  let declarations = 0;
  while (stack.length) {
    const current = stack.pop();
    if (!current || typeof current !== "object") continue;
    if (Object.prototype.hasOwnProperty.call(current, "provider")) {
      declarations += 1;
      assert.equal(current.provider, "mock", `${label} provider`);
    }
    if (Object.prototype.hasOwnProperty.call(current, "real_motion_enabled")) {
      declarations += 1;
      assert.equal(current.real_motion_enabled, false, `${label} real_motion_enabled`);
    }
    for (const child of Object.values(current)) {
      if (child && typeof child === "object") stack.push(child);
    }
  }
  assert.ok(declarations > 0, `${label} did not declare its Mock contract`);
}

async function jsonRequest(base, endpoint, { method = "GET", body, expect = [200, 201] } = {}) {
  const response = await fetch(`${base}${endpoint}`, {
    method,
    headers: body ? { "content-type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const payload = await response.json();
  restEvidence.push({
    at: new Date().toISOString(),
    method,
    endpoint,
    status: response.status,
    code: payload.code ?? null,
    request_id: payload.request_id ?? payload.requestId ?? null,
    execution_state:
      payload?.data?.execution_state ??
      payload?.data?.emergency_case?.execution_state ??
      payload?.data?.active_task?.execution_state ??
      null,
  });
  assert.ok(expect.includes(response.status), `${method} ${endpoint} returned ${response.status}: ${JSON.stringify(payload)}`);
  if (response.ok) validateMockContract(payload, `${method} ${endpoint}`);
  return payload;
}

function openSocket(url, label) {
  const messages = [];
  let socket;
  const opened = new Promise((resolve, reject) => {
    socket = new WebSocket(url);
    const timer = setTimeout(() => reject(new Error(`WebSocket open timeout: ${label}`)), 8000);
    socket.addEventListener("open", () => {
      clearTimeout(timer);
      resolve();
    });
    socket.addEventListener("error", () => {
      clearTimeout(timer);
      reject(new Error(`WebSocket failed: ${label}`));
    });
  });
  socket?.addEventListener("message", (event) => {
    try {
      const payload = JSON.parse(String(event.data));
      validateMockContract(payload, `WS ${label}`);
      const summary = {
        label,
        type: payload.type ?? null,
        sequence: payload.sequence ?? null,
        upstream_sequence: payload.upstream_sequence ?? null,
        execution_state:
          payload?.data?.execution_state ??
          payload?.data?.emergency_case?.execution_state ??
          payload?.data?.active_task?.execution_state ??
          null,
        received_at: new Date().toISOString(),
      };
      messages.push(summary);
      wsEvidence.push(summary);
    } catch (error) {
      wsEvidence.push({ label, parse_error: String(error), received_at: new Date().toISOString() });
    }
  });
  return {
    opened,
    messages,
    close: () => {
      if (socket && socket.readyState < 2) socket.close();
    },
  };
}

async function waitFor(predicate, label, timeoutMs = 10000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    if (await predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error(`Timed out waiting for ${label}`);
}

async function installBrowserSession(context) {
  await context.addInitScript(() => {
    localStorage.setItem("ai_health_demo_session_token", "robot-mock-acceptance-token");
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
          name: "Mock Demo Administrator",
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

async function openPage(context, hash, label) {
  const page = await context.newPage();
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push({ label, text: message.text() });
  });
  page.on("pageerror", (error) => consoleErrors.push({ label, text: String(error) }));
  page.on("websocket", (socket) => {
    pageWebSockets.push({ label, url: socket.url(), opened_at: new Date().toISOString() });
  });
  await page.goto(`${frontendBase}/${hash}`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1800);
  return page;
}

async function screenshot(page, name) {
  const target = path.join(screenshotRoot, `${name}.png`);
  await page.screenshot({ path: target, fullPage: true });
  return target;
}

function runPowerShell(script, args = [], timeout = 180000) {
  const result = spawnSync(
    "powershell.exe",
    ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script, ...args],
    { cwd: projectRoot, encoding: "utf8", timeout, maxBuffer: 4 * 1024 * 1024 },
  );
  if (result.status !== 0) {
    throw new Error(`${path.basename(script)} failed: ${result.stderr || result.stdout}`);
  }
}

async function setScenario(name) {
  return jsonRequest(gatewayBase, "/api/navigation/mock/scenario", {
    method: "POST",
    body: { request_id: `robot-demo-scenario-${name}-${Date.now()}`, scenario: name },
  });
}

async function runEmergencyBranch(branch, browserContext) {
  await setScenario(branch === "uncertain" ? "uncertain_response" : branch);
  const incidentId = `robot-demo-${branch}-${Date.now()}`;
  const dispatch = await jsonRequest(apiBase(), `/robot/emergency/${incidentId}/dispatch`, {
    method: "POST",
    body: {
      request_id: `${incidentId}-dispatch`,
      area_id: "elderly_activity_area",
      area_name: "Elderly Activity Area",
      alarm_id: `${incidentId}-alarm`,
      camera_id: "camera_01",
      risk_level: "critical",
      fall_probability: 0.96,
    },
  });
  assert.equal(dispatch.data.execution_state, "navigating");
  const taskId = dispatch.data.robot_task_id;

  const emergencySocket = openSocket(
    `${backendBase.replace(/^http/, "ws")}/ws/robot/emergency/${incidentId}`,
    `emergency-${branch}`,
  );
  await emergencySocket.opened;
  await jsonRequest(apiBase(), `/robot/emergency/${incidentId}/mock/dialogue/start`, {
    method: "POST",
    body: {
      request_id: `${incidentId}-dialogue-start`,
      mock_prompt_text: "Are you okay? Do you need help?",
    },
  });
  const result = await jsonRequest(apiBase(), `/robot/emergency/${incidentId}/escalate`, {
    method: "POST",
    body: {
      request_id: `${incidentId}-dialogue-result`,
      turn_id: `${incidentId}-turn-01`,
      intent: branch,
      input_text: branch === "safe_response" ? "I am okay." : `Mock result: ${branch}`,
      confidence: branch === "uncertain" ? 0.45 : 0.95,
    },
  });
  const expectedState = {
    safe_response: "waiting_admin_confirmation",
    need_help: "help_requested",
    no_response: "no_response",
    uncertain: "uncertain",
  }[branch];
  assert.equal(result.data.execution_state, expectedState);

  const page = await openPage(browserContext, `#/robot-emergency?incidentId=${incidentId}`, `emergency-${branch}`);
  await screenshot(page, `emergency-${branch}`);
  await page.close();

  if (branch === "safe_response") {
    await jsonRequest(apiBase(), `/robot/emergency/${incidentId}/acknowledge`, {
      method: "POST",
      body: { request_id: `${incidentId}-ack`, admin_id: "robot-demo-admin" },
    });
    await setScenario("return_home_success");
    const returning = await jsonRequest(apiBase(), `/robot/emergency/${incidentId}/resolve-and-return`, {
      method: "POST",
      body: {
        request_id: `${incidentId}-resolve-return`,
        resolution: "Mock administrator confirmed safe response and return.",
      },
    });
    assert.equal(returning.data.execution_state, "returning_home");
    const completed = await jsonRequest(apiBase(), `/robot/emergency/${incidentId}/mock/return/complete`, {
      method: "POST",
      body: { request_id: `${incidentId}-return-complete` },
    });
    assert.equal(completed.data.emergency_case.execution_state, "completed");
    assert.equal(completed.data.emergency_case.status, "resolved");
    await screenshot(
      await openPage(browserContext, `#/robot-emergency?incidentId=${incidentId}`, "emergency-completed"),
      "emergency-completed",
    );
  } else {
    const rejected = await jsonRequest(apiBase(), `/robot/emergency/${incidentId}/resolve-and-return`, {
      method: "POST",
      body: {
        request_id: `${incidentId}-forbidden-return`,
        resolution: "This operation must be rejected.",
      },
      expect: [409],
    });
    assert.equal(rejected.success, false);
    const gatewayState = await jsonRequest(gatewayBase, "/api/navigation/state");
    const activeGatewayTaskId = gatewayState.data.active_task?.task_id;
    if (activeGatewayTaskId) {
      await jsonRequest(gatewayBase, `/api/navigation/tasks/${activeGatewayTaskId}/stop`, {
        method: "POST",
        body: { request_id: `${incidentId}-qa-teardown` },
      });
    }
  }
  const bundle = await jsonRequest(apiBase(), `/robot/emergency/${incidentId}`);
  const dialogue = await jsonRequest(apiBase(), `/robot/emergency/${incidentId}/dialogue`);
  assert.equal(bundle.data.robot_task_id, taskId);
  assert.equal(dialogue.data.length, 1);
  emergencySocket.close();
  await setScenario("robot_ready");
  return { incidentId, taskId, state: expectedState };
}

async function main() {
  recordCheck("manifest is Mock-only", manifest.provider === "mock" && manifest.real_motion_enabled === false);
  const navigationSocket = openSocket(`${backendBase.replace(/^http/, "ws")}/ws/robot/navigation`, "main-navigation");
  const statusSocket = openSocket(`${backendBase.replace(/^http/, "ws")}/ws/robot/status`, "main-status");
  await Promise.all([navigationSocket.opened, statusSocket.opened]);

  const executablePath = browserCandidates.find((candidate) => fs.existsSync(candidate));
  const browser = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : {}) });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await installBrowserSession(context);

  try {
    const statePage = await openPage(context, "#/robot-status", "robot-status");
    const navigationPage = await openPage(context, "#/robot-navigation", "robot-navigation");
    let followPage;
    await screenshot(statePage, "robot-status");
    await screenshot(navigationPage, "robot-navigation-map-point-cloud");

    const state = await jsonRequest(apiBase(), "/robot/navigation/state");
    recordCheck(
      "seven safety interlocks pass",
      state.data.safety_interlock.passed === true &&
        Object.values(state.data.safety_interlock.checks).every((value) => value === true),
    );
    const points = await jsonRequest(apiBase(), "/robot/navigation/points?map_id=map_mock_0001");
    const routes = await jsonRequest(apiBase(), "/robot/navigation/routes?map_id=map_mock_0001");
    recordCheck(
      "fixed demo map points exist",
      points.data.filter((point) => point.point_type === "patrol").length >= 3 &&
        points.data.some((point) => point.point_type === "home") &&
        points.data.some((point) => point.point_type === "observation"),
    );
    assert.ok(routes.data.some((route) => route.route_id === "robot-demo-patrol-route"));

    const patrolRequestId = `robot-demo-patrol-${Date.now()}`;
    const patrol = await jsonRequest(apiBase(), "/robot/navigation/routes/robot-demo-patrol-route/start", {
      method: "POST",
      body: {
        request_id: patrolRequestId,
        source_event_id: `${patrolRequestId}-source`,
        trace_id: `${patrolRequestId}-trace`,
      },
    });
    const patrolTaskId = patrol.data.task_id;
    assert.equal(patrol.data.execution_state, "navigating");
    await screenshot(navigationPage, "patrol-navigating");

    const manual = await jsonRequest(apiBase(), `/robot/navigation/tasks/${patrolTaskId}/manual-acquire`, {
      method: "POST",
      body: { request_id: `${patrolRequestId}-manual-acquire` },
    });
    assert.equal(manual.data.execution_state, "paused_manual");
    assert.equal(manual.data.control_owner, "MANUAL");
    await navigationPage.reload({ waitUntil: "domcontentloaded" });
    await navigationPage.waitForTimeout(900);
    await screenshot(navigationPage, "patrol-manual-takeover");

    const released = await jsonRequest(apiBase(), `/robot/navigation/tasks/${patrolTaskId}/manual-release`, {
      method: "POST",
      body: { request_id: `${patrolRequestId}-manual-release` },
    });
    assert.equal(released.data.execution_state, "paused_manual");
    assert.equal(released.data.control_owner, "NONE");
    await setScenario("navigation_success");
    const completedPatrol = await jsonRequest(apiBase(), `/robot/navigation/tasks/${patrolTaskId}/resume`, {
      method: "POST",
      body: { request_id: `${patrolRequestId}-resume` },
    });
    assert.equal(completedPatrol.data.execution_state, "completed");
    assert.equal(completedPatrol.data.status, "COMPLETED");
    const patrolTimeline = await jsonRequest(apiBase(), `/robot/navigation/tasks/${patrolTaskId}/timeline`);
    const patrolEvents = await jsonRequest(apiBase(), `/robot/tasks/${patrolTaskId}/navigation-events`);
    recordCheck(
      "patrol persisted through manual release and completion",
      patrolTimeline.data.some((item) => item.payload?.execution_state === "paused_manual") &&
        patrolEvents.data.at(-1)?.execution_state === "completed",
    );
    await navigationPage.reload({ waitUntil: "domcontentloaded" });
    await navigationPage.waitForTimeout(900);
    await screenshot(navigationPage, "patrol-completed");

    const wsCountBeforeRestart = pageWebSockets.length;
    runPowerShell(stopScript);
    await new Promise((resolve) => setTimeout(resolve, 1200));
    runPowerShell(startScript, [
      "-GatewayPort", String(manifest.ports.gateway),
      "-BackendPort", String(manifest.ports.backend),
      "-FrontendPort", String(manifest.ports.frontend),
      "-KeepDemoData",
    ]);
    manifest = readManifest();
    gatewayBase = manifest.gateway_base_url;
    backendBase = manifest.backend_base_url;
    frontendBase = manifest.frontend_base_url;
    await waitFor(async () => {
      try {
        return (await fetch(`${backendBase}/api/v1/robot/navigation/state`)).ok;
      } catch {
        return false;
      }
    }, "backend restart");
    await statePage.waitForTimeout(4500);
    const persistedEvents = await jsonRequest(apiBase(), `/robot/tasks/${patrolTaskId}/navigation-events`);
    recordCheck(
      "SQLite survives backend restart",
      persistedEvents.data.at(-1)?.execution_state === "completed",
    );
    recordCheck(
      "browser WebSockets reconnect after restart",
      pageWebSockets.length > wsCountBeforeRestart,
      { before: wsCountBeforeRestart, after: pageWebSockets.length },
    );

    navigationSocket.close();
    statusSocket.close();
    const navigationSocketAfterRestart = openSocket(
      `${backendBase.replace(/^http/, "ws")}/ws/robot/navigation`,
      "main-navigation-reconnected",
    );
    await navigationSocketAfterRestart.opened;

    const emergencyResults = [];
    for (const branch of ["safe_response", "need_help", "no_response", "uncertain"]) {
      emergencyResults.push(await runEmergencyBranch(branch, context));
    }

    const blockedResults = [];
    for (const scenario of [
      "localization_invalid",
      "map_not_loaded",
      "emergency_stop_active",
      "robot_offline",
      "path_not_plannable",
      "manual_takeover",
    ]) {
      await setScenario(scenario);
      const incidentId = `robot-demo-blocked-${scenario}-${Date.now()}`;
      const blocked = await jsonRequest(apiBase(), `/robot/emergency/${incidentId}/dispatch`, {
        method: "POST",
        body: {
          request_id: `${incidentId}-dispatch`,
          area_id: "elderly_activity_area",
          area_name: "Elderly Activity Area",
          alarm_id: `${incidentId}-alarm`,
          camera_id: "camera_01",
          risk_level: "critical",
          fall_probability: 0.97,
        },
        expect: [409],
      });
      assert.equal(blocked.success, false);
      assert.ok(Array.isArray(blocked.data.blocked_by) && blocked.data.blocked_by.length > 0);
      blockedResults.push({ scenario, incident_id: incidentId, code: blocked.code, blocked_by: blocked.data.blocked_by });
    }
    await setScenario("robot_ready");

    const blockedPage = await openPage(
      context,
      `#/robot-emergency?incidentId=${blockedResults.at(-1)?.incident_id ?? ""}`,
      "blocked-summary",
    );
    await screenshot(blockedPage, "safety-blocked");
    await blockedPage.close();

    const emergencyPage = await openPage(
      context,
      `#/robot-emergency?incidentId=${emergencyResults[0].incidentId}`,
      "robot-emergency-concurrent",
    );
    followPage = await openPage(context, "#/robot-follow", "robot-follow");
    await Promise.all([
      statePage.waitForTimeout(1000),
      navigationPage.waitForTimeout(1000),
      emergencyPage.waitForTimeout(1000),
      followPage.waitForTimeout(1000),
    ]);
    recordCheck(
      "four robot pages remain open concurrently",
      [statePage, navigationPage, emergencyPage, followPage].every((page) => !page.isClosed()),
    );
    await screenshot(emergencyPage, "multi-page-emergency");
    await emergencyPage.close();
    await statePage.waitForTimeout(500);
    recordCheck("closing one page does not close the others", !statePage.isClosed() && !navigationPage.isClosed() && !followPage.isClosed());

    const memoryBefore = await statePage.evaluate(() => performance.memory?.usedJSHeapSize ?? 0);
    await statePage.waitForTimeout(1500);
    const memoryAfter = await statePage.evaluate(() => performance.memory?.usedJSHeapSize ?? 0);
    recordCheck(
      "browser memory has no sustained obvious growth",
      memoryBefore === 0 || memoryAfter - memoryBefore < 64 * 1024 * 1024,
      { memoryBefore, memoryAfter },
    );

    navigationSocketAfterRestart.close();
    await Promise.all([statePage.close(), navigationPage.close(), followPage.close()]);
    await new Promise((resolve) => setTimeout(resolve, 800));

    const demoDatabase = manifest.database;
    const pythonPath = manifest.processes.find((item) => item.name === "health-new-backend").executable;
    const cleanupOutput = path.join(evidenceRoot, "cleanup-summary.json");
    const cleanup = spawnSync(
      pythonPath,
      [cleanupScript, "--database", demoDatabase, "--output", cleanupOutput],
      { cwd: projectRoot, encoding: "utf8", timeout: 30000 },
    );
    if (cleanup.status !== 0) throw new Error(`cleanup failed: ${cleanup.stderr || cleanup.stdout}`);
    const cleanupSummary = JSON.parse(fs.readFileSync(cleanupOutput, "utf8"));
    recordCheck(
      "cleanup removes only dynamic demo records and preserves fixed map",
      cleanupSummary.after.robot_maps === 1 &&
        cleanupSummary.after.robot_map_points === 5 &&
        cleanupSummary.after.robot_patrol_routes === 1 &&
        cleanupSummary.after.robot_tasks === 0,
      cleanupSummary.after,
    );

    const result = {
      provider: "mock",
      real_motion_enabled: false,
      completed_at: new Date().toISOString(),
      patrol_task_id: patrolTaskId,
      emergency_results: emergencyResults,
      blocked_results: blockedResults,
      checks,
      rest_request_count: restEvidence.length,
      websocket_event_count: wsEvidence.length,
      page_websocket_count: pageWebSockets.length,
      console_errors: {
        expected_during_video_fallback_or_restart: consoleErrors.filter(
          (item) => item.text.includes("503") || item.text.includes("ERR_CONNECTION_REFUSED"),
        ),
        unexpected: consoleErrors.filter(
          (item) => !item.text.includes("503") && !item.text.includes("ERR_CONNECTION_REFUSED"),
        ),
      },
      cleanup: cleanupSummary,
      formal_database_sha256_before: manifest.formal_database_sha256_before,
    };
    recordCheck(
      "console has no unexpected error storm",
      result.console_errors.unexpected.length === 0,
      { expected_transient_count: result.console_errors.expected_during_video_fallback_or_restart.length },
    );
    fs.writeFileSync(path.join(evidenceRoot, "rest-summary.json"), JSON.stringify(restEvidence, null, 2));
    fs.writeFileSync(path.join(evidenceRoot, "websocket-summary.json"), JSON.stringify(wsEvidence, null, 2));
    fs.writeFileSync(path.join(evidenceRoot, "browser-websocket-summary.json"), JSON.stringify(pageWebSockets, null, 2));
    fs.writeFileSync(path.join(evidenceRoot, "acceptance-result.json"), JSON.stringify(result, null, 2));
    console.log("ROBOT_MOCK_FULL_ACCEPTANCE_OK");
    console.log(JSON.stringify(result, null, 2));
  } finally {
    navigationSocket.close();
    statusSocket.close();
    await Promise.race([
      context.close(),
      new Promise((resolve) => setTimeout(resolve, 3000)),
    ]);
    await Promise.race([
      browser.close(),
      new Promise((resolve) => setTimeout(resolve, 3000)),
    ]);
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
