<script setup lang="ts">
import { computed } from "vue";
import type { AlarmRecord, HealthSample } from "../api/client";

type StageTone = "stable" | "warning" | "critical";

const props = defineProps<{
  sample: HealthSample | null;
  trend: HealthSample[];
  focusAlarm: AlarmRecord | null;
}>();

const thresholdItems = [
  { label: "血氧", value: "低于 93%" },
  { label: "体温", value: "高于或等于 37.8°C" },
  { label: "心率", value: "高于 110 bpm 或低于 45 bpm" },
  { label: "SOS", value: "样本中包含 SOS 标记" },
] as const;

function isAbnormal(sample: HealthSample | null) {
  if (!sample) return false;
  return Boolean(
    sample.sos_flag
      || sample.blood_oxygen < 93
      || sample.temperature >= 37.8
      || sample.heart_rate >= 110
      || sample.heart_rate <= 45,
  );
}

const sustainedAbnormal = computed(() => {
  if (props.trend.length < 3) return false;
  return props.trend.slice(-3).every((item) => isAbnormal(item));
});

const activeStage = computed(() => {
  if (props.focusAlarm) return 4;
  if (sustainedAbnormal.value) return 3;
  if (isAbnormal(props.sample)) return 2;
  return 1;
});

const stages = computed(() => [
  { id: 1, label: "正常", description: "指标处于常规观察区间。", active: activeStage.value >= 1 },
  { id: 2, label: "异常", description: "出现单次或短时异常波动。", active: activeStage.value >= 2 },
  { id: 3, label: "持续异常", description: "多个样本连续异常，需要升级关注。", active: activeStage.value >= 3 },
  { id: 4, label: "报警", description: "已进入告警处理链路。", active: activeStage.value >= 4 },
]);

const currentStage = computed(() => stages.value[activeStage.value - 1]);

const stageTone = computed<StageTone>(() => {
  if (activeStage.value === 4) return "critical";
  if (activeStage.value === 2 || activeStage.value === 3) return "warning";
  return "stable";
});

const stageSummary = computed(() => {
  if (!props.sample) {
    return "当前还没有实时样本，暂时无法判断异常演进位置。同步到新样本后会自动更新阶段。";
  }
  if (props.focusAlarm) {
    return `当前已触发告警，消息为“${props.focusAlarm.message}”。建议先处理告警链路，再回看结构化报告和关键发现。`;
  }
  if (sustainedAbnormal.value) {
    return "最近多个样本连续异常，已经从单次波动升级为持续异常，建议立即进入重点观察状态。";
  }
  if (isAbnormal(props.sample)) {
    return "当前出现单次异常样本，建议继续看后续样本是否恢复，避免遗漏持续异常。";
  }
  return "当前样本整体平稳，仍处于常规观察阶段，可继续结合报告建议做日常关注。";
});

const evidence = computed(() => {
  const rows: string[] = [];
  if (!props.sample) return ["当前还没有实时样本，暂无法判断异常演进链路。"];
  if (props.sample.blood_oxygen < 93) rows.push(`当前血氧 ${props.sample.blood_oxygen}% ，已低于常规观察阈值。`);
  if (props.sample.temperature >= 37.8) rows.push(`当前体温 ${props.sample.temperature.toFixed(1)}°C ，已进入异常观察区间。`);
  if (props.sample.heart_rate >= 110 || props.sample.heart_rate <= 45) rows.push(`当前心率 ${props.sample.heart_rate} bpm ，需要重点关注。`);
  if (props.sample.sos_flag) rows.push("当前样本包含 SOS 标记。");
  if (sustainedAbnormal.value) rows.push("最近连续 3 个样本均表现为异常，已满足持续异常观察条件。");
  if (props.focusAlarm) rows.push(`当前已生成告警：${props.focusAlarm.message}`);
  if (!rows.length) rows.push("当前样本整体平稳，仍处于常规观察阶段。");
  return rows;
});

const alarmDetails = computed(() => {
  if (!props.focusAlarm) return [];
  return [
    { label: "告警类型", value: props.focusAlarm.alarm_type },
    { label: "告警层级", value: props.focusAlarm.alarm_layer },
    { label: "告警等级", value: String(props.focusAlarm.alarm_level) },
    { label: "触发时间", value: new Date(props.focusAlarm.created_at).toLocaleString("zh-CN", { hour12: false }) },
  ];
});

const actionChecklist = computed(() => {
  if (activeStage.value === 4) {
    return [
      "先按告警消息完成电话确认或现场核查，再补充查看报告中的建议动作。",
      "确认告警结束前，不要只根据单次恢复样本直接判定风险解除。",
      "对外演示时优先展示告警消息、阶段卡片和当前判断依据。",
    ];
  }
  if (activeStage.value === 3) {
    return [
      "把持续异常视为需要升级关注的状态，优先看建议动作和关键发现。",
      "继续观察后续样本，确认是否进入正式告警链路。",
      "如用于演示，可说明系统已经识别到多次连续异常。",
    ];
  }
  if (activeStage.value === 2) {
    return [
      "当前先视为单次异常波动，继续关注最近几次样本是否恢复。",
      "结合健康报告中的摘要和建议动作，判断是否需要主动联系。",
      "异常未持续前，页面以提示关注为主，不提前展示告警结论。",
    ];
  }
  return [
    "当前处于常规观察阶段，可继续按报告建议进行日常关注。",
    "如需演示主链，可说明页面会在异常出现后自动升级到下一阶段。",
  ];
});
</script>

