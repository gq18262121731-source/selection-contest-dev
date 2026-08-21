<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { Bot, Camera, RefreshCw, ShieldAlert, Wifi } from "lucide-vue-next";
import { api, type RobotObservation, type RobotSocketEvent, type RobotTask, type RobotTaskTimeline } from "../api/client";
import PageHeader from "../components/layout/PageHeader.vue";
import { normalizeRobotCapabilityStatus } from "../utils/robotCapabilityStatus";

const tasks = ref<RobotTask[]>([]);
const selectedTaskId = ref("");
const timeline = ref<RobotTaskTimeline[]>([]);
const observation = ref<RobotObservation | null>(null);
const robotStatus = ref<Record<string, unknown> | null>(null);
const loading = ref(false);
const detailLoading = ref(false);
const errorMessage = ref("");

let robotSocket: WebSocket | null = null;
let refreshTimer: number | null = null;
let reconnectTimer: number | null = null;
let socketRuntimeActive = false;
let taskListController: AbortController | null = null;
let taskDetailController: AbortController | null = null;
let taskListRequestId = 0;
let taskDetailRequestId = 0;

const currentTask = computed(() =>
  tasks.value.find((task) => ["RUNNING", "QUEUED", "BLOCKED"].includes(task.status)) ?? tasks.value[0] ?? null,
);

const selectedTask = computed(() =>
  tasks.value.find((task) => task.task_id === selectedTaskId.value) ?? currentTask.value,
);

const gatewayPayload = computed(() => (robotStatus.value?.gateway ?? {}) as Record<string, unknown>);
const gatewayData = computed(() => (gatewayPayload.value.data ?? {}) as Record<string, unknown>);
const robotOnline = computed(() =>
  Boolean(gatewayData.value.robotOnline ?? gatewayData.value.robot_online ?? gatewayData.value.online ?? gatewayPayload.value.ok),
);
const motionCapability = computed(() =>
  normalizeRobotCapabilityStatus(
    gatewayData.value.motionReady ?? gatewayData.value.motion_ready,
    "未收到机器人运动状态数据",
  ),
);
const batteryValue = computed(() => {
  const robot = (gatewayData.value.robot ?? {}) as Record<string, unknown>;
  const value = robot.battery ?? gatewayData.value.battery;
  return typeof value === "number" ? `${value}%` : "-";
});
const runtimeMode = computed(() => {
  const mode = gatewayData.value.mode ?? gatewayData.value.runtime_mode ?? gatewayData.value.mock;
  if (mode === true || mode === "mock") return "模拟";
  if (mode === "real") return "真实模式（本演示禁用）";
  return gatewayPayload.value.ok ? "未验证" : "不可用";
});

const pageMeta = computed(() => [
  `任务数 ${tasks.value.length}`,
  selectedTask.value ? `当前 ${selectedTask.value.status}` : "暂无任务",
  `网关 ${gatewayPayload.value.ok ? "在线" : "不可用"}`,
]);

const statusLabel: Record<string, string> = {
  QUEUED: "排队中",
  RUNNING: "执行中",
  COMPLETED: "已完成",
  FAILED: "失败",
  CANCELLED: "已取消",
  BLOCKED: "已阻塞",
};

const stepLabel: Record<string, string> = {
  RECEIVED: "固定摄像头发现",
  PREFLIGHT: "机器人预检",
  MOVING: "移动",
  ARRIVED: "到达",
  CAMERA_CHECK: "相机取证",
  VOICE_PROMPT: "语音询问",
  WAITING_RESPONSE: "老人回应",
  REPORTING: "告警融合",
};

const outcomeLabel: Record<string, string> = {
  SAFE: "老人有回应",
  NEED_HELP: "需要帮助",
  NO_RESPONSE: "无回应",
  UNKNOWN: "结果未知",
};

