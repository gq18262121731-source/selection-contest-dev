<script setup lang="ts">
import { computed } from "vue";
import type { RobotDiagnostics, RobotNavigationState } from "../../types/robot";
import RobotControlOwnerBadge from "./RobotControlOwnerBadge.vue";

type DiagnosticTone = "normal" | "abnormal" | "unknown" | "mock" | "blocked";
type DiagnosticItem = {
  key: string;
  label: string;
  value: unknown;
  code: string;
  message: string;
  special?: "owner" | "mapping";
};

const props = defineProps<{
  diagnostics: RobotDiagnostics | null;
  navigationState: RobotNavigationState | null;
}>();

function record(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

const navigation = computed(() => props.navigationState ?? props.diagnostics?.navigation ?? null);
const gateway = computed(() => record(props.diagnostics?.gateway));
const gatewayData = computed(() => record(gateway.value.data));
const lidar = computed(() => props.diagnostics?.lidar ?? {});

const items = computed<DiagnosticItem[]>(() => {
  const state = navigation.value;
  const lidarCode = lidar.value.error_code ?? lidar.value.reason ?? "LIDAR_STATUS_NOT_VERIFIED";
  return [
    { key: "network_reachable", label: "网络可达", value: state?.network_reachable ?? gatewayData.value.networkReachable ?? gatewayData.value.network_reachable, code: "NETWORK_UNVERIFIED", message: "主系统网关网络诊断" },
    { key: "dds_initialized", label: "DDS 初始化", value: state?.dds_initialized ?? gatewayData.value.ddsInitialized ?? gatewayData.value.dds_initialized, code: "DDS_INIT_UNVERIFIED", message: "只读 DDS 通信初始化状态" },
    { key: "dds_state_available", label: "DDS 状态样本", value: state?.dds_state_available ?? gatewayData.value.ddsStateAvailable ?? gatewayData.value.dds_state_available, code: "DDS_STATE_UNAVAILABLE", message: "未收到样本不等于硬件不存在" },
    { key: "robot_online", label: "机器人在线", value: state?.robot_online ?? gatewayData.value.robotOnline ?? gatewayData.value.robot_online, code: "ROBOT_ONLINE_UNVERIFIED", message: "真实机器人当前可保持关机" },
    { key: "motion_ready", label: "运动准备", value: state?.motion_ready ?? gatewayData.value.motionReady ?? gatewayData.value.motion_ready, code: "MOTION_NOT_VERIFIED", message: "本页面不启用真实运动" },
    { key: "lidar.device_detected", label: "LiDAR 设备", value: lidar.value.device_detected, code: String(lidarCode), message: "未验证不会解释为设备故障" },
    { key: "lidar.topic_discovered", label: "LiDAR 话题", value: lidar.value.topic_discovered, code: String(lidarCode), message: "候选数据话题发现状态" },
    { key: "lidar.sample_received", label: "LiDAR 样本", value: lidar.value.sample_received, code: String(lidarCode), message: "真实样本接收状态" },
    { key: "lidar.data_fresh", label: "LiDAR 新鲜度", value: lidar.value.data_fresh, code: String(lidarCode), message: "样本是否满足新鲜度要求" },
    { key: "lidar.mapping_prerequisites_ready", label: "建图数据前置条件", value: lidar.value.mapping_prerequisites_ready ?? lidar.value.mapping_ready, code: String(lidarCode), message: "具备后续验证前置条件，不代表可导航", special: "mapping" },
    { key: "localization_valid", label: "定位有效", value: state?.localization_valid, code: "LOCALIZATION_INVALID", message: "当前为 Mock 定位条件" },
    { key: "map_loaded", label: "地图加载", value: state?.map_loaded, code: "MAP_NOT_LOADED", message: "当前为 Mock 地图状态" },
    { key: "emergency_stop_clear", label: "急停解除", value: state?.emergency_stop_clear ?? (typeof state?.emergency_stop_active === "boolean" ? !state.emergency_stop_active : undefined), code: "EMERGENCY_STOP_ACTIVE", message: "急停优先于所有控制权" },
    { key: "control_owner", label: "控制权", value: state?.control_owner ?? props.diagnostics?.control_owner ?? "NONE", code: "CONTROL_OWNER", message: "统一控制权状态机", special: "owner" },
  ];
});

function tone(item: DiagnosticItem): DiagnosticTone {
  if (item.special === "owner") return item.value === "EMERGENCY_STOP" ? "blocked" : "mock";
  if (item.special === "mapping" && item.value === true) return "mock";
  if (item.value === true) return "normal";
  if (item.value === false) return "abnormal";
  return "unknown";
}

function label(item: DiagnosticItem) {
  if (item.special === "mapping" && item.value === true) return "前置条件满足";
  if (item.value === true) return "正常";
  if (item.value === false) return "未通过";
  return "未验证";
}
</script>

<template>
  <article class="robot-status-card robot-diagnostics">
    <header class="robot-card-head">
      <div><p>READ-ONLY DIAGNOSTICS</p><h2>诊断网格</h2></div>
      <span>缺失字段统一显示“未验证”</span>
    </header>
    <div class="robot-diagnostics__grid">
      <div v-for="item in items" :key="item.key" class="robot-diagnostic" :class="`robot-diagnostic--${tone(item)}`">
        <div class="robot-diagnostic__top">
          <strong>{{ item.label }}</strong>
          <RobotControlOwnerBadge v-if="item.special === 'owner'" :owner="item.value as RobotNavigationState['control_owner']" />
          <span v-else>{{ label(item) }}</span>
        </div>
        <p>{{ item.message }}</p>
        <code>{{ item.value === true ? "OK" : item.code }}</code>
      </div>
    </div>
  </article>
</template>

<style scoped>
.robot-status-card { border: 1px solid #dce6f0; border-radius: 18px; background: #fbfdff; box-shadow: 0 8px 24px rgba(35, 78, 112, 0.06); }
.robot-diagnostics { padding: 20px; }
.robot-card-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.robot-card-head p { margin: 0; color: #47779c; font-size: 0.68rem; font-weight: 800; letter-spacing: 0.08em; }
.robot-card-head h2 { margin: 4px 0 0; color: #102a43; font-size: 1.05rem; }
.robot-card-head > span { color: #70869a; font-size: 0.7rem; }
.robot-diagnostics__grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-top: 17px; }
.robot-diagnostic { min-width: 0; padding: 12px; border: 1px solid #dfe7ee; border-left: 3px solid #9fb3c3; border-radius: 10px; background: #f7f9fb; }
.robot-diagnostic--normal { border-left-color: #2c9b71; }
.robot-diagnostic--abnormal { border-left-color: #d05a52; }
.robot-diagnostic--blocked { border-left-color: #d19027; }
.robot-diagnostic--mock { border-left-color: #4283bd; }
.robot-diagnostic__top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.robot-diagnostic__top strong { color: #274a65; font-size: 0.77rem; }
.robot-diagnostic__top > span { color: #5e768a; font-size: 0.67rem; font-weight: 750; }
.robot-diagnostic--normal .robot-diagnostic__top > span { color: #087653; }
.robot-diagnostic--abnormal .robot-diagnostic__top > span { color: #a53630; }
.robot-diagnostic p { min-height: 2.7em; margin: 8px 0; color: #6b8092; font-size: 0.69rem; line-height: 1.4; }
.robot-diagnostic code { display: block; overflow: hidden; color: #667b8e; font-family: var(--font-mono); font-size: 0.62rem; text-overflow: ellipsis; white-space: nowrap; }
@media (max-width: 1100px) { .robot-diagnostics__grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 620px) { .robot-diagnostics__grid { grid-template-columns: 1fr; } .robot-card-head { flex-direction: column; } }
</style>
