<script setup lang="ts">
import { computed } from "vue";
import {
  ArrowLeft,
  CircleAlert,
  PlugZap,
  RefreshCw,
  Shield,
} from "lucide-vue-next";
import type { SessionUser } from "../api/client";
import PageHeader from "../components/layout/PageHeader.vue";
import EmergencyActionPanel from "../components/robot/EmergencyActionPanel.vue";
import EmergencyCaseSummary from "../components/robot/EmergencyCaseSummary.vue";
import EmergencyDialoguePanel from "../components/robot/EmergencyDialoguePanel.vue";
import EmergencyEscalationCard from "../components/robot/EmergencyEscalationCard.vue";
import EmergencyNavigationProgress from "../components/robot/EmergencyNavigationProgress.vue";
import EmergencyRealtimeBridge from "../components/robot/EmergencyRealtimeBridge.vue";
import EmergencySafetyPanel from "../components/robot/EmergencySafetyPanel.vue";
import EmergencyTimeline from "../components/robot/EmergencyTimeline.vue";
import Go2VideoPanel from "../components/robot/Go2VideoPanel.vue";
import { useRobotEmergency } from "../composables/useRobotEmergency";
import type { RobotDialogueIntent } from "../types/robot";
import {
  MOCK_ENVIRONMENT_NOTICE,
  robotExecutionStateLabel,
} from "../utils/robotPresentation";

const props = defineProps<{
  incidentId: string | null;
  sessionUser: SessionUser;
}>();

const emergency = useRobotEmergency(props.incidentId, props.sessionUser.id);

const state = computed(() => emergency.emergencyCase.value?.execution_state ?? null);
const controlOwner = computed(() => emergency.emergencyCase.value?.control_owner ?? null);
const blockedBy = computed(() => {
  const fromInterlock = emergency.safetyInterlock.value?.blocked_by ?? [];
  const caseError = emergency.emergencyCase.value?.error_code;
  return [...new Set([...fromInterlock, ...(caseError ? [caseError] : [])])];
});
const prompt = computed<Record<string, unknown> | null>(() => {
  const value = emergency.emergencyCase.value?.metadata.mock_prompt;
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
});
const connectionLabel = computed(() => ({
  idle: "等待案例建立",
  connecting: "实时通道连接中",
  connected: "实时通道已连接",
  reconnecting: "实时通道重连中",
  disconnected: "实时通道已断开",
  error: "实时通道异常",
})[emergency.connectionState.value]);
const pageMeta = computed(() => [
  "高优先级事件",
  `事件 ${props.incidentId ?? "无效"}`,
  `任务 ${emergency.bundle.value?.robot_task_id ?? "尚未创建"}`,
  `状态 ${robotExecutionStateLabel(state.value)}`,
  `更新 ${formatTime(emergency.lastUpdatedAt.value)}`,
]);

function formatTime(value: string | null) {
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "尚未更新";
}

function goBack(page: "overview" | "robot-tasks") {
  window.location.hash = page === "overview" ? "#/overview" : "#/robot-tasks";
}

function handleDialogueResult(intent: RobotDialogueIntent) {
  void emergency.submitDialogueResult(intent);
}
</script>