function formatTime(value?: string | null) {
  if (!value) return "-";
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

function selectTask(taskId: string) {
  if (taskId === selectedTaskId.value) return;
  selectedTaskId.value = taskId;
  timeline.value = [];
  observation.value = null;
  void loadTaskDetail(taskId);
}

async function loadTasks() {
  taskListController?.abort();
  const controller = new AbortController();
  const requestId = ++taskListRequestId;
  taskListController = controller;
  loading.value = true;
  errorMessage.value = "";
  try {
    const [status, taskList] = await Promise.all([
      api.getRobotStatus(controller.signal).catch(() => null),
      api.listRobotTasks({ limit: 100 }, controller.signal),
    ]);
    if (controller.signal.aborted || requestId !== taskListRequestId) return;
    robotStatus.value = (status ?? {}) as Record<string, unknown>;
    tasks.value = taskList.tasks;
    if (
      tasks.value.length
      && (!selectedTaskId.value || !tasks.value.some((task) => task.task_id === selectedTaskId.value))
    ) {
      selectedTaskId.value = currentTask.value?.task_id ?? tasks.value[0].task_id;
      timeline.value = [];
      observation.value = null;
    } else if (!tasks.value.length) {
      selectedTaskId.value = "";
      timeline.value = [];
      observation.value = null;
    }
    if (selectedTaskId.value) {
      await loadTaskDetail(selectedTaskId.value);
    }
  } catch (error) {
    if (controller.signal.aborted || requestId !== taskListRequestId) return;
    errorMessage.value = error instanceof Error ? error.message : "机器人任务加载失败";
  } finally {
    if (taskListController === controller) {
      taskListController = null;
      loading.value = false;
    }
  }
}

async function loadTaskDetail(taskId: string) {
  taskDetailController?.abort();
  const controller = new AbortController();
  const requestId = ++taskDetailRequestId;
  taskDetailController = controller;
  detailLoading.value = true;
  try {
    const [timelinePayload, observationPayload] = await Promise.all([
      api.getRobotTaskTimeline(taskId, controller.signal),
      api.getRobotTaskObservation(taskId, controller.signal),
    ]);
    if (
      controller.signal.aborted
      || requestId !== taskDetailRequestId
      || selectedTaskId.value !== taskId
    ) {
      return;
    }
    timeline.value = timelinePayload.timeline;
    observation.value = observationPayload.observation ?? null;
  } catch (error) {
    if (
      controller.signal.aborted
      || requestId !== taskDetailRequestId
      || selectedTaskId.value !== taskId
    ) {
      return;
    }
    timeline.value = [];
    observation.value = null;
    errorMessage.value = error instanceof Error ? error.message : "机器人任务详情加载失败";
  } finally {
    if (taskDetailController === controller) {
      taskDetailController = null;
      detailLoading.value = false;
    }
  }
}

function connectRobotSocket() {
  if (!socketRuntimeActive) return;
  if (reconnectTimer !== null) {
    window.clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (robotSocket) robotSocket.onclose = null;
  robotSocket?.close();
  robotSocket = api.alarmSocket();
  robotSocket.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data) as RobotSocketEvent;
      if (!payload.event_type?.startsWith("robot.")) return;
      void loadTasks();
    } catch {
      // ignore malformed websocket payloads
    }
  };
  robotSocket.onclose = () => {
    robotSocket = null;
    if (!socketRuntimeActive) return;
    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = null;
      connectRobotSocket();
    }, 2000);
  };
}

onMounted(() => {
  socketRuntimeActive = true;
  void loadTasks();
  connectRobotSocket();
  refreshTimer = window.setInterval(() => {
    void loadTasks();
  }, 10000);
});

