<script setup lang="ts">
import { computed } from "vue";
import {
  Bot,
  CircleAlert,
  CircleCheckBig,
  ListChecks,
  PlugZap,
  RefreshCw,
  Shield,
} from "lucide-vue-next";
import PageHeader from "../components/layout/PageHeader.vue";
import Go2VideoPanel from "../components/robot/Go2VideoPanel.vue";
import RobotCapabilityBadge from "../components/robot/RobotCapabilityBadge.vue";
import RobotDiagnosticGrid from "../components/robot/RobotDiagnosticGrid.vue";
import RobotSafetyInterlock from "../components/robot/RobotSafetyInterlock.vue";
import RobotStatusSummary from "../components/robot/RobotStatusSummary.vue";
import RobotStatusTimeline from "../components/robot/RobotStatusTimeline.vue";
import { useRobotStatus } from "../composables/useRobotStatus";
import type { CapabilityState, RobotSafetyInterlock as RobotSafetyInterlockType } from "../types/robot";
import {
  MOCK_ENVIRONMENT_NOTICE,
  robotExecutionStateLabel,
} from "../utils/robotPresentation";

const {
  capabilities,
  connectionState,
  contractIssue,
  diagnostics,
  errors,
  events,
  hasData,
  lastUpdatedAt,
  legacyStatus,
  loading,
  navigationState,
  reconnect,
  refresh,
  refreshing,
} = useRobotStatus();

const connectionLabels = {
  idle: "未连接",
  connecting: "连接中",
  connected: "实时连接",
  reconnecting: "正在重连",
  disconnected: "已断开",
  error: "连接异常",
};

const pageMeta = computed(() => [
  "设备 Go2 EDU",
  "Provider Mock",
  "真实运动已禁用",
]);

const interlock = computed<RobotSafetyInterlockType | null>(() =>
  diagnostics.value?.safety_interlock
  ?? navigationState.value?.safety_interlock
  ?? null,
);

const currentTask = computed(() =>
  diagnostics.value?.current_task
  ?? navigationState.value?.current_task
  ?? legacyStatus.value?.task_center?.current_task
  ?? null,
);

const capabilityItems = computed(() => {
  const value = capabilities.value;
  const state = (item: unknown, fallback?: unknown): CapabilityState => {
    const candidate = item ?? fallback;
    return ["mock", "unavailable", "not_verified", "blocked", "ready"].includes(String(candidate))
      ? candidate as CapabilityState
      : "not_verified";
  };
  return [
    ["建图", state(value?.mapping)],
    ["地图预览", state(value?.map_preview, value?.maps)],
    ["地图保存", state(value?.map_save, value?.maps)],
    ["点位导航", state(value?.point_navigation, value?.navigation)],
    ["巡逻", state(value?.patrol)],
    ["返航", state(value?.return_home)],
    ["遥控接管", state(value?.manual_takeover)],
    ["定位", state(value?.localization)],
    ["点云", state(value?.point_cloud)],
    ["音频输入", state(value?.audio_input)],
    ["音频输出", state(value?.audio_output)],
    ["ROS2", state(value?.ros2)],
    ["Nav2", state(value?.nav2)],
    ["SLAM Toolbox", state(value?.slam_toolbox)],
  ] as Array<[string, CapabilityState]>;
});

function formatTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "尚未更新";
}
</script>

