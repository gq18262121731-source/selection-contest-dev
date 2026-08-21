<script setup lang="ts">
import { computed } from "vue";
import { BatteryMedium, Bot, CircleGauge, Map, RadioTower, ShieldCheck } from "lucide-vue-next";
import type {
  LegacyRobotStatus,
  RobotDiagnostics,
  RobotNavigationState,
} from "../../types/robot";
import RobotControlOwnerBadge from "./RobotControlOwnerBadge.vue";

type SummaryTone = "normal" | "abnormal" | "unknown" | "mock" | "blocked";
type SummaryItem = { label: string; value: string; tone: SummaryTone };

const props = defineProps<{
  diagnostics: RobotDiagnostics | null;
  navigationState: RobotNavigationState | null;
  legacyStatus: LegacyRobotStatus | null;
  updatedAt: string | null;
}>();

function record(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function booleanItem(label: string, value: unknown, trueLabel = "正常", falseLabel = "异常"): SummaryItem {
  if (value === true) return { label, value: trueLabel, tone: "normal" };
  if (value === false) return { label, value: falseLabel, tone: "abnormal" };
  return { label, value: "未验证", tone: "unknown" };
}

const navigation = computed(() => props.navigationState ?? props.diagnostics?.navigation ?? null);
const gateway = computed(() => record(props.diagnostics?.gateway ?? props.legacyStatus?.gateway));
const gatewayData = computed(() => record(gateway.value.data));
const lidar = computed(() => props.diagnostics?.lidar ?? {});
const robotData = computed(() => record(gatewayData.value.robot));

const items = computed<SummaryItem[]>(() => {
  const state = navigation.value;
  const battery = robotData.value.battery ?? gatewayData.value.battery;
  const lidarStatus = lidar.value.status;
  const lidarItem: SummaryItem = lidarStatus === "mock"
    ? { label: "LiDAR", value: "模拟", tone: "mock" }
    : lidarStatus === "blocked"
      ? { label: "LiDAR", value: "阻塞", tone: "blocked" }
      : lidarStatus === "ready"
        ? { label: "LiDAR", value: "正常", tone: "normal" }
        : lidarStatus === "unavailable"
          ? { label: "LiDAR", value: "不可用", tone: "abnormal" }
          : { label: "LiDAR", value: "未验证", tone: "unknown" };

  return [
    booleanItem("机器人在线", state?.robot_online ?? gatewayData.value.robotOnline ?? gatewayData.value.robot_online),
    booleanItem("go2-gateway", gateway.value.ok ?? gatewayData.value.ok, "可访问", "不可用"),
    booleanItem("网络", state?.network_reachable ?? gatewayData.value.networkReachable ?? gatewayData.value.network_reachable),
    booleanItem("DDS", state?.dds_state_available ?? gatewayData.value.ddsStateAvailable ?? gatewayData.value.dds_state_available),
    lidarItem,
    booleanItem("定位", state?.localization_valid, "模拟有效", "异常"),
    booleanItem("地图", state?.map_loaded, "模拟已加载", "不可用"),
    {
      label: "电量",
      value: typeof battery === "number" ? `${Math.round(battery)}%` : "未验证",
      tone: typeof battery === "number" ? "normal" : "unknown",
    },
    booleanItem(
      "急停",
      state?.emergency_stop_clear ?? (typeof state?.emergency_stop_active === "boolean" ? !state.emergency_stop_active : undefined),
      "已解除",
      "阻塞",
    ),
    {
      label: "当前任务",
      value: props.diagnostics?.current_task?.task_id ?? state?.current_task?.task_id ?? "暂无任务",
      tone: props.diagnostics?.current_task || state?.current_task ? "mock" : "unknown",
    },
  ];
});

function formatTime(value: string | null) {
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "尚未更新";
}
</script>

<template>
  <article class="robot-status-card robot-summary">
    <header class="robot-status-card__head">
      <div>
        <p>STATUS OVERVIEW</p>
        <h2>总体状态摘要</h2>
      </div>
      <span class="robot-summary__updated">{{ formatTime(updatedAt) }}</span>
    </header>

    <div class="robot-summary__grid">
      <div v-for="(item, index) in items" :key="item.label" class="robot-summary__item">
        <span class="robot-summary__icon" :class="`robot-summary__icon--${item.tone}`">
          <Bot v-if="index < 2" :size="17" />
          <RadioTower v-else-if="index < 5" :size="17" />
          <Map v-else-if="index < 7" :size="17" />
          <BatteryMedium v-else-if="index === 7" :size="17" />
          <ShieldCheck v-else-if="index === 8" :size="17" />
          <CircleGauge v-else :size="17" />
        </span>
        <div>
          <small>{{ item.label }}</small>
          <strong :class="`robot-summary__value--${item.tone}`">{{ item.value }}</strong>
        </div>
      </div>
    </div>

    <footer class="robot-summary__owner">
      <span>当前控制权</span>
      <RobotControlOwnerBadge :owner="diagnostics?.control_owner ?? navigationState?.control_owner" />
    </footer>
  </article>
</template>

<style scoped>
.robot-status-card {
  border: 1px solid #dce6f0;
  border-radius: 18px;
  background: #fbfdff;
  box-shadow: 0 8px 24px rgba(35, 78, 112, 0.06);
}

.robot-summary { padding: 20px; }

.robot-status-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.robot-status-card__head p {
  margin: 0;
  color: #47779c;
  font-size: 0.68rem;
  font-weight: 800;
  letter-spacing: 0.08em;
}

.robot-status-card__head h2 {
  margin: 4px 0 0;
  color: #102a43;
  font-size: 1.05rem;
}

.robot-summary__updated { color: #6b8092; font-size: 0.72rem; }

.robot-summary__grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
  margin-top: 18px;
}

.robot-summary__item {
  min-width: 0;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 9px;
  padding: 11px;
  border: 1px solid #e0e8ef;
  border-radius: 11px;
  background: #f6f9fb;
}

.robot-summary__icon {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border-radius: 9px;
  background: #e8f1f8;
  color: #396d93;
}

.robot-summary__icon--normal { background: #dff3ea; color: #087653; }
.robot-summary__icon--abnormal { background: #fbe5e2; color: #a53630; }
.robot-summary__icon--blocked { background: #fff0d1; color: #8b5a0a; }
.robot-summary__icon--mock { background: #e5f1ff; color: #245d97; }

.robot-summary__item div { min-width: 0; display: grid; gap: 3px; }
.robot-summary__item small { color: #70869a; font-size: 0.66rem; }
.robot-summary__item strong {
  overflow: hidden;
  color: #294b65;
  font-size: 0.78rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.robot-summary__value--normal { color: #087653 !important; }
.robot-summary__value--abnormal { color: #a53630 !important; }
.robot-summary__value--blocked { color: #8b5a0a !important; }
.robot-summary__value--mock { color: #245d97 !important; }

.robot-summary__owner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid #e0e8ef;
  color: #61798e;
  font-size: 0.75rem;
  font-weight: 700;
}

@media (max-width: 1120px) {
  .robot-summary__grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}

@media (max-width: 680px) {
  .robot-summary__grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .robot-status-card__head { flex-direction: column; }
}
</style>