onUnmounted(() => {
  socketRuntimeActive = false;
  taskListRequestId += 1;
  taskDetailRequestId += 1;
  taskListController?.abort();
  taskDetailController?.abort();
  taskListController = null;
  taskDetailController = null;
  if (reconnectTimer !== null) {
    window.clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (robotSocket) robotSocket.onclose = null;
  robotSocket?.close();
  robotSocket = null;
  if (refreshTimer !== null) {
    window.clearInterval(refreshTimer);
    refreshTimer = null;
  }
});
</script>

<template>
  <section class="page-stack robot-task-page">
    <PageHeader
      eyebrow="Go2 / Robot Task Center"
      title="机器人任务中心"
      description="从主系统持久化任务恢复 Go2 跌倒确认流程，实时展示状态、时间线、证据和告警融合结果。Mock 状态会明确标识，不伪造成真实硬件。"
      :meta="pageMeta"
    >
      <template #actions>
        <button type="button" class="robot-task-btn" :disabled="loading" @click="loadTasks">
          <RefreshCw :size="16" />
          刷新
        </button>
      </template>
    </PageHeader>

    <p v-if="errorMessage" class="robot-task-error">{{ errorMessage }}</p>

    <section class="robot-task-grid">
      <article class="robot-card robot-status-card">
        <div class="robot-card__title">
          <Bot :size="20" />
          <h2>Go2 状态</h2>
        </div>
        <dl class="robot-fields">
          <div><dt>型号</dt><dd>Go2 EDU</dd></div>
          <div><dt>模式</dt><dd>{{ runtimeMode }}</dd></div>
          <div><dt>在线</dt><dd>{{ robotOnline ? "在线" : "离线/未知" }}</dd></div>
          <div class="robot-capability-field" :data-status="motionCapability.status">
            <dt>运动能力</dt>
            <dd>{{ motionCapability.label }}</dd>
            <small>{{ motionCapability.reason }}</small>
          </div>
          <div><dt>电量</dt><dd>{{ batteryValue }}</dd></div>
          <div><dt>当前任务</dt><dd>{{ currentTask?.task_id ?? "-" }}</dd></div>
        </dl>
      </article>

      <article class="robot-card robot-current-card">
        <div class="robot-card__title">
          <ShieldAlert :size="20" />
          <h2>当前任务</h2>
        </div>
        <dl v-if="selectedTask" class="robot-fields">
          <div><dt>老人</dt><dd>{{ selectedTask.elder_name || selectedTask.elder_id || "-" }}</dd></div>
          <div><dt>目标位置</dt><dd>{{ selectedTask.location }}</dd></div>
          <div><dt>风险等级</dt><dd>{{ selectedTask.risk_level }}</dd></div>
          <div><dt>状态</dt><dd>{{ statusLabel[selectedTask.status] ?? selectedTask.status }}</dd></div>
          <div><dt>当前步骤</dt><dd>{{ stepLabel[selectedTask.current_step] ?? selectedTask.current_step }}</dd></div>
          <div><dt>创建时间</dt><dd>{{ formatTime(selectedTask.created_at) }}</dd></div>
        </dl>
        <p v-else class="robot-empty">暂无持久化机器人任务。</p>
      </article>
    </section>

    <section class="robot-task-main">
      <article class="robot-card robot-timeline-card">
        <div class="robot-card__title">
          <Wifi :size="20" />
          <h2>任务时间线</h2>
        </div>
        <p v-if="detailLoading" class="robot-empty" aria-live="polite">正在加载所选任务详情…</p>
        <ol v-else-if="timeline.length" class="robot-timeline">
          <li v-for="item in timeline" :key="`${item.callback_id ?? item.id}-${item.sequence}`">
            <span>{{ item.sequence }}</span>
            <div>
              <strong>{{ stepLabel[item.step] ?? item.step }}</strong>
              <p>{{ item.message || statusLabel[item.status] || item.status }}</p>
              <small>{{ formatTime(item.occurred_at) }}</small>
            </div>
          </li>
        </ol>
        <p v-else class="robot-empty">暂无时间线，等待 Go2 回调或 REST 恢复。</p>
      </article>

      <aside class="robot-side-stack">
        <article class="robot-card">
          <div class="robot-card__title">
            <Camera :size="20" />
            <h2>双视角证据</h2>
          </div>
          <div class="robot-evidence-grid">
            <div>
              <span>固定摄像头</span>
              <p>{{ selectedTask?.source_event_id ?? "暂无事件" }}</p>
            </div>
            <div>
              <span>Go2 靠近确认</span>
              <img
                v-if="selectedTask && observation?.snapshot_url"
                :src="api.getRobotArrivalEvidenceUrl(selectedTask.task_id)"
                alt="Go2 到达现场证据"
              />
              <p v-else>暂无证据</p>
            </div>
          </div>
        </article>

        <article class="robot-card">
          <div class="robot-card__title">
            <ShieldAlert :size="20" />
            <h2>回应结果</h2>
          </div>
          <dl class="robot-fields">
            <div><dt>结果</dt><dd>{{ observation?.response_type ? outcomeLabel[observation.response_type] : selectedTask?.outcome ?? "-" }}</dd></div>
            <div><dt>识别文本</dt><dd>{{ observation?.transcript ?? "暂无" }}</dd></div>
            <div><dt>相机可用</dt><dd>{{ observation?.camera_available === undefined || observation?.camera_available === null ? "-" : observation.camera_available ? "是" : "否" }}</dd></div>
            <div><dt>语音可用</dt><dd>{{ observation?.voice_available === undefined || observation?.voice_available === null ? "-" : observation.voice_available ? "是" : "否" }}</dd></div>
          </dl>
        </article>
      </aside>
    </section>

    <article class="robot-card robot-history-card">
      <div class="robot-card__title">
        <Bot :size="20" />
        <h2>历史任务</h2>
      </div>
      <div class="robot-history-list">
        <button
          v-for="task in tasks"
          :key="task.task_id"
          type="button"
          class="robot-history-item"
          :class="{ 'robot-history-item--active': selectedTask?.task_id === task.task_id }"
          @click="selectTask(task.task_id)"
        >
          <strong>{{ task.elder_name || task.elder_id || "未知老人" }}</strong>
          <span>{{ statusLabel[task.status] ?? task.status }} / {{ task.outcome ?? "等待结果" }}</span>
          <small>{{ task.location }} · {{ formatTime(task.created_at) }}</small>
        </button>
      </div>
    </article>
  </section>
</template>

<style scoped>
.robot-task-page {
  --robot-blue: #2563eb;
  --robot-ink: #0f172a;
}

.robot-task-btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 9px 12px;
  border: 1px solid #cbd5e1;
  border-radius: 10px;
  background: #fff;
  color: #1e3a8a;
  font: inherit;
  font-weight: 750;
  cursor: pointer;
}