<template>
  <section class="page-stack robot-status-page">
    <PageHeader
      eyebrow="Go2 / Read-only Robot Status"
      title="机器人状态"
      description="汇总主系统代理的 Mock 机器人状态、诊断、安全联锁和实时事件。页面只读，不发送运动、建图或导航指令。"
      :meta="pageMeta"
    >
      <template #actions>
        <div class="robot-status-page__actions">
          <span class="robot-status-page__connection" :class="`is-${connectionState}`">
            <PlugZap :size="15" />
            {{ connectionLabels[connectionState] }}
          </span>
          <button
            v-if="connectionState === 'error' || connectionState === 'disconnected'"
            type="button"
            class="robot-status-button robot-status-button--secondary"
            @click="reconnect"
          >
            重连状态流
          </button>
          <button
            type="button"
            class="robot-status-button"
            :disabled="refreshing"
            @click="refresh()"
          >
            <RefreshCw :size="15" :class="{ 'is-spinning': refreshing }" />
            {{ refreshing ? "刷新中" : "刷新" }}
          </button>
        </div>
      </template>
    </PageHeader>

    <div class="robot-status-mock-banner" role="status">
      <Shield :size="21" />
      <div>
        <strong>{{ MOCK_ENVIRONMENT_NOTICE }}</strong>
        <p>地图、导航、点云和联锁状态均用于模拟验证；未验证字段不会被解释为异常或已就绪。</p>
      </div>
      <code>provider=mock · real_motion_enabled=false</code>
    </div>

    <div v-if="contractIssue" class="robot-status-alert robot-status-alert--critical" role="alert">
      <CircleAlert :size="19" />
      <div>
        <strong>接口安全契约异常</strong>
        <p>{{ contractIssue.message }}</p>
        <code>{{ contractIssue.code }} · {{ contractIssue.endpoint }}</code>
      </div>
    </div>

    <div v-if="errors.length" class="robot-status-alert" role="alert">
      <CircleAlert :size="19" />
      <div>
        <strong>部分状态暂不可用</strong>
        <p v-for="message in errors" :key="message">{{ message }}</p>
      </div>
    </div>

    <div v-if="loading && !hasData" class="robot-status-loading" aria-live="polite">
      <span></span><span></span><span></span>
      <p>正在并行读取四个主系统状态接口…</p>
    </div>

    <div v-else class="robot-status-layout">
      <main class="robot-status-layout__main">
        <RobotStatusSummary
          :diagnostics="diagnostics"
          :navigation-state="navigationState"
          :legacy-status="legacyStatus"
          :updated-at="lastUpdatedAt"
        />
        <RobotDiagnosticGrid :diagnostics="diagnostics" :navigation-state="navigationState" />
        <RobotSafetyInterlock :interlock="interlock" />
        <RobotStatusTimeline :events="events" />
      </main>

      <aside class="robot-status-layout__side">
        <Go2VideoPanel />

        <article class="robot-side-card">
          <header>
            <span><Bot :size="18" /></span>
            <div><p>CURRENT TASK</p><h2>当前任务</h2></div>
          </header>
          <dl v-if="currentTask">
            <div><dt>任务编号</dt><dd>{{ currentTask.task_id }}</dd></div>
            <div>
              <dt>状态</dt>
              <dd>{{ robotExecutionStateLabel(currentTask.execution_state ?? currentTask.status) }}</dd>
            </div>
            <div><dt>对象</dt><dd>{{ currentTask.elder_name ?? currentTask.elder_id ?? "-" }}</dd></div>
            <div><dt>位置</dt><dd>{{ currentTask.location ?? "-" }}</dd></div>
            <div><dt>更新时间</dt><dd>{{ formatTime(currentTask.updated_at) }}</dd></div>
          </dl>
          <div v-else class="robot-side-card__empty">
            <ListChecks :size="22" />
            <p>暂无当前机器人任务。</p>
          </div>
        </article>

        <article class="robot-side-card">
          <header>
            <span><CircleCheckBig :size="18" /></span>
            <div><p>CAPABILITIES</p><h2>能力状态</h2></div>
          </header>
          <div class="robot-capability-list">
            <div v-for="[label, state] in capabilityItems" :key="label">
              <span>{{ label }}</span>
              <RobotCapabilityBadge :state="state" />
            </div>
          </div>
          <p class="robot-side-card__note">“模拟”仅表示软件接口可用于演示，不代表真实设备已就绪。</p>
        </article>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.robot-status-page {
  --robot-ink: #102a43;
  --robot-blue: #245d97;
}

