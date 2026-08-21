<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  deviceCount: number;
  anomalyScore: number;
  selectedMac: string;
}>();

const architectureStages = [
  {
    badge: "01",
    title: "T10 智能手环",
    description: "采集心率、体温、血氧、血压、电量与 SOS 广播，覆盖社区与居家场景。",
  },
  {
    badge: "02",
    title: "BLE / MQTT 网关",
    description: "完成蓝牙包接收、分包合并与上传，为多设备并行接入打底。",
  },
  {
    badge: "03",
    title: "流式处理层",
    description: "数据进入实时处理链路，持续产出告警、风险分层和趋势样本。",
  },
  {
    badge: "04",
    title: "AI 分析引擎",
    description: "后端调度本地或受控模型，结合知识库生成设备与社区分析结论。",
  },
  {
    badge: "05",
    title: "Web / App 联动",
    description: "Dashboard 与移动端承接实时监测、社区汇总、趋势分析与处置闭环。",
  },
];

const readinessLabel = computed(() => {
  if (props.anomalyScore >= 10) return "高波动阶段";
  if (props.anomalyScore >= 5) return "重点巡检阶段";
  return "常规监测阶段";
});

const capabilityCards = computed(() => [
  { label: "已接入设备", value: String(props.deviceCount) },
  { label: "当前主设备", value: props.selectedMac || "未选择" },
  { label: "异常评分", value: props.anomalyScore.toFixed(2) },
]);
</script>

<template>
  <section class="panel architecture-panel">
    <div class="panel-head">
      <div>
        <h2>系统架构路线</h2>
        <p class="panel-subtitle">把设备接入、数据流、AI 分析和前端展示串成一条清晰链路，方便说明系统完整性。</p>
      </div>
      <span>{{ readinessLabel }}</span>
    </div>
    <div class="capability-strip">
      <article v-for="item in capabilityCards" :key="item.label" class="capability-card">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
      </article>
    </div>
    <div class="architecture-flow">
      <article v-for="item in architectureStages" :key="item.title" class="architecture-node">
        <span class="architecture-badge">{{ item.badge }}</span>
        <strong>{{ item.title }}</strong>
        <p>{{ item.description }}</p>
      </article>
    </div>
    <div class="architecture-foot">
      <article class="stack-card">
        <span>在线智能体</span>
        <strong>受控后端模型服务</strong>
        <small>适合网络环境良好时的高质量问答、检索增强与社区级汇总分析。</small>
      </article>
      <article class="stack-card">
        <span>离线智能体</span>
        <strong>本地模型运行时</strong>
        <small>离线环境下继续完成单设备趋势分析，不把外部网络作为必需前提。</small>
      </article>
      <article class="stack-card">
        <span>数据底座</span>
        <strong>向量检索 + 时序数据 + WebSocket</strong>
        <small>同时支持知识检索、趋势查询、实时订阅与社区监测态势页面。</small>
      </article>
    </div>
  </section>
</template>