<template>
  <section class="panel alarm-escalation-panel">
    <div class="alarm-head">
      <div>
        <h2>异常到报警流</h2>
        <p class="panel-subtitle">用现有结构化指标解释当前位于哪一阶段、为什么会到这里，以及下一步建议怎么处理。</p>
      </div>
      <div class="alarm-head-meta">
        <span class="status-tag" :class="`tone-${stageTone}`">当前阶段 {{ currentStage.label }}</span>
        <span class="meta-pill">{{ focusAlarm ? "已触发告警" : "未触发告警" }}</span>
      </div>
    </div>

    <div class="alarm-overview">
      <article class="alarm-stage-card" :class="`tone-${stageTone}`">
        <p class="section-eyebrow">Alarm Stage</p>
        <h3>{{ currentStage.label }}</h3>
        <p>{{ stageSummary }}</p>
        <div class="alarm-stage-meta">
          <span class="meta-pill">实时样本 {{ sample ? "已同步" : "未同步" }}</span>
          <span class="meta-pill">趋势样本 {{ trend.length }}</span>
        </div>
      </article>

      <article class="alarm-detail-card">
        <h3>{{ focusAlarm ? "当前告警信息" : "当前处理建议" }}</h3>
        <div v-if="alarmDetails.length" class="alarm-detail-grid">
          <article v-for="item in alarmDetails" :key="item.label" class="alarm-detail-item">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </article>
        </div>
        <ul class="list-copy compact">
          <li v-for="item in actionChecklist" :key="item">{{ item }}</li>
        </ul>
      </article>
    </div>

    <div class="flow-grid flow-grid--timeline">
      <article v-for="stage in stages" :key="stage.id" class="flow-card" :class="{ active: stage.active, current: stage.id === activeStage }">
        <span class="flow-index">{{ stage.id }}</span>
        <div class="flow-copy">
          <strong>{{ stage.label }}</strong>
          <p>{{ stage.description }}</p>
        </div>
      </article>
    </div>

    <div class="alarm-support-grid">
      <article class="flow-evidence">
        <h3>当前判断依据</h3>
        <ul class="list-copy">
          <li v-for="item in evidence" :key="item">{{ item }}</li>
        </ul>
      </article>

      <article class="flow-evidence">
        <h3>观察阈值</h3>
        <ul class="list-copy compact">
          <li v-for="item in thresholdItems" :key="item.label">{{ item.label }}：{{ item.value }}</li>
        </ul>
      </article>
    </div>
  </section>
</template>

<style scoped>
.alarm-escalation-panel,
.alarm-overview,
.flow-grid,
.alarm-support-grid,
.alarm-detail-grid {
  display: grid;
  gap: 14px;
}

.alarm-head {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: flex-start;
}

.alarm-head-meta,
.alarm-stage-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.alarm-overview,
.alarm-support-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.alarm-stage-card,
.alarm-detail-card,
.flow-card,
.flow-evidence,
.alarm-detail-item {
  border: 1px solid rgba(56, 189, 248, 0.10);
  border-radius: 22px;
  background: rgba(13, 22, 38, 0.90);
  padding: 18px;
}

.alarm-stage-card,
.alarm-detail-card,
.flow-evidence {
  display: grid;
  gap: 12px;
}

.alarm-stage-card h3,
.alarm-detail-card h3,
.flow-evidence h3 {
  margin: 0;
}

.alarm-stage-card p {
  margin: 0;
  color: var(--text-sub);
  line-height: 1.78;
}

.alarm-stage-card.tone-critical {
  border-color: rgba(248, 113, 113, 0.24);
  background: linear-gradient(180deg, rgba(33, 18, 30, 0.96), rgba(52, 20, 28, 0.92));
}

.alarm-stage-card.tone-warning {
  border-color: rgba(251, 146, 60, 0.22);
  background: linear-gradient(180deg, rgba(28, 20, 30, 0.96), rgba(52, 30, 16, 0.92));
}

.alarm-stage-card.tone-stable {
  border-color: rgba(52, 211, 153, 0.22);
  background: linear-gradient(180deg, rgba(14, 24, 34, 0.96), rgba(16, 42, 38, 0.92));
}

.alarm-detail-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.alarm-detail-item span {
  color: var(--text-sub);
  font-size: 0.8rem;
  font-weight: 700;
}

.alarm-detail-item strong {
  display: block;
  margin-top: 8px;
  color: var(--text-main);
  line-height: 1.5;
}

.flow-grid--timeline {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.flow-card {
  display: grid;
  gap: 12px;
  opacity: 0.58;
}

.flow-card.active {
  opacity: 1;
}

.flow-card.current {
  border-color: rgba(34, 211, 238, 0.24);
  box-shadow: 0 16px 32px rgba(0, 0, 0, 0.26);
}

.flow-index {
  display: inline-flex;
  width: 34px;
  height: 34px;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: rgba(34, 211, 238, 0.10);
  color: #67e8f9;
  font-weight: 800;
}

.flow-copy strong {
  display: block;
}

.flow-copy p {
  margin: 8px 0 0;
  color: var(--text-sub);
  line-height: 1.68;
}

@media (max-width: 1100px) {
  .alarm-overview,
  .alarm-support-grid,
  .flow-grid--timeline,
  .alarm-detail-grid {
    grid-template-columns: 1fr;
  }

  .alarm-head {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
