const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { spawn } = require("node:child_process");
const { chromium } = require("playwright");

const root = path.resolve(__dirname, "..");
const port = 4176;
const baseUrl = `http://127.0.0.1:${port}`;
const outputDir = path.join(os.tmpdir(), "health-new-robot-emergency-qa");
fs.mkdirSync(outputDir, { recursive: true });
const browserCandidates = [
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
];

const now = "2026-07-23T08:00:00Z";
const checksPassed = {
  robot_online: true,
  emergency_stop_clear: true,
  localization_valid: true,
  map_loaded: true,
  path_plannable: true,
  robot_stationary: true,
  control_available: true,
};

function envelope(data) {
  return {
    success: true,
    code: "OK",
    message: "操作成功",
    data,
    timestamp: now,
    request_id: null,
  };
}

function makeCase(incidentId, state = "navigating") {
  return {
    provider: "mock",
    real_motion_enabled: false,
    case_id: `case-${incidentId}`,
    incident_id: incidentId,
    robot_task_id: `task-${incidentId}`,
    alarm_id: `alarm-${incidentId}`,
    camera_id: "camera-01",
    area_id: "living-room",
    area_name: "客厅观察区",
    observation_point_id: "point-observation",
    home_point_id: "point-home",
    risk_level: "critical",
    fall_probability: 0.96,
    status: state === "blocked" ? "blocked" : "active",
    execution_state: state,
    navigation_state: state,
    control_owner: "NONE",
    dialogue_intent: null,
    acknowledged_by: null,
    acknowledged_at: null,
    resolution: null,
    resolved_at: null,
    error_code: state === "blocked" ? "LOCALIZATION_INVALID" : null,
    error_message: state === "blocked" ? "定位无效，无法派发" : null,
    metadata: {
      event: {
        event_type: "fall_confirmed",
        occurred_at: now,
      },
    },
    created_at: now,
    updated_at: now,
  };
}

function makeEvent(incidentId, type, state, sequence) {
  return {
    provider: "mock",
    real_motion_enabled: false,
    id: sequence,
    event_id: `${incidentId}:${type}:${sequence}`,
    task_id: `task-${incidentId}`,
    incident_id: incidentId,
    event_type: type,
    execution_state: state,
    navigation_state: state,
    x: null,
    y: null,
    yaw: null,
    control_owner: "NONE",
    error_code: null,
    sequence,
    message: state,
    metadata: {},
    occurred_at: now,
    created_at: now,
  };
}

function makeBundle(state) {
  return {
    provider: "mock",
    real_motion_enabled: false,
    incident_id: state.incidentId,
    emergency_case: state.case,
    robot_task_id: state.case.robot_task_id,
    navigation_events: state.events,
    dialogue_turns: state.turns,
  };
}

