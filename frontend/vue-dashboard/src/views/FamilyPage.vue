<script setup lang="ts">
import { computed, ref, toRef, watch } from "vue";
import type {
  AgentDeviceHealthReport,
  CareAccessProfile,
  CareHealthEvaluationSummary,
  CareHealthReportSummary,
  HealthSample,
  SessionUser,
} from "../api/client";
import { ApiError, api } from "../api/client";
import AlarmEscalationPanel from "../components/AlarmEscalationPanel.vue";
import AssistantPanel from "../components/AssistantPanel.vue";
import HealthEvaluationPanel from "../components/HealthEvaluationPanel.vue";
import PageHeader from "../components/layout/PageHeader.vue";
import { useCareDirectoryDashboard } from "../composables/useCareDirectoryDashboard";
import { useDeviceTrend } from "../composables/useDeviceTrend";
import { evaluateRisk, riskLabel, type RiskLevel } from "../domain/careModel";

type DemoTone = "neutral" | "stable" | "warning" | "critical";

interface ElderRow {
  id: string;
  name: string;
  apartment: string;
  deviceMac: string;
  familyNames: string;
  risk: RiskLevel;
  sample: HealthSample | null;
}

interface SnapshotMetric {
  id: string;
  shortLabel: string;
  label: string;
  value: string;
  unit: string;
  note: string;
  tone: DemoTone;
}

const props = defineProps<{
  sessionUser: SessionUser;
}>();

const sessionUser = toRef(props, "sessionUser");
const {
  alarms,
  allFamilies: allFamiliesRaw,
  dashboardLoadError,
  dashboardLoading,
  devices,
  elders,
  lastSyncAt,
  latest,
} = useCareDirectoryDashboard(sessionUser);

const selectedFamilyId = ref("");
const selectedDeviceMac = ref("");
const accessProfile = ref<CareAccessProfile | null>(null);
const generatedHealthReport = ref<AgentDeviceHealthReport | null>(null);
const reportLoading = ref(false);
const reportError = ref("");

const { focusLatest, focusTrend } = useDeviceTrend({
  selectedDeviceMac,
  latest,
  pollIntervalMs: 15000,
});

