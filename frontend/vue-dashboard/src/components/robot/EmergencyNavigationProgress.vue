<script setup lang="ts">
import { computed } from "vue";
import { CircleCheck, Navigation, PauseCircle, ShieldAlert } from "lucide-vue-next";
import type { RobotControlOwner, RobotNavigationExecutionState } from "../../types/robot";
import {
  robotBlockedReason,
  robotControlOwnerLabel,
  robotExecutionStateLabel,
} from "../../utils/robotPresentation";

const props = defineProps<{
  state: RobotNavigationExecutionState | null;
  controlOwner: RobotControlOwner | null;
  blockedBy: string[];
}>();

const phases: Array<{ label: string; states: RobotNavigationExecutionState[] }> = [
  { label: "准备", states: ["created", "safety_checking", "blocked", "queued"] },
  { label: "前往现场", states: ["navigating", "paused_manual", "paused_admin", "arrived"] },
  { label: "现场询问", states: ["voice_prompting", "waiting_response"] },
  { label: "处置判断", states: ["safe_response", "help_requested", "no_response", "uncertain", "waiting_admin_confirmation"] },
  { label: "返航闭环", states: ["returning_home", "completed", "failed", "cancelled"] },
];

const activePhase = computed(() =>
  phases.findIndex((phase) => props.state && phase.states.includes(props.state)),
);
</script>

<template>
  <article class="progress-card">
    <header>
      <div>
        <p>MOCK NAVIGATION PROGRESS</p>
        <h2>应急执行进度</h2>
      </div>
      <span v-if="controlOwner === 'MANUAL'" class="owner owner--manual">
        <PauseCircle :size="14" /> 人工接管
      </span>
      <span v-else class="owner"><Navigation :size="14" /> {{ robotControlOwnerLabel(controlOwner) }}</span>
    </header>

    <div class="phase-rail">
      <section
        v-for="(phase, index) in phases"
        :key="phase.label"
        :class="{ 'is-active': index === activePhase, 'is-past': activePhase > index }"
      >
        <span class="phase-dot">
          <CircleCheck v-if="activePhase > index" :size="15" />
          <span v-else>{{ index + 1 }}</span>
        </span>
        <div>
          <strong>{{ phase.label }}</strong>
          <p>{{ index === activePhase && state ? robotExecutionStateLabel(state) : "—" }}</p>
        </div>
      </section>
    </div>

    <div v-if="state === 'blocked'" class="blocked-notice">
      <ShieldAlert :size="18" />
      <div>
        <strong>机器人无法出动，请人工处置</strong>
        <p v-if="blockedBy.length">
          <span v-for="code in blockedBy" :key="code">
            {{ robotBlockedReason(code) }}（{{ code }}）
          </span>
        </p>
        <p v-else>安全联锁未通过</p>
      </div>
    </div>
    <p class="progress-note">页面只显示后端 REST / WebSocket 状态，不会自行推进阶段。</p>
  </article>
</template>

<style scoped>
.progress-card { padding: 20px; border: 1px solid #dce6f0; border-radius: 18px; background: #fff; box-shadow: 0 8px 24px rgba(35, 78, 112, .055); }
header { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; }
header p { margin: 0; color: #47779c; font-size: .64rem; font-weight: 850; letter-spacing: .09em; }
h2 { margin: 4px 0 0; color: #102a43; font-size: 1rem; }
.owner { display: inline-flex; align-items: center; gap: 5px; padding: 6px 8px; border: 1px solid #d6e1e9; border-radius: 8px; background: #f5f8fa; color: #577187; font-size: .66rem; font-weight: 800; }
.owner--manual { border-color: #f0cf91; background: #fff8e7; color: #8a5a09; }
.phase-rail { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 6px; margin-top: 18px; }
.phase-rail section { position: relative; display: grid; justify-items: center; gap: 7px; min-width: 0; padding: 10px 5px; color: #91a2af; text-align: center; }
.phase-rail section:not(:last-child)::after { content: ""; position: absolute; left: calc(50% + 16px); right: calc(-50% + 16px); top: 22px; height: 2px; background: #dfe7ed; }
.phase-dot { position: relative; z-index: 1; display: grid; width: 26px; height: 26px; place-items: center; border: 2px solid #d7e1e8; border-radius: 50%; background: #fff; font-size: .65rem; font-weight: 850; }
.phase-rail strong { display: block; color: #60788b; font-size: .68rem; }
.phase-rail p { margin: 3px 0 0; font-size: .61rem; line-height: 1.35; }
.phase-rail .is-active { color: #1c67a3; }
.phase-rail .is-active .phase-dot { border-color: #2e78b5; background: #eaf4fc; box-shadow: 0 0 0 4px #eef6fc; }
.phase-rail .is-active strong { color: #174f7d; }
.phase-rail .is-past .phase-dot { border-color: #3e9a75; background: #e9f7f1; color: #087653; }
.phase-rail .is-past:not(:last-child)::after { background: #92cfb7; }
.blocked-notice { display: grid; grid-template-columns: auto 1fr; gap: 9px; margin-top: 14px; padding: 11px 12px; border: 1px solid #efc1bc; border-radius: 10px; background: #fff3f1; color: #a53630; }
.blocked-notice strong { font-size: .73rem; }
.blocked-notice p, .progress-note { margin: 3px 0 0; font-size: .65rem; line-height: 1.45; }
.blocked-notice p span { display: block; }
.progress-note { color: #718698; }
@media (max-width: 760px) { .phase-rail { grid-template-columns: 1fr; } .phase-rail section { grid-template-columns: auto 1fr; justify-items: start; text-align: left; } .phase-rail section::after { display: none; } }
</style>