async function installApiMock(context, state) {
  await context.addInitScript(({ incidentId }) => {
    localStorage.setItem("ai_health_demo_session_token", "browser-qa-token");
    sessionStorage.setItem(
      `robot-emergency:alarm:${incidentId}`,
      JSON.stringify({
        incident_id: incidentId,
        alarm_id: `alarm-${incidentId}`,
        camera_id: "camera-01",
        area_id: "living-room",
        area_name: "客厅观察区",
        event_type: "fall_confirmed",
        occurred_at: "2026-07-23T08:00:00Z",
        risk_level: "critical",
        fall_probability: 0.96,
      }),
    );
  }, { incidentId: state.incidentId });

  await context.routeWebSocket(/\/ws\/robot\/emergency\//, (webSocket) => {
    state.webSocketConnections += 1;
    setTimeout(() => {
      if (!state.case) return;
      webSocket.send(JSON.stringify({
        type: "emergency_snapshot",
        sequence: state.sequence,
        timestamp: now,
        provider: "mock",
        real_motion_enabled: false,
        data: makeBundle(state),
      }));
    }, 20);
  });

  await context.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const pathname = url.pathname;
    const method = request.method();
    const emergencyBase = `/api/v1/robot/emergency/${state.incidentId}`;
    const respond = (body, status = 200) => route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(body),
    });

    if (pathname === "/api/v1/auth/me") {
      return respond({
        id: "admin-browser-qa",
        username: "admin",
        name: "值守管理员",
        role: "admin",
        community_id: "community-demo",
      });
    }
    if (pathname === "/api/v1/alarms") return respond([]);
    if (pathname === "/api/v1/robot/navigation/state") {
      const checks = state.blocked
        ? { ...checksPassed, localization_valid: false }
        : checksPassed;
      return respond(envelope({
        provider: "mock",
        real_motion_enabled: false,
        execution_state: state.case?.execution_state ?? "created",
        control_owner: "NONE",
        safety_interlock: {
          provider: "mock",
          real_motion_enabled: false,
          passed: !state.blocked,
          checks,
          blocked_by: state.blocked ? ["LOCALIZATION_INVALID"] : [],
          checked_at: now,
        },
      }));
    }
    if (pathname === emergencyBase && method === "GET") {
      if (!state.case) {
        return respond({
          success: false,
          code: "INCIDENT_NOT_FOUND",
          message: "应急案例不存在",
          data: { incident_id: state.incidentId },
          timestamp: now,
        }, 404);
      }
      return respond(envelope(makeBundle(state)));
    }
    if (pathname === `${emergencyBase}/dialogue` && method === "GET") {
      if (!state.case) return respond({ code: "INCIDENT_NOT_FOUND", message: "应急案例不存在" }, 404);
      return respond(envelope(state.turns));
    }
    if (pathname === `${emergencyBase}/dispatch` && method === "POST") {
      state.case = makeCase(state.incidentId, state.blocked ? "blocked" : "navigating");
      state.events.push(makeEvent(state.incidentId, state.blocked ? "emergency_dispatch_blocked" : "emergency_dispatched", state.case.execution_state, ++state.sequence));
      return respond(envelope(state.case), 201);
    }
    if (pathname === `${emergencyBase}/mock/dialogue/start` && method === "POST") {
      state.case.execution_state = "waiting_response";
      state.case.navigation_state = "waiting_response";
      state.case.metadata.mock_prompt = {
        text: "您还好吗？需要帮助吗？",
        asr_status: "pending_mock",
        tts_status: "pending_mock",
      };
      for (const [type, executionState] of [
        ["task_arrived", "arrived"],
        ["voice_prompting", "voice_prompting"],
        ["waiting_response", "waiting_response"],
      ]) {
        state.events.push(makeEvent(state.incidentId, type, executionState, ++state.sequence));
      }
      return respond(envelope(makeBundle(state)));
    }
    if (pathname === `${emergencyBase}/escalate` && method === "POST") {
      const body = request.postDataJSON();
      const resultState = {
        safe_response: "waiting_admin_confirmation",
        need_help: "help_requested",
        no_response: "no_response",
        uncertain: "uncertain",
      }[body.intent];
      state.case.dialogue_intent = body.intent;
      state.case.execution_state = resultState;
      state.case.navigation_state = resultState;
      state.case.status = body.intent === "safe_response" ? "active" : "escalated";
      state.turns.push({
        provider: "mock",
        real_motion_enabled: false,
        id: state.turns.length + 1,
        turn_id: body.turn_id,
        incident_id: state.incidentId,
        robot_task_id: state.case.robot_task_id,
        role: "user",
        text: body.input_text,
        input_text: body.input_text,
        intent: body.intent,
        confidence: body.confidence,
        recommended_action: body.intent === "safe_response" ? "confirm_return_home" : "notify_admin",
        reply_text: null,
        asr_status: "mock",
        tts_status: "mock",
        conversation_complete: true,
        metadata: { source: "mock" },
        occurred_at: now,
        created_at: now,
      });
      state.events.push(makeEvent(state.incidentId, body.intent === "safe_response" ? "waiting_admin_confirmation" : "alarm_escalation_required", resultState, ++state.sequence));
      return respond(envelope(state.case));
    }
    if (pathname === `${emergencyBase}/acknowledge` && method === "POST") {
      state.case.acknowledged_by = "admin-browser-qa";
      state.case.acknowledged_at = now;
      return respond(envelope(state.case));
    }
    if (pathname === `${emergencyBase}/resolve-and-return` && method === "POST") {
      state.case.execution_state = "returning_home";
      state.case.navigation_state = "returning_home";
      state.events.push(makeEvent(state.incidentId, "return_home_requested", "returning_home", ++state.sequence));
      return respond(envelope(state.case));
    }
    if (pathname === `${emergencyBase}/mock/return/complete` && method === "POST") {
      state.case.execution_state = "completed";
      state.case.navigation_state = "completed";
      state.case.status = "resolved";
      state.case.resolution = "Mock 返航完成，事件已结束";
      state.case.resolved_at = now;
      state.events.push(makeEvent(state.incidentId, "return_home_completed", "completed", ++state.sequence));
      state.events.push(makeEvent(state.incidentId, "emergency_completed", "completed", ++state.sequence));
      return respond(envelope(makeBundle(state)));
    }
    return respond({ detail: "browser qa route not implemented" }, 404);
  });
}

async function openScenario(browser, name, {
  initialState = null,
  blocked = false,
  viewport = { width: 1366, height: 768 },
} = {}) {
  const incidentId = `qa-${name}`;
  const state = {
    incidentId,
    case: initialState ? makeCase(incidentId, initialState) : null,
    blocked,
    events: initialState ? [makeEvent(incidentId, "emergency_dispatched", initialState, 1)] : [],
    turns: [],
    sequence: 1,
    webSocketConnections: 0,
  };
  const context = await browser.newContext({ viewport });
  await installApiMock(context, state);
  const page = await context.newPage();
  await page.goto(`${baseUrl}/#/robot-emergency?incidentId=${incidentId}`);
  await page.waitForSelector("text=机器人应急处置");
  return { context, page, state, incidentId };
}