.robot-task-error {
  margin: 0;
  padding: 12px 14px;
  border: 1px solid #fecaca;
  border-radius: 12px;
  background: #fff1f2;
  color: #b91c1c;
}

.robot-task-grid,
.robot-task-main {
  display: grid;
  grid-template-columns: minmax(0, 0.95fr) minmax(0, 1.05fr);
  gap: 18px;
}

.robot-task-main {
  grid-template-columns: minmax(0, 1.25fr) minmax(320px, 0.75fr);
  align-items: start;
}

.robot-side-stack {
  display: grid;
  gap: 18px;
}

.robot-card {
  padding: clamp(18px, 2vw, 24px);
  border: 1px solid #dbe5ef;
  border-radius: 22px;
  background: #fbfdff;
  box-shadow: 0 10px 32px rgba(15, 23, 42, 0.06);
}

.robot-card__title {
  display: flex;
  align-items: center;
  gap: 9px;
  color: var(--robot-blue);
}

.robot-card__title h2 {
  margin: 0;
  color: var(--robot-ink);
  font-size: 1.06rem;
}

.robot-fields {
  margin: 18px 0 0;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.robot-fields div {
  min-width: 0;
  padding: 10px 12px;
  border-radius: 12px;
  background: #f1f5f9;
}

.robot-fields dt {
  color: #64748b;
  font-size: 0.72rem;
}

.robot-fields dd {
  margin: 4px 0 0;
  overflow: hidden;
  color: #0f172a;
  font-size: 0.86rem;
  font-weight: 750;
  text-overflow: ellipsis;
}

.robot-capability-field small {
  display: block;
  margin-top: 5px;
  color: #64748b;
  font-size: 0.72rem;
  line-height: 1.45;
}

.robot-capability-field[data-status="READY"] dd { color: #087653; }
.robot-capability-field[data-status="NOT_READY"] dd { color: #a53630; }
.robot-capability-field[data-status="UNKNOWN"] dd { color: #64748b; }

.robot-timeline {
  margin: 18px 0 0;
  padding: 0;
  display: grid;
  gap: 12px;
  list-style: none;
}

.robot-timeline li {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 12px;
}

.robot-timeline li > span {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: #dbeafe;
  color: #1d4ed8;
  font-family: var(--font-mono);
  font-weight: 800;
}

.robot-timeline strong {
  color: #0f172a;
}

.robot-timeline p,
.robot-timeline small,
.robot-empty {
  margin: 3px 0 0;
  color: #64748b;
}

.robot-evidence-grid {
  margin-top: 18px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.robot-evidence-grid div {
  min-height: 148px;
  display: grid;
  align-content: center;
  gap: 8px;
  padding: 14px;
  border: 1px dashed #cbd5e1;
  border-radius: 14px;
  background: #f8fafc;
  text-align: center;
}

.robot-evidence-grid span {
  color: #475569;
  font-weight: 800;
}

.robot-evidence-grid p {
  margin: 0;
  color: #64748b;
  font-size: 0.82rem;
}

.robot-evidence-grid img {
  width: 100%;
  max-height: 190px;
  object-fit: cover;
  border-radius: 10px;
}

.robot-history-list {
  margin-top: 16px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 10px;
}

.robot-history-item {
  display: grid;
  gap: 4px;
  padding: 13px 14px;
  border: 1px solid #dbe5ef;
  border-radius: 14px;
  background: #fff;
  text-align: left;
  cursor: pointer;
}

.robot-history-item--active {
  border-color: #2563eb;
  background: #eff6ff;
}

.robot-history-item strong {
  color: #0f172a;
}

.robot-history-item span,
.robot-history-item small {
  color: #64748b;
}

@media (max-width: 1080px) {
  .robot-task-grid,
  .robot-task-main {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .robot-fields,
  .robot-evidence-grid {
    grid-template-columns: 1fr;
  }
}
</style>