const families = computed(() =>
  sessionUser.value.role === "family"
    ? allFamiliesRaw.value.filter((family) => family.id === sessionUser.value.family_id)
    : allFamiliesRaw.value,
);
const selectedFamily = computed(() =>
  families.value.find((family) => family.id === selectedFamilyId.value) ?? families.value[0] ?? null,
);
const elderRows = computed<ElderRow[]>(() =>
  elders.value.map((elder) => {
    const rawDeviceMac = elder.device_macs?.[0] ?? elder.device_mac ?? "";
    const deviceRecord = rawDeviceMac
      ? devices.value.find((device) => device.mac_address === rawDeviceMac) ?? null
      : null;
    const exposeDevice =
      deviceRecord != null
        ? deviceRecord.ingest_mode === "mock" || deviceRecord.bind_status === "bound"
        : false;
    const deviceMac = exposeDevice ? rawDeviceMac : "";
    const sample = deviceMac ? latest.value[deviceMac] ?? null : null;
    const risk = evaluateRisk(
      sample,
      deviceMac ? (deviceRecord?.status ?? "unknown") : "unbound",
    );
    const familyNames = elder.family_ids
      .map((id) => allFamiliesRaw.value.find((family) => family.id === id)?.name)
      .filter(Boolean)
      .join(" / ");
    return { id: elder.id, name: elder.name, apartment: elder.apartment, deviceMac, familyNames, risk, sample };
  }),
);
const visibleRows = computed(() =>
  sessionUser.value.role === "family" && selectedFamily.value
    ? elderRows.value.filter((row) => new Set(selectedFamily.value.elder_ids ?? []).has(row.id))
    : elderRows.value,
);
const focusRow = computed(
  () =>
    visibleRows.value.find((row) => row.deviceMac === selectedDeviceMac.value)
    ?? elderRows.value.find((row) => row.deviceMac === selectedDeviceMac.value)
    ?? null,
);
const focusAlarm = computed(
  () => alarms.value.find((alarm) => !alarm.acknowledged && alarm.device_mac === selectedDeviceMac.value) ?? null,
);
const currentHealthEvaluation = computed<CareHealthEvaluationSummary | null>(() => {
  if (!selectedDeviceMac.value || !accessProfile.value) return null;
  return accessProfile.value.health_evaluations.find((item) => item.device_mac === selectedDeviceMac.value) ?? null;
});
const currentHealthReportSummary = computed<CareHealthReportSummary | null>(() => {
  if (!selectedDeviceMac.value || !accessProfile.value) return null;
  return accessProfile.value.health_reports.find((item) => item.device_mac === selectedDeviceMac.value) ?? null;
});
const hasBoundDevice = computed(() => {
  if (sessionUser.value.role === "family") {
    return visibleRows.value.some((row) => Boolean(row.deviceMac));
  }
  return Boolean(focusRow.value?.deviceMac);
});
const focusRiskLabel = computed(() => (focusRow.value ? riskLabel(focusRow.value.risk) : "未选择对象"));
const focusTone = computed<DemoTone>(() => {
  if (!hasBoundDevice.value) return "neutral";
  if (focusAlarm.value) return "critical";
  if (focusRow.value?.risk === "high" || focusRow.value?.risk === "medium") return "warning";
  if (focusRow.value?.risk === "low") return "stable";
  return "neutral";
});
const focusUpdatedLabel = computed(() =>
  displayFocusLatest.value ? new Date(displayFocusLatest.value.timestamp).toLocaleString("zh-CN", { hour12: false }) : "尚未同步",
);
const focusSummaryTitle = computed(() => {
  if (!hasBoundDevice.value) return "当前家属还没有绑定设备";
  if (focusAlarm.value) return "已出现需要优先处理的告警";
  if (focusRow.value?.risk === "high") return "健康风险偏高，需要尽快跟进";
  if (focusRow.value?.risk === "medium") return "近期状态有波动，建议继续观察";
  if (focusRow.value?.risk === "low") return "当前状态总体平稳";
  return "等待更多同步数据";
});
const focusSummaryCopy = computed(() => {
  if (!hasBoundDevice.value) {
    return "当前还没有可用设备，请先确认家属关系和设备绑定状态。";
  }
  if (!displayFocusLatest.value) {
    return "已识别到绑定关系，但当前设备还没有可用的实时数据。请确认设备在线状态和最近同步情况。";
  }

  const metrics = `心率 ${displayFocusLatest.value.heart_rate} bpm，血氧 ${displayFocusLatest.value.blood_oxygen}%，体温 ${displayFocusLatest.value.temperature.toFixed(1)}°C`;

  if (focusAlarm.value) {
    return `${focusAlarm.value.message}。当前关键指标为 ${metrics}，建议先查看告警升级建议，再决定是否联系社区人员处理。`;
  }
  if (focusRow.value?.risk === "high") {
    return `当前对象综合风险为高，最近同步指标为 ${metrics}。建议尽快补充观察、生成正式报告并结合家属照护安排做进一步判断。`;
  }
  if (focusRow.value?.risk === "medium") {
    return `当前对象存在中度波动，最近同步指标为 ${metrics}。建议继续观察趋势变化，并结合健康评估结果决定是否需要人工干预。`;
  }
  return `最近同步指标为 ${metrics}。整体趋势相对平稳，可继续保持日常观察并关注后续波动。`;
});
const familyTrendPreview = computed(() => focusTrend.value.slice(-4).reverse());
const displayFocusLatest = computed(() => focusLatest.value ?? focusRow.value?.sample ?? null);
const familyTrendHeadline = computed(() => {
  if (!familyTrendPreview.value.length) {
    return "选中的设备还没有可展示的趋势片段，后续同步后会在这里展示最近的变化轨迹。";
  }

  const latestPoint = familyTrendPreview.value[0];
  const oldestPoint = familyTrendPreview.value[familyTrendPreview.value.length - 1];
  const latestScore = latestPoint.health_score ?? null;
  const oldestScore = oldestPoint.health_score ?? null;

  if (latestScore !== null && oldestScore !== null) {
    if (latestScore - oldestScore >= 5) return "最近几个采样点的健康分有回升趋势，短期状态正在改善。";
    if (oldestScore - latestScore >= 5) return "最近几个采样点的健康分有下降趋势，建议关注后续变化。";
  }

  return "最近同步的几个采样点整体波动有限，可以继续结合实时指标与评估结果做判断。";
});
const familySnapshotCards = computed<SnapshotMetric[]>(() => {
  const sample = displayFocusLatest.value;
  return [
    {
      id: "heart-rate",
      shortLabel: "HR",
      label: "心率",
      value: sample ? String(sample.heart_rate) : "--",
      unit: "bpm",
      note: sample
        ? sample.heart_rate >= 110 || sample.heart_rate <= 45
          ? "心率超出稳态区间，建议重点关注。"
          : "心率处于可接受范围。"
        : "等待实时数据同步。",
      tone: sample && (sample.heart_rate >= 110 || sample.heart_rate <= 45) ? "warning" : "stable",
    },
    {
      id: "blood-oxygen",
      shortLabel: "SpO2",
      label: "血氧",
      value: sample ? String(sample.blood_oxygen) : "--",
      unit: "%",
      note: sample ? (sample.blood_oxygen < 93 ? "血氧偏低，建议尽快查看告警与趋势。" : "血氧状态相对稳定。") : "等待实时数据同步。",
      tone: sample && sample.blood_oxygen < 93 ? "critical" : "stable",
    },
    {
      id: "temperature",
      shortLabel: "TEMP",
      label: "体温",
      value: sample ? sample.temperature.toFixed(1) : "--",
      unit: "°C",
      note: sample ? (sample.temperature >= 37.8 ? "体温偏高，需要继续观察。" : "体温状态平稳。") : "等待实时数据同步。",
      tone: sample && sample.temperature >= 37.8 ? "warning" : "stable",
    },
    {
      id: "battery",
      shortLabel: "BAT",
      label: "设备电量",
      value: sample?.battery !== null && sample?.battery !== undefined ? String(sample.battery) : "--",
      unit: "%",
      note:
        sample?.battery !== null && sample?.battery !== undefined
          ? sample.battery <= 20
            ? "电量偏低，建议尽快充电。"
            : "设备电量正常。"
          : "尚未获取设备电量。",
      tone:
        sample?.battery !== null && sample?.battery !== undefined
          ? sample.battery <= 20
            ? "warning"
            : "stable"
          : "neutral",
    },
    {
      id: "health-score",
      shortLabel: "SCORE",
      label: "健康分",
      value:
        sample?.health_score !== null && sample?.health_score !== undefined
          ? String(Math.round(sample.health_score))
          : "--",
      unit: "分",
      note:
        sample?.health_score !== null && sample?.health_score !== undefined
          ? sample.health_score < 60
            ? "健康分偏低，建议生成正式报告。"
            : "健康分处于可观察区间。"
          : "等待健康分同步。",
      tone:
        sample?.health_score !== null && sample?.health_score !== undefined
          ? sample.health_score < 60
            ? "warning"
            : "stable"
          : "neutral",
    },
    {
      id: "alarm-stage",
      shortLabel: "ALERT",
      label: "告警状态",
      value: focusAlarm.value ? "处理中" : "无活动告警",
      unit: "",
      note: focusAlarm.value?.message ?? "当前没有活动告警，仍建议持续关注实时状态变化。",
      tone: focusAlarm.value ? "critical" : "stable",
    },
  ];
});
const syncLabel = computed(() =>
  lastSyncAt.value ? lastSyncAt.value.toLocaleTimeString("zh-CN", { hour12: false }) : "尚未同步",
);
const pageMeta = computed(() => [
  `家属 ${selectedFamily.value?.name || "未选择"}`,
  `对象 ${focusRow.value?.name || "未选择"}`,
  `设备 ${selectedDeviceMac.value || "未绑定"}`,
  `同步 ${syncLabel.value}`,
]);