<template>
  <section class="page-stack emergency-page">
    <PageHeader
      eyebrow="High Priority / Mock Emergency"
      title="机器人应急处置"
      description="以文字事件、Mock 导航状态、机器人现场画面和人工确认完成跌倒事件处置。所有状态推进均由主系统后端控制。"
      :meta="pageMeta"
    >
      <template #actions>
        <div class="header-actions">
          <span class="connection" :class="`is-${emergency.connectionState.value}`">
            <PlugZap :size="14" /> {{ connectionLabel }}
          </span>
          <button type="button" class="secondary" @click="goBack('overview')">
            <ArrowLeft :size="14" /> 告警中心
          </button>
          <button type="button" class="secondary" @click="goBack('robot-tasks')">
            机器人任务中心
          </button>
          <button
            type="button"
            :disabled="emergency.refreshing.value || !incidentId || Boolean(emergency.contractIssue.value)"
            @click="emergency.refresh()"
          >
            <RefreshCw :size="14" :class="{ spinning: emergency.refreshing.value }" />
            刷新
          </button>
        </div>
      </template>
    </PageHeader>

    <div class="mock-banner">
      <Shield :size="20" />
      <div>
        <strong>{{ MOCK_ENVIRONMENT_NOTICE }}</strong>
        <p>到达、语音询问、对话结果和返航均为受控模拟；当前未生成或播放真实音频。</p>
      </div>
      <code>provider=mock · real_motion_enabled=false</code>
    </div>

    <div v-if="!incidentId" class="page-alert page-alert--critical" role="alert">
      <CircleAlert :size="19" />
      <div>
        <strong>incident_id 缺失或格式非法</strong>
        <p>请从有效跌倒告警的“进入应急处置”按钮打开。本页未向后端发送任何请求。</p>
      </div>
    </div>

    <div v-if="emergency.contractIssue.value" class="page-alert page-alert--critical" role="alert">
      <CircleAlert :size="19" />
      <div>
        <strong>接口安全契约异常</strong>
        <p>{{ emergency.contractIssue.value.message }}</p>
        <code>{{ emergency.contractIssue.value.code }} · {{ emergency.contractIssue.value.endpoint }}</code>
      </div>
    </div>

    <div v-else-if="emergency.loadError.value" class="page-alert" role="alert">
      <CircleAlert :size="19" />
      <div>
        <strong>{{ emergency.loadError.value.code ?? "PARTIAL_DATA_UNAVAILABLE" }}</strong>
        <p>{{ emergency.loadError.value.message }}</p>
      </div>
    </div>

    <div v-if="emergency.loading.value && !emergency.bundle.value" class="loading-state">
      <span></span><span></span><span></span>
      <p>正在读取应急案例、对话与安全联锁…</p>
    </div>

    <template v-else-if="incidentId">
      <div v-if="emergency.notFound.value" class="page-alert">
        <CircleAlert :size="19" />
        <div>
          <strong>应急案例尚未建立</strong>
          <p v-if="emergency.bootstrapAlarm.value">
            已保留当前跌倒告警的文字元数据，可在右侧执行严格的 Mock 派发。
          </p>
          <p v-else>未找到可用于派发的区域信息，请返回告警中心人工复核。</p>
        </div>
      </div>

      <div class="emergency-layout">
        <main class="emergency-layout__main">
          <section class="video-section">
            <div class="section-heading">
              <div><p>ROBOT ON-SITE VIEW</p><h2>机器人现场画面</h2></div>
              <span>Go2 8093 视频链路，与 Mock 导航控制隔离</span>
            </div>
            <Go2VideoPanel />
          </section>

          <EmergencyNavigationProgress
            :state="state"
            :control-owner="controlOwner"
            :blocked-by="blockedBy"
          />
          <EmergencyDialoguePanel
            :turns="emergency.dialogueTurns.value"
            :state="state"
            :prompt="prompt"
            :disabled="emergency.operationsDisabled.value"
            :submitting="emergency.activeOperation.value === 'dialogue-result'"
            @result="handleDialogueResult"
          />
          <EmergencyTimeline
            :events="emergency.bundle.value?.navigation_events ?? []"
            :live-events="emergency.liveEvents.value"
          />
        </main>

        <aside class="emergency-layout__side">
          <EmergencyCaseSummary
            :emergency-case="emergency.emergencyCase.value"
            :bootstrap-alarm="emergency.bootstrapAlarm.value"
          />
          <EmergencySafetyPanel
            :interlock="emergency.safetyInterlock.value"
            :control-owner="controlOwner"
          />
          <EmergencyEscalationCard
            :intent="emergency.emergencyCase.value?.dialogue_intent ?? null"
            :status="emergency.emergencyCase.value?.status ?? null"
          />
          <EmergencyActionPanel
            :emergency-case="emergency.emergencyCase.value"
            :has-bootstrap-alarm="Boolean(emergency.bootstrapAlarm.value)"
            :active-operation="emergency.activeOperation.value"
            :disabled="emergency.operationsDisabled.value"
            :return-allowed="emergency.returnEvaluation.value.allowed"
            :return-blocked-by="emergency.returnEvaluation.value.blockedBy"
            :feedback="emergency.operationFeedback.value"
            @acknowledge="emergency.acknowledge"
            @dispatch="emergency.dispatch"
            @resume="emergency.resume"
            @start-dialogue="emergency.startDialogue"
            @resolve-return="emergency.resolveAndReturn"
            @complete-return="emergency.completeReturn"
          />
        </aside>
      </div>

      <EmergencyRealtimeBridge
        v-if="emergency.bundle.value"
        :incident-id="incidentId"
        @snapshot="emergency.acceptWebSocketSnapshot"
        @event="emergency.acceptWebSocketEvent"
        @refresh="emergency.refresh"
        @contract-error="emergency.registerContractError"
        @connection="emergency.setConnectionState"
      />
    </template>
  </section>
