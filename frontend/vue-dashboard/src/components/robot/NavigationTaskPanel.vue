<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { Hand, Pause, Play, ShieldAlert, Square } from "lucide-vue-next";
import type {
  RobotControlOwner,
  RobotNavigationExecutionState,
  RobotNavigationTask,
} from "../../types/robot";
import {
  robotControlOwnerLabel,
  robotExecutionStateLabel,
} from "../../utils/robotPresentation";

const props = defineProps<{
  task: RobotNavigationTask | null;
  executionState?: RobotNavigationExecutionState;
  controlOwner?: RobotControlOwner;
  activeOperation: string | null;
}>();

const emit = defineEmits<{
  pause: [];
  resume: [];
  stop: [];
  "manual-acquire": [];
  "manual-release": [];
}>();

const stopConfirmed = ref(false);
const state = computed(() => props.task?.execution_state ?? props.executionState ?? "created");
const owner = computed(() => props.task?.control_owner ?? props.controlOwner ?? "NONE");
const taskId = computed(() => props.task?.task_id ?? null);
const busy = computed(() => Boolean(props.activeOperation));
const terminal = computed(() => ["completed", "failed", "cancelled"].includes(state.value));
const canPause = computed(() => Boolean(taskId.value) && ["navigating", "returning_home"].includes(state.value));
const canResume = computed(() => Boolean(taskId.value) && ["paused_admin", "paused_manual"].includes(state.value));
const canAcquire = computed(() => Boolean(taskId.value) && owner.value !== "MANUAL" && !terminal.value);
const canRelease = computed(() => Boolean(taskId.value) && owner.value === "MANUAL");

watch(taskId, () => { stopConfirmed.value = false; });
</script>

<template>
  <section class="task-card">
    <div class="task-card__heading">
      <span class="icon"><ShieldAlert :size="18" /></span>
      <div>
        <h3>任务与控制权</h3>
        <p>所有操作进入后端状态机与安全联锁，不发送方向或速度指令。</p>
      </div>
    </div>

    <div class="status-grid">
      <div>
        <span>任务</span>
        <strong>{{ taskId ?? "无活动任务" }}</strong>
      </div>
      <div>
        <span>执行状态</span>
        <strong>{{ robotExecutionStateLabel(state) }}</strong>
      </div>
      <div>
        <span>控制权</span>
        <strong :class="{ manual: owner === 'MANUAL' }">{{ robotControlOwnerLabel(owner) }}</strong>
      </div>
      <div>
        <span>Mock 进度</span>
        <strong>{{ Math.round(Number(task?.progress ?? 0)) }}%</strong>
      </div>
    </div>

    <div class="progress" aria-label="Mock 任务进度">
      <span :style="{ width: `${Math.min(100, Math.max(0, Number(task?.progress ?? 0)))}%` }"></span>
    </div>

    <div class="actions">
      <button type="button" :disabled="busy || !canPause" @click="emit('pause')">
        <Pause :size="15" />暂停
      </button>
      <button type="button" :disabled="busy || !canResume" @click="emit('resume')">
        <Play :size="15" />继续
      </button>
      <button
        v-if="!canRelease"
        type="button"
        :disabled="busy || !canAcquire"
        @click="emit('manual-acquire')"
      >
        <Hand :size="15" />申请遥控接管
      </button>
      <button v-else type="button" class="manual-button" :disabled="busy" @click="emit('manual-release')">
        <Hand :size="15" />释放控制权
      </button>
    </div>

    <p v-if="canRelease" class="manual-note">
      第 1 步已申请遥控接管；第 2 步释放控制权后不会自动恢复；第 3 步必须点击“继续”并重新通过安全联锁。
    </p>

    <div v-if="taskId && !terminal" class="stop-zone">
      <label>
        <input v-model="stopConfirmed" type="checkbox" />
        确认停止当前 Mock 任务。停止后由后端决定返航/取消状态，不自动发起移动。
      </label>
      <button type="button" class="stop-button" :disabled="busy || !stopConfirmed" @click="emit('stop')">
        <Square :size="14" />停止任务
      </button>
    </div>
  </section>
</template>

<style scoped>
.task-card { display: grid; gap: 15px; padding: 20px; border: 1px solid #dbe4ee; border-radius: 18px; background: #fff; }
.task-card__heading { display: grid; grid-template-columns: auto 1fr; gap: 11px; }
.icon { display: grid; width: 36px; height: 36px; place-items: center; border-radius: 10px; background: #f1f5f9; color: #334155; }
h3 { margin: 0 0 3px; color: #0f172a; font-size: .98rem; }
p { margin: 0; color: #64748b; font-size: .75rem; line-height: 1.5; }
.status-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.status-grid div { display: grid; gap: 3px; padding: 9px 10px; border-radius: 10px; background: #f8fafc; }
.status-grid span { color: #64748b; font-size: .67rem; }
.status-grid strong { overflow: hidden; color: #1e293b; font-size: .76rem; text-overflow: ellipsis; white-space: nowrap; }
.status-grid strong.manual { color: #b45309; }
.progress { height: 6px; overflow: hidden; border-radius: 999px; background: #e2e8f0; }
.progress span { display: block; height: 100%; border-radius: inherit; background: #2563eb; transition: width .3s ease; }
.actions { display: grid; grid-template-columns: repeat(3, 1fr); gap: 7px; }
button { display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-height: 37px; padding: 7px 9px; border: 1px solid #cbd5e1; border-radius: 9px; background: #fff; color: #334155; font-size: .74rem; font-weight: 750; cursor: pointer; }
button:disabled { opacity: .43; cursor: not-allowed; }
.manual-button { border-color: #f59e0b; background: #fffbeb; color: #92400e; }
.manual-note { padding: 9px 10px; border-radius: 9px; background: #fffbeb; color: #92400e; }
.stop-zone { display: grid; gap: 9px; padding-top: 12px; border-top: 1px solid #fee2e2; }
.stop-zone label { display: flex; align-items: flex-start; gap: 7px; color: #991b1b; font-size: .71rem; line-height: 1.45; }
.stop-zone input { margin-top: 2px; }
.stop-button { border-color: #fecaca; color: #b91c1c; }
@media (max-width: 650px) { .actions { grid-template-columns: 1fr; } }
</style>