function sessionToken() {
  return localStorage.getItem("ai_health_demo_session_token") ?? "";
}

function formatUiError(error: unknown, fallback: string) {
  if (error instanceof ApiError && error.detail) return error.detail;
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

async function refreshAccessProfile() {
  if (sessionUser.value.role !== "family" && sessionUser.value.role !== "elder") {
    accessProfile.value = null;
    return;
  }

  accessProfile.value = await api.getCareAccessProfile(sessionToken()).catch(() => null);
}

async function generateHealthReport() {
  if (!selectedDeviceMac.value) {
    reportError.value = "请先选择一个已绑定设备，再生成正式健康报告。";
    return;
  }

  reportLoading.value = true;
  reportError.value = "";
  generatedHealthReport.value = null;

  try {
    const endAt = new Date();
    const startAt = new Date(endAt.getTime() - 24 * 60 * 60 * 1000);
    generatedHealthReport.value = await api.generateDeviceHealthReport({
      device_mac: selectedDeviceMac.value,
      start_at: startAt.toISOString(),
      end_at: endAt.toISOString(),
      role: "family",
      mode: "qwen",
    });
  } catch (error) {
    reportError.value = formatUiError(error, "正式健康报告生成失败，请稍后重试。");
  } finally {
    reportLoading.value = false;
  }
}

watch(
  families,
  (list) => {
    if (!list.length) {
      selectedFamilyId.value = "";
      return;
    }
    if (!list.some((item) => item.id === selectedFamilyId.value)) {
      selectedFamilyId.value = list[0].id;
    }
  },
  { immediate: true },
);

watch(
  visibleRows,
  (list) => {
    if (!list.length) {
      selectedDeviceMac.value = "";
      return;
    }
    if (!list.some((item) => item.deviceMac === selectedDeviceMac.value)) {
      selectedDeviceMac.value = list.find((item) => item.deviceMac)?.deviceMac ?? "";
    }
  },
  { immediate: true },
);

watch(selectedDeviceMac, () => {
  generatedHealthReport.value = null;
  reportError.value = "";
});

watch(
  lastSyncAt,
  () => {
    void refreshAccessProfile();
  },
  { immediate: true },
);

function riskClass(level: RiskLevel) {
  return `risk-${level}`;
}

function updateFamilyId(event: Event) {
  selectedFamilyId.value = (event.target as HTMLSelectElement).value;
}
</script>

<template>
  <section class="page-stack">
    <PageHeader
      eyebrow="Family View"
      title="家属视图"
      description="页面级头部承载家属对象、当前设备和同步信息；具体照护摘要、趋势、报告与助手能力都放在页面内部。"
      :meta="pageMeta"
    />

    <p v-if="dashboardLoadError" class="feedback-banner feedback-error">{{ dashboardLoadError }}</p>

    <div v-else-if="dashboardLoading && !visibleRows.length" class="state-block state-loading">
      <strong>正在加载家属视图</strong>
      <p>页面会在数据到位后展示绑定对象、实时摘要、健康评估和正式报告入口。</p>
    </div>

    <section v-else class="panel-grid family-grid">
      <article class="panel family-header family-selector-panel">
        <div class="family-toolbar">
          <div>
            <p class="section-eyebrow">Family View</p>
            <h2>当前照护对象</h2>
            <p class="subtle-copy">这里集中展示当前家属可访问的老人对象，并支持切换当前关注的设备与照护摘要。</p>
          </div>
          <label class="form-field family-select-field">
            <span>当前家属</span>
            <select :value="selectedFamilyId" class="inline-select" @change="updateFamilyId">
              <option v-for="family in families" :key="family.id" :value="family.id">
                {{ family.name }} / {{ family.relationship }}
              </option>
            </select>
          </label>
        </div>
        <div class="family-cards">
          <button
            v-for="row in visibleRows"
            :key="row.id"
            type="button"
            class="family-elder-card family-elder-card--demo"
            :class="[riskClass(row.risk), { active: row.deviceMac === selectedDeviceMac }]"
            @click="selectedDeviceMac = row.deviceMac"
          >
            <div class="family-card-head">
              <div>
                <strong>{{ row.name }}</strong>
                <small>{{ row.apartment }}</small>
              </div>
              <span class="risk-pill" :class="riskClass(row.risk)">{{ riskLabel(row.risk) }}</span>
            </div>
            <p>{{ row.familyNames || "当前尚未配置家属关系说明" }}</p>
            <div class="family-kpis">
              <span>HR {{ row.sample?.heart_rate ?? "-" }}</span>
              <span>SpO2 {{ row.sample?.blood_oxygen ?? "-" }}</span>
              <span>健康分 {{ row.sample?.health_score ?? "-" }}</span>
            </div>
          </button>
        </div>
      </article>

      <article class="panel family-detail family-main-panel">
        <header class="panel-head family-main-head">
          <div>
            <p class="section-eyebrow">Care Summary</p>
            <h2>{{ focusRow?.name ?? "请选择一个照护对象" }}</h2>
            <p class="subtle-copy">当前对象的实时摘要、趋势预览和页面级状态都在这里集中展示。</p>
          </div>
          <span class="meta-pill">{{ hasBoundDevice ? focusRiskLabel : "未绑定设备" }}</span>
        </header>

        <div v-if="hasBoundDevice" class="family-overview-stack">
          <section class="family-summary-banner" :class="`tone-${focusTone}`">
            <div class="family-summary-copy">
              <p class="section-eyebrow">Summary</p>
              <h3>{{ focusSummaryTitle }}</h3>
              <p class="summary-body">{{ focusSummaryCopy }}</p>
              <div class="summary-meta">
                <span class="status-tag tone-info">房间 {{ focusRow?.apartment ?? "--" }}</span>
                <span class="status-tag tone-neutral">设备 {{ selectedDeviceMac || "未选择" }}</span>
                <span class="status-tag tone-neutral">更新时间 {{ focusUpdatedLabel }}</span>
              </div>
            </div>
            <div class="family-summary-score">
              <span>当前风险</span>
              <strong>{{ focusRiskLabel }}</strong>
              <p>
                {{ focusAlarm ? "建议优先查看告警升级建议和正式报告，再决定是否联系社区处理。" : "当前没有活动告警，可结合趋势和评估结果持续观察。" }}
              </p>
            </div>
          </section>

          <div class="family-health-grid family-health-grid--demo">
            <article
              v-for="card in familySnapshotCards"
              :key="card.id"
              class="family-health-card family-health-card--demo"
              :class="`tone-${card.tone}`"
            >
              <div class="family-health-card-top">
                <span class="metric-badge">{{ card.shortLabel }}</span>
                <small>{{ card.label }}</small>
              </div>
              <div class="family-health-card-value">
                <strong>{{ card.value }}</strong>
                <span>{{ card.unit }}</span>
              </div>
              <p>{{ card.note }}</p>
            </article>
          </div>

          <article class="family-trend-panel">
            <div class="panel-head">
              <div>
                <h3>最近趋势预览</h3>
                <p class="panel-subtitle">{{ familyTrendHeadline }}</p>
              </div>
              <span class="meta-pill">片段 {{ familyTrendPreview.length }}</span>
            </div>
            <div v-if="familyTrendPreview.length" class="trend-list trend-list--compact">
              <article v-for="point in familyTrendPreview" :key="point.timestamp" class="trend-item trend-item--demo">
                <div class="trend-item-head">
                  <strong>{{ new Date(point.timestamp).toLocaleString("zh-CN", { hour12: false }) }}</strong>
                  <span>健康分 {{ point.health_score ?? "--" }}</span>
                </div>
                <div class="trend-kpi-row">
                  <span>HR {{ point.heart_rate }}</span>
                  <span>SpO2 {{ point.blood_oxygen }}%</span>
                  <span>Temp {{ point.temperature.toFixed(1) }}°C</span>
                </div>
              </article>
            </div>
            <div v-else class="state-block state-empty">
              <strong>暂无趋势片段</strong>
              <p>设备完成更多同步后，这里会展示最近几个采样点的变化轨迹。</p>
            </div>
          </article>

          <div class="family-chain-grid">
            <HealthEvaluationPanel
              :is-bound="hasBoundDevice"
              :subject-name="focusRow?.name ?? '未选择对象'"
              :device-mac="selectedDeviceMac"
              :evaluation="currentHealthEvaluation"
              :report-summary="currentHealthReportSummary"
              :generated-report="generatedHealthReport"
              :report-loading="reportLoading"
              :report-error="reportError"
              @generate-report="generateHealthReport"
            />
            <AlarmEscalationPanel
              :sample="displayFocusLatest"
              :trend="focusTrend"
              :focus-alarm="focusAlarm"
            />
          </div>
        </div>

        <div v-else class="state-block state-empty state-large">
          <strong>当前还没有可用的绑定设备</strong>
        </div>
      </article>

      <AssistantPanel
        v-if="hasBoundDevice"
        class="family-agent"
        :device-mac="selectedDeviceMac"
        :subject-name="focusRow?.name ?? '未选择对象'"
        :sample="displayFocusLatest"
        :risk-label="focusRiskLabel"
        :focus-alarm="focusAlarm"
        :trend-count="focusTrend.length"
      />
      <article v-else class="panel family-agent">
        <h2>家属助手</h2>
        <p class="subtle-copy">完成设备绑定后，这里会展示基于当前对象状态生成的照护建议与对话入口。</p>
      </article>
    </section>
  </section>
</template>