</template>

<style scoped>
.emergency-page { --emergency-ink: #102a43; padding-bottom: 34px; }
.header-actions { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: 7px; }
.header-actions button, .connection { display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-height: 34px; padding: 7px 10px; border: 1px solid #24679f; border-radius: 9px; background: #245f98; color: #fff; font: inherit; font-size: .69rem; font-weight: 780; }
.header-actions button { cursor: pointer; }
.header-actions button.secondary { border-color: #c9d7e2; background: #f8fbfd; color: #41647d; }
.header-actions button:disabled { cursor: not-allowed; opacity: .48; }
.connection { border-color: #cbd9e4; background: #f6f9fb; color: #5c7487; }
.connection.is-connected { border-color: #a9ddca; background: #edf9f4; color: #087653; }
.connection.is-reconnecting, .connection.is-connecting { border-color: #edca8f; background: #fff8e8; color: #8b5a0a; }
.connection.is-error, .connection.is-disconnected { border-color: #efc1bc; background: #fff3f1; color: #a53630; }
.mock-banner { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 12px; padding: 14px 16px; border: 1px solid #b8d2ec; border-left: 4px solid #3d7fb8; border-radius: 13px; background: #eef6fd; color: #2d638d; }
.mock-banner strong { color: #174e78; font-size: .82rem; }
.mock-banner p { margin: 3px 0 0; color: #4f718c; font-size: .7rem; line-height: 1.45; }
.mock-banner code { color: #365d78; font-size: .62rem; white-space: nowrap; }
.page-alert { display: grid; grid-template-columns: auto 1fr; gap: 9px; padding: 13px 15px; border: 1px solid #edca8f; border-radius: 12px; background: #fff8e8; color: #8b5a0a; }
.page-alert--critical { border-color: #efc1bc; background: #fff3f1; color: #a53630; }
.page-alert strong { font-size: .76rem; }
.page-alert p { margin: 3px 0 0; font-size: .69rem; line-height: 1.45; }
.page-alert code { display: block; margin-top: 4px; font-size: .59rem; }
.loading-state { min-height: 300px; display: grid; grid-template-columns: repeat(3, 12px); place-content: center; gap: 7px; border: 1px solid #dce6f0; border-radius: 18px; background: #fff; color: #61798e; text-align: center; }
.loading-state span { width: 12px; height: 12px; border-radius: 50%; background: #6f9fc4; animation: pulse 1.2s ease-in-out infinite; }
.loading-state span:nth-child(2) { animation-delay: 120ms; }
.loading-state span:nth-child(3) { animation-delay: 240ms; }
.loading-state p { grid-column: 1 / -1; margin: 8px 0 0; font-size: .72rem; }
.emergency-layout { display: grid; grid-template-columns: minmax(0, 2fr) minmax(310px, .9fr); gap: 18px; align-items: start; }
.emergency-layout__main, .emergency-layout__side { display: grid; gap: 16px; min-width: 0; }
.emergency-layout__side { position: sticky; top: 16px; }
.video-section { padding: 18px; border: 1px solid #dce6f0; border-radius: 18px; background: #fff; box-shadow: 0 8px 24px rgba(35, 78, 112, .055); }
.section-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 14px; margin-bottom: 12px; }
.section-heading p { margin: 0; color: #47779c; font-size: .63rem; font-weight: 850; letter-spacing: .09em; }
.section-heading h2 { margin: 3px 0 0; color: var(--emergency-ink); font-size: 1rem; }
.section-heading span { color: #718698; font-size: .63rem; text-align: right; }
.video-section :deep(.go2-video-panel) { padding: 0; border: 0; border-radius: 0; box-shadow: none; }
.spinning { animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@keyframes pulse { 0%, 100% { opacity: .35; transform: scale(.82); } 50% { opacity: 1; transform: scale(1); } }
@media (prefers-reduced-motion: reduce) { .spinning, .loading-state span { animation: none; } }
@media (max-width: 1180px) { .emergency-layout { grid-template-columns: 1fr; } .emergency-layout__side { position: static; grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 760px) {
  .header-actions { justify-content: flex-start; }
  .mock-banner { grid-template-columns: auto 1fr; }
  .mock-banner code { grid-column: 2; white-space: normal; }
  .emergency-layout__side { grid-template-columns: 1fr; }
  .section-heading { align-items: flex-start; flex-direction: column; }
  .section-heading span { text-align: left; }
}
</style>