.robot-status-page__actions { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.robot-status-page__connection { display: inline-flex; align-items: center; gap: 6px; padding: 8px 10px; border: 1px solid #cad7e2; border-radius: 9px; background: #f4f8fb; color: #587187; font-size: 0.72rem; font-weight: 750; }
.robot-status-page__connection.is-connected { border-color: #a9ddca; background: #edf9f4; color: #087653; }
.robot-status-page__connection.is-reconnecting, .robot-status-page__connection.is-connecting { border-color: #edca8f; background: #fff8e8; color: #8b5a0a; }
.robot-status-page__connection.is-error, .robot-status-page__connection.is-disconnected { border-color: #efc1bc; background: #fff3f1; color: #a53630; }
.robot-status-button { display: inline-flex; align-items: center; justify-content: center; gap: 7px; padding: 9px 12px; border: 1px solid #1765c2; border-radius: 9px; background: #174ea6; color: #f8fbff; font: inherit; font-size: 0.76rem; font-weight: 760; cursor: pointer; }
.robot-status-button--secondary { border-color: #cbd8e4; background: #f8fbfd; color: #345a77; }
.robot-status-button:disabled { cursor: not-allowed; opacity: 0.55; }
.is-spinning { animation: robot-status-spin 1s linear infinite; }

.robot-status-mock-banner { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 13px; padding: 14px 16px; border: 1px solid #b8d2ec; border-left: 4px solid #3d7fb8; border-radius: 13px; background: #eef6fd; color: #2d638d; }
.robot-status-mock-banner strong { color: #174e78; font-size: 0.86rem; }
.robot-status-mock-banner p { margin: 3px 0 0; color: #4f718c; font-size: 0.75rem; line-height: 1.45; }
.robot-status-mock-banner code { color: #365d78; font-family: var(--font-mono); font-size: 0.66rem; white-space: nowrap; }

.robot-status-alert { display: grid; grid-template-columns: auto 1fr; gap: 10px; padding: 13px 15px; border: 1px solid #edca8f; border-radius: 12px; background: #fff8e8; color: #8b5a0a; }
.robot-status-alert--critical { border-color: #efc1bc; background: #fff3f1; color: #a53630; }
.robot-status-alert strong { font-size: 0.8rem; }
.robot-status-alert p { margin: 3px 0 0; font-size: 0.72rem; line-height: 1.45; }
.robot-status-alert code { display: block; margin-top: 5px; font-family: var(--font-mono); font-size: 0.63rem; }

.robot-status-loading { min-height: 300px; display: grid; grid-template-columns: repeat(3, 14px); place-content: center; gap: 7px; border: 1px solid #dce6f0; border-radius: 18px; background: #fbfdff; color: #61798e; text-align: center; }
.robot-status-loading span { width: 14px; height: 14px; border-radius: 50%; background: #6f9fc4; animation: robot-status-pulse 1.2s ease-in-out infinite; }
.robot-status-loading span:nth-child(2) { animation-delay: 120ms; }
.robot-status-loading span:nth-child(3) { animation-delay: 240ms; }
.robot-status-loading p { grid-column: 1 / -1; margin: 8px 0 0; font-size: 0.76rem; }

.robot-status-layout { display: grid; grid-template-columns: minmax(0, 2fr) minmax(300px, 0.92fr); gap: 18px; align-items: start; }
.robot-status-layout__main, .robot-status-layout__side { min-width: 0; display: grid; gap: 16px; }
.robot-status-layout__side { position: sticky; top: 16px; }

.robot-side-card { padding: 18px; border: 1px solid #dce6f0; border-radius: 18px; background: #fbfdff; box-shadow: 0 8px 24px rgba(35, 78, 112, 0.06); }
.robot-side-card header { display: flex; align-items: center; gap: 10px; }
.robot-side-card header > span { width: 36px; height: 36px; display: grid; place-items: center; border-radius: 10px; background: #eaf3fb; color: #326e9a; }
.robot-side-card header p { margin: 0; color: #47779c; font-size: 0.64rem; font-weight: 800; letter-spacing: 0.08em; }
.robot-side-card h2 { margin: 3px 0 0; color: var(--robot-ink); font-size: 0.96rem; }
.robot-side-card dl { display: grid; gap: 0; margin: 14px 0 0; }
.robot-side-card dl > div { display: grid; grid-template-columns: 92px minmax(0, 1fr); gap: 8px; padding: 9px 0; border-top: 1px solid #e4ebf1; }
.robot-side-card dt { color: #74899b; font-size: 0.68rem; }
.robot-side-card dd { margin: 0; overflow: hidden; color: #34566f; font-size: 0.72rem; font-weight: 700; text-overflow: ellipsis; white-space: nowrap; }
.robot-side-card__empty { min-height: 100px; display: grid; place-content: center; justify-items: center; gap: 7px; color: #7a90a2; }
.robot-side-card__empty p { margin: 0; font-size: 0.72rem; }
.robot-capability-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 7px; margin-top: 14px; }
.robot-capability-list > div { min-width: 0; display: flex; align-items: center; justify-content: space-between; gap: 7px; padding: 8px; border: 1px solid #e1e9f0; border-radius: 9px; background: #f6f9fb; }
.robot-capability-list > div > span { overflow: hidden; color: #536f84; font-size: 0.68rem; text-overflow: ellipsis; white-space: nowrap; }
.robot-side-card__note { margin: 12px 0 0; padding-top: 10px; border-top: 1px solid #e4ebf1; color: #6f8394; font-size: 0.66rem; line-height: 1.45; }

@keyframes robot-status-spin { to { transform: rotate(360deg); } }
@keyframes robot-status-pulse { 0%, 100% { opacity: 0.35; transform: scale(0.82); } 50% { opacity: 1; transform: scale(1); } }
@media (prefers-reduced-motion: reduce) { .is-spinning, .robot-status-loading span { animation: none; } }
@media (max-width: 1180px) { .robot-status-layout { grid-template-columns: 1fr; } .robot-status-layout__side { position: static; grid-template-columns: repeat(2, minmax(0, 1fr)); } .robot-status-layout__side > :first-child { grid-column: 1 / -1; } }
@media (max-width: 720px) { .robot-status-mock-banner { grid-template-columns: auto 1fr; } .robot-status-mock-banner code { grid-column: 2; white-space: normal; } .robot-status-layout__side { grid-template-columns: 1fr; } .robot-status-layout__side > :first-child { grid-column: auto; } .robot-capability-list { grid-template-columns: 1fr; } }
@media (max-width: 520px) { .robot-status-page__actions { width: 100%; } .robot-status-button { flex: 1; } }
</style>
