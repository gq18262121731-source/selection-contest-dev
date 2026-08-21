<script setup lang="ts">
import { computed } from "vue";
import {
  BellRing,
  Check,
  CirclePlay,
  Home,
  MessageSquareText,
  RotateCcw,
} from "lucide-vue-next";
import type { EmergencyOperation, EmergencyOperationFeedback } from "../../composables/useRobotEmergency";
import type {
  RobotEmergencyCase,
  RobotNavigationExecutionState,
} from "../../types/robot";
import { robotBlockedReason } from "../../utils/robotPresentation";

const props = defineProps<{
  emergencyCase: RobotEmergencyCase | null;
  hasBootstrapAlarm: boolean;
  activeOperation: EmergencyOperation | null;
  disabled: boolean;
  returnAllowed: boolean;
  returnBlockedBy: string[];
  feedback: EmergencyOperationFeedback | null;
}>();

const emit = defineEmits<{
  acknowledge: [];
  dispatch: [];
  resume: [];
  startDialogue: [];
  resolveReturn: [];
  completeReturn: [];
}>();

const state = computed<RobotNavigationExecutionState | null>(
  () => props.emergencyCase?.execution_state ?? null,
);
const showDispatch = computed(
  () => !props.emergencyCase?.robot_task_id || ["created", "blocked"].includes(state.value ?? ""),
);
const showResume = computed(() => state.value === "paused_admin" || state.value === "paused_manual");
const showDialogueStart = computed(() => state.value === "navigating" || state.value === "arrived");
const escalationState = computed(
  () => ["help_requested", "no_response", "uncertain"].includes(state.value ?? ""),
);
</script>

<template>
  <article class="action-card">
    <header>
      <div><p>CONTROLLED ACTIONS</p><h2>应急操作</h2></div>
      <code>real_motion_enabled=false</code>
    </header>

    <div class="actions">
      <button
        v-if="emergencyCase && !emergencyCase.acknowledged_by"
        type="button"
        :disabled="disabled"
        @click="emit('acknowledge')"
      >
        <Check :size="15" /> {{ activeOperation === "acknowledge" ? "记录中…" : "我已知晓" }}
      </button>
      <button
        v-if="showDispatch && (emergencyCase || hasBootstrapAlarm)"
        type="button"
        class="is-primary"
        :disabled="disabled"
        @click="emit('dispatch')"
      >
        <CirclePlay :size="15" /> {{ activeOperation === "dispatch" ? "派发中…" : "派发机器人" }}
      </button>
      <button v-if="showResume" type="button" :disabled="disabled" @click="emit('resume')">
        <RotateCcw :size="15" /> {{ activeOperation === "resume" ? "联锁检查中…" : "继续导航" }}
      </button>
      <button
        v-if="showDialogueStart"
        type="button"
        class="is-primary"
        :disabled="disabled"
        @click="emit('startDialogue')"
      >
        <MessageSquareText :size="15" />
        {{ activeOperation === "start-dialogue" ? "推进中…" : "模拟到达并开始询问" }}
      </button>
      <button
        v-if="state === 'waiting_admin_confirmation' && emergencyCase?.dialogue_intent === 'safe_response'"
        type="button"
        class="is-safe"
        :disabled="disabled || !returnAllowed"
        @click="emit('resolveReturn')"
      >
        <Home :size="15" />
        {{ activeOperation === "resolve-return" ? "确认并请求返航中…" : "管理员确认并返回待命区" }}
      </button>
      <button
        v-if="state === 'returning_home'"
        type="button"
        class="is-safe"
        :disabled="disabled"
        @click="emit('completeReturn')"
      >
        <Home :size="15" />
        {{ activeOperation === "complete-return" ? "完成中…" : "模拟完成返航" }}
      </button>
    </div>

    <div v-if="escalationState" class="escalation">
      <BellRing :size="17" />
      <div><strong>已升级人工处置</strong><p>机器人保持原地，返航入口已禁用。</p></div>
    </div>
    <div v-if="state === 'waiting_admin_confirmation' && !returnAllowed" class="blocked">
      <strong>返航前置条件未满足</strong>
      <p v-for="code in returnBlockedBy" :key="code">
        {{ robotBlockedReason(code) }} <code>{{ code }}</code>
      </p>
    </div>
    <div v-if="feedback" class="feedback" :class="`is-${feedback.kind}`" role="status">
      <strong>{{ feedback.code ?? (feedback.kind === "success" ? "OK" : "OPERATION_FAILED") }}</strong>
      <p>{{ feedback.message }}</p>
      <code v-if="feedback.blockedBy?.length">{{ feedback.blockedBy.join(" · ") }}</code>
    </div>

    <p class="boundary">
      当前后端未提供应急专用暂停/停止接口，本页不会绕用运动控制或伪造任务终态；需要取消时请返回机器人任务中心。
    </p>
    <p v-if="state === 'completed'" class="terminal-note">
      本次应急处置已完成，页面进入只读终态。历史记录仍可查看，但不能再次推进任务。
    </p>
  </article>
</template>

<style scoped>
.action-card { padding: 18px; border: 1px solid #dce6f0; border-radius: 18px; background: #fff; box-shadow: 0 8px 24px rgba(35, 78, 112, .055); }
header { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
header p { margin: 0; color: #47779c; font-size: .62rem; font-weight: 850; letter-spacing: .09em; }
h2 { margin: 3px 0 0; color: #102a43; font-size: .98rem; }
header code { color: #58758a; font-size: .58rem; }
.actions { display: grid; gap: 8px; margin-top: 14px; }
.actions button { display: inline-flex; align-items: center; justify-content: center; gap: 7px; min-height: 40px; padding: 9px 11px; border: 1px solid #cbd9e4; border-radius: 9px; background: #f7fafc; color: #3f627b; font: inherit; font-size: .7rem; font-weight: 800; cursor: pointer; }
.actions button.is-primary { border-color: #276da6; background: #245f98; color: #fff; }
.actions button.is-safe { border-color: #14805e; background: #087653; color: #fff; }
.actions button:disabled { cursor: not-allowed; opacity: .48; }
.escalation, .blocked, .feedback { display: grid; grid-template-columns: auto 1fr; gap: 8px; margin-top: 11px; padding: 10px; border: 1px solid #efc1bc; border-radius: 9px; background: #fff3f1; color: #a53630; }
.escalation strong, .blocked strong, .feedback strong { font-size: .68rem; }
.escalation p, .blocked p, .feedback p { margin: 3px 0 0; font-size: .63rem; line-height: 1.45; }
.blocked, .feedback { display: block; border-color: #edca8f; background: #fff8e8; color: #8b5a0a; }
.feedback.is-success { border-color: #a9ddca; background: #edf9f4; color: #087653; }
.feedback code { display: block; margin-top: 5px; font-size: .58rem; }
.boundary { margin: 12px 0 0; padding-top: 11px; border-top: 1px solid #e5ecf1; color: #718698; font-size: .62rem; line-height: 1.5; }
.terminal-note { margin: 10px 0 0; padding: 10px; border-radius: 9px; background: #edf9f4; color: #087653; font-size: .66rem; line-height: 1.5; }
</style>