async function run() {
  const viteEntry = path.join(root, "node_modules", "vite", "bin", "vite.js");
  const server = spawn(process.execPath, [viteEntry, "--host", "127.0.0.1", "--port", String(port)], {
    cwd: root,
    stdio: "ignore",
  });
  let browser;
  try {
    for (let attempt = 0; attempt < 50; attempt += 1) {
      try {
        const response = await fetch(baseUrl);
        if (response.ok) break;
      } catch {
        await new Promise((resolve) => setTimeout(resolve, 200));
      }
      if (attempt === 49) throw new Error("Vite server did not start");
    }
    const executablePath = browserCandidates.find((candidate) => fs.existsSync(candidate));
    browser = await chromium.launch({
      headless: true,
      ...(executablePath ? { executablePath } : {}),
    });

    const scenarioA = await openScenario(browser, "safe", { viewport: { width: 1366, height: 768 } });
    await scenarioA.page.getByRole("button", { name: "派发机器人" }).click();
    await scenarioA.page.getByText("前往现场", { exact: true }).first().waitFor();
    await scenarioA.page.getByText("实时通道已连接", { exact: true }).waitFor();
    assert.equal(scenarioA.state.webSocketConnections, 1);
    await scenarioA.page.getByRole("button", { name: "模拟到达并开始询问" }).click();
    await scenarioA.page.getByText("等待回应", { exact: true }).first().waitFor();
    await scenarioA.page.getByRole("button", { name: "模拟“我没事”" }).click();
    await scenarioA.page.getByText("老人已明确回应").waitFor();
    await scenarioA.page.getByRole("button", { name: "我已知晓" }).click();
    await scenarioA.page.getByRole("button", { name: "管理员确认并返回待命区" }).click();
    await scenarioA.page.getByRole("button", { name: "模拟完成返航" }).click();
    await scenarioA.page.getByText("闭环完成", { exact: true }).first().waitFor();
    assert.equal(scenarioA.state.case.execution_state, "completed");
    const safeOverflow = await scenarioA.page.evaluate(() => ({
      width: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
    }));
    assert.ok(safeOverflow.scrollWidth <= safeOverflow.width + 1, "1366 viewport has horizontal overflow");
    const safeShot = path.join(outputDir, "scenario-a-1366.png");
    await scenarioA.page.screenshot({ path: safeShot, fullPage: true });
    await scenarioA.context.close();

    for (const branch of [
      ["need-help", "模拟“需要帮助”", "老人请求帮助"],
      ["no-response", "模拟“无回应”", "15 秒内无有效回应"],
      ["uncertain", "模拟“无法判断”", "无法可靠判断老人状态"],
    ]) {
      const scenario = await openScenario(browser, branch[0], { initialState: "waiting_response" });
      await scenario.page.getByRole("button", { name: branch[1] }).click();
      await scenario.page.getByRole("heading", { name: branch[2], exact: true }).waitFor();
      assert.equal(await scenario.page.getByRole("button", { name: "管理员确认并返回待命区" }).count(), 0);
      await scenario.context.close();
    }

    const scenarioE = await openScenario(browser, "blocked", { initialState: "blocked", blocked: true });
    await scenarioE.page.getByText("机器人无法出动，请人工处置").waitFor();
    assert.equal(await scenarioE.page.getByRole("button", { name: "管理员确认并返回待命区" }).count(), 0);
    const blockedShot = path.join(outputDir, "scenario-e-blocked.png");
    await scenarioE.page.screenshot({ path: blockedShot, fullPage: true });
    await scenarioE.context.close();

    for (const viewport of [
      { width: 1920, height: 1080, label: "1920" },
      { width: 430, height: 932, label: "narrow" },
    ]) {
      const scenario = await openScenario(browser, `layout-${viewport.label}`, {
        initialState: "completed",
        viewport,
      });
      const overflow = await scenario.page.evaluate(() => ({
        width: document.documentElement.clientWidth,
        scrollWidth: document.documentElement.scrollWidth,
      }));
      assert.ok(overflow.scrollWidth <= overflow.width + 1, `${viewport.label} viewport has horizontal overflow`);
      await scenario.page.screenshot({
        path: path.join(outputDir, `layout-${viewport.label}.png`),
        fullPage: true,
      });
      await scenario.context.close();
    }

    console.log("ROBOT_EMERGENCY_BROWSER_QA_OK");
    console.log(outputDir);
  } finally {
    if (browser) await browser.close();
    server.kill();
  }
}

run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
