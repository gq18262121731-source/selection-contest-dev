<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { AlertTriangle, CheckCircle2, RefreshCw, Siren, Video, WifiOff } from "lucide-vue-next";
import {
  api,
  type AlarmRecord,
  type VideoBridgeAnalysisRecord,
  type VideoBridgeRuntimeConfigResponse,
  type VideoBridgeStatusResponse,
} from "../api/client";
import PageHeader from "../components/layout/PageHeader.vue";

const status = ref<VideoBridgeStatusResponse | null>(null);
const runtimeConfig = ref<VideoBridgeRuntimeConfigResponse | null>(null);
const loading = ref(false);
const simulatingFall = ref(false);
const savingConfig = ref(false);
const error = ref("");
const simulationMessage = ref("");
const simulatedAlarm = ref<AlarmRecord | null>(null);
const alarmQueueCount = ref<number | null>(null);
const visionHost = ref("192.168.8.253");
const visionActionMessage = ref("");
const configMessage = ref("");

const configForm = ref({
  base_url: "",
  camera_id: "camera_01",
  poll_enabled: true,
  poll_hz: 2,
  timeout_seconds: 2.5,
  push_token: "",
  target_device_mac: "",
  target_elder_id: "",
  target_family_ids: "",
});

const latest = computed(() => status.value?.latest ?? null);
const cameras = computed(() => status.value?.cameras ?? []);
const visionService = computed(() => status.value?.vision_service ?? {});
const poseKeypointCount = computed(() => {
  const count = latest.value?.metadata?.pose_keypoint_count;
  return typeof count === "number" ? count : 0;
});
const latestDisplaySource = computed(() => String(latest.value?.metadata?.display_source ?? "-"));
const latestAnalysisSource = computed(() => String(latest.value?.metadata?.analysis_source ?? "-"));
const pageMeta = computed(() => [
  `adapter ${status.value?.adapter_version ?? "video_adapter.v1"}`,
  `cameras ${status.value?.camera_count ?? 0}`,
  `state ${status.value?.bridge_state ?? "unknown"}`,
  `vision ${visionService.value.base_url ?? "unconfigured"}`,
]);

const stateTone = computed(() => {
  const state = status.value?.bridge_state ?? "unknown";
  if (state === "running") return "good";
  if (state === "mock" || state === "unknown" || state === "stopped") return "idle";
  return "warn";
});

function formatTimestamp(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { hour12: false });
}

function formatNumber(value?: number | null, digits = 1) {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return value.toFixed(digits);
}

function targetLabel(record: VideoBridgeAnalysisRecord) {
  const target = record.target;
  if (!target) return "reserved";
  if (typeof target === "string") return target;
  const label = typeof target.label === "string" ? target.label : "";
  const id = typeof target.target_id === "string" ? target.target_id : "";
  return label || id || "reserved";
}

function syncConfigForm(payload: VideoBridgeRuntimeConfigResponse) {
  runtimeConfig.value = payload;
  configForm.value = {
    base_url: payload.base_url,
    camera_id: payload.camera_id,
    poll_enabled: payload.poll_enabled,
    poll_hz: payload.poll_hz,
    timeout_seconds: payload.timeout_seconds,
    push_token: "",
    target_device_mac: payload.target_device_mac,
    target_elder_id: payload.target_elder_id,
    target_family_ids: payload.target_family_ids.join(", "),
  };
  const extractedHost = payload.base_url.replace(/^https?:\/\//i, "").split(":")[0];
  if (extractedHost) {
    visionHost.value = extractedHost;
  }
}

async function refreshStatus() {
  loading.value = true;
  error.value = "";
  try {
    const [statusPayload, runtimePayload] = await Promise.all([
      api.getVideoBridgeStatus(),
      api.getVideoBridgeRuntimeConfig(),
    ]);
    status.value = statusPayload;
    syncConfigForm(runtimePayload);
  } catch (err) {
    error.value = err instanceof Error ? err.message : "视频接入状态读取失败";
  } finally {
    loading.value = false;
  }
}

async function saveRuntimeConfig() {
  if (savingConfig.value) return;
  savingConfig.value = true;
  error.value = "";
  configMessage.value = "";
  try {
    const saved = await api.updateVideoBridgeRuntimeConfig({
      base_url: configForm.value.base_url,
      camera_id: configForm.value.camera_id,
      poll_enabled: configForm.value.poll_enabled,
      poll_hz: Number(configForm.value.poll_hz),
      timeout_seconds: Number(configForm.value.timeout_seconds),
      push_token: configForm.value.push_token.trim() || undefined,
      target_device_mac: configForm.value.target_device_mac,
      target_elder_id: configForm.value.target_elder_id,
      target_family_ids: configForm.value.target_family_ids,
    });
    syncConfigForm(saved);
    configMessage.value = "运行时配置已保存并立即生效";
    await refreshStatus();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "运行时配置保存失败";
  } finally {
    savingConfig.value = false;
  }
}

async function simulateFallAlarm() {
  if (simulatingFall.value) return;
  simulatingFall.value = true;
  error.value = "";
  simulationMessage.value = "";
  try {
    const record = latest.value;
    const result = await api.simulateVideoBridgeFallAlarm({
      camera_id: record?.camera_id,
      stream_name: record?.stream_name,
      fall_prob: record?.fall_prob && record.fall_prob >= 0.5 ? record.fall_prob : 0.91,
      snapshot_url: record?.snapshot_url ?? "/api/v1/camera/processed-snapshot",
      track_id: record?.track_id ?? "video-bridge-demo",
    });
    simulatedAlarm.value = result.alarm;
    const queue = await api.listAlarmQueue();
    alarmQueueCount.value = queue.length;
    await refreshStatus();
    simulationMessage.value = `已推送到主系统告警链路：${result.alarm.id}`;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "疑似风险告警触发失败";
  } finally {
    simulatingFall.value = false;
  }
}

async function pollVisionOnce() {
  loading.value = true;
  error.value = "";
  visionActionMessage.value = "";
  try {
    await api.pollVideoBridgeVisionOnce();
    await refreshStatus();
    visionActionMessage.value = "已拉取视觉服务最新结果";
  } catch (err) {
    error.value = err instanceof Error ? err.message : "视觉服务拉取失败";
  } finally {
    loading.value = false;
  }
}

async function probeVisionHost() {
  const host = visionHost.value.trim();
  if (!host) return;
  loading.value = true;
  error.value = "";
  visionActionMessage.value = "";
  try {
    await api.probeVideoBridgeVisionStream({ host, port: 10554, timeout_ms: 1500 });
    visionActionMessage.value = `探测完成：${host}:10554`;
  } catch (err) {
    error.value = err instanceof Error ? err.message : "摄像头探测失败";
  } finally {
    loading.value = false;
  }
}

async function switchVisionHost() {
  const host = visionHost.value.trim();
  if (!host) return;
  loading.value = true;
  error.value = "";
  visionActionMessage.value = "";
  try {
    await api.switchVideoBridgeVisionHost({
      camera_id: configForm.value.camera_id || "camera_01",
      host,
      username: "admin",
      password: "",
      port: 10554,
      main_path: "/tcp/av0_0",
      analysis_path: "/tcp/av0_1",
    });
    visionActionMessage.value = `已切换视觉服务拉流主机：${host}`;
    await pollVisionOnce();
  } catch (err) {
    error.value = err instanceof Error ? err.message : "切换拉流失败";
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  void refreshStatus();
});
</script>

<template>
  <section class="page-stack video-bridge-page">
    <PageHeader
      eyebrow="Video Bridge / Runtime"
      title="外部视觉告警接入"
      description="主系统可轮询指定 IP 的视觉服务，也可接收外部服务主动推送，并统一进入现有跌倒告警与弹窗链路。"
      :meta="pageMeta"
    >
      <template #actions>
        <button type="button" class="ghost-btn" :disabled="loading" @click="refreshStatus">
          <RefreshCw :size="16" />
          刷新状态
        </button>
        <button type="button" class="ghost-btn" :disabled="loading" @click="pollVisionOnce">
          <RefreshCw :size="16" />
          拉取视觉结果
        </button>
        <button type="button" class="video-bridge-alert-btn" :disabled="simulatingFall" @click="simulateFallAlarm">
          <Siren :size="16" />
          {{ simulatingFall ? "发送中" : "模拟跌倒告警" }}
        </button>
      </template>
    </PageHeader>

    <p v-if="error" class="feedback-banner feedback-error">{{ error }}</p>
    <p v-if="simulationMessage" class="feedback-banner feedback-success">{{ simulationMessage }}</p>
    <p v-if="visionActionMessage" class="feedback-banner feedback-success">{{ visionActionMessage }}</p>
    <p v-if="configMessage" class="feedback-banner feedback-success">{{ configMessage }}</p>

    <section class="panel video-bridge-demo-panel">
      <div class="video-bridge-demo-panel__copy">
        <p class="section-eyebrow">Runtime Config</p>
        <h2>目标 IP 与运行时配置</h2>
        <p class="subtle-copy">
          配置会写入本地运行时配置文件，优先级高于 <code>.env</code> 默认值，保存后立即生效。
        </p>
      </div>

      <div class="video-bridge-config-grid">
        <label>
          <span>Base URL</span>
          <input v-model="configForm.base_url" type="text" />
        </label>
        <label>
          <span>Camera ID</span>
          <input v-model="configForm.camera_id" type="text" />
        </label>
        <label>
          <span>Poll Hz</span>
          <input v-model.number="configForm.poll_hz" type="number" min="0.2" max="5" step="0.1" />
        </label>
        <label>
          <span>Timeout Seconds</span>
          <input v-model.number="configForm.timeout_seconds" type="number" min="0.5" max="30" step="0.1" />
        </label>
        <label>
          <span>Push Token</span>
          <input v-model="configForm.push_token" type="text" placeholder="留空表示不更新当前令牌" />
        </label>
        <label>
          <span>Target Device MAC</span>
          <input v-model="configForm.target_device_mac" type="text" />
        </label>
        <label>
          <span>Target Elder ID</span>
          <input v-model="configForm.target_elder_id" type="text" />
        </label>
        <label>
          <span>Target Family IDs</span>
          <input v-model="configForm.target_family_ids" type="text" placeholder="family_001, family_002" />
        </label>
        <label class="video-bridge-config-grid__checkbox">
          <input v-model="configForm.poll_enabled" type="checkbox" />
          <span>启用后台轮询</span>
        </label>
        <div class="video-bridge-config-grid__actions">
          <button type="button" class="ghost-btn" :disabled="savingConfig" @click="saveRuntimeConfig">
            <RefreshCw :size="16" />
            {{ savingConfig ? "保存中" : "保存配置" }}
          </button>
          <span class="meta-pill">push token: {{ runtimeConfig?.push_token_set ? "configured" : "empty" }}</span>
        </div>
      </div>
    </section>

    <section class="video-bridge-layout">
      <article class="panel video-bridge-hero">
        <div class="video-bridge-hero__copy">
          <p class="section-eyebrow">Main System Adapter</p>
          <h2>外部视觉服务状态桥接</h2>
          <p class="subtle-copy">
            这里展示结构化结果字段。轮询结果满足跌倒条件时会自动升级成正式告警，否则仅保留为状态页调试信息。
          </p>
        </div>

        <div class="video-bridge-stage" aria-label="视觉分析状态">
          <div class="video-bridge-stage__frame">
            <Video :size="42" />
            <span>Analysis Placeholder</span>
          </div>
          <div
            v-if="latest?.bbox"
            class="video-bridge-stage__bbox"
            :class="`video-bridge-stage__bbox--${latest.risk}`"
          >
            <span>{{ latest.track_id ?? "track pending" }}</span>
          </div>
        </div>
      </article>

      <article class="panel video-bridge-status">
        <div class="video-bridge-status__heading">
          <component
            :is="stateTone === 'good' ? CheckCircle2 : stateTone === 'warn' ? AlertTriangle : WifiOff"
            :size="20"
          />
          <div>
            <p class="section-eyebrow">Bridge State</p>
            <h2>{{ status?.bridge_state ?? "unknown" }}</h2>
          </div>
        </div>

        <div class="video-bridge-metrics">
          <span><strong>{{ formatNumber(latest?.frame_age_ms, 0) }}</strong><small>frame_age_ms</small></span>
          <span><strong>{{ formatNumber(latest?.video_fps) }}</strong><small>video_fps</small></span>
          <span><strong>{{ formatNumber(latest?.overlay_fps) }}</strong><small>overlay_fps</small></span>
          <span><strong>{{ formatNumber(latest?.ws_fps) }}</strong><small>ws_fps</small></span>
        </div>

        <dl class="video-bridge-fields">
          <div><dt>camera_id</dt><dd>{{ latest?.camera_id ?? "-" }}</dd></div>
          <div><dt>stream_name</dt><dd>{{ latest?.stream_name ?? "-" }}</dd></div>
          <div><dt>display_source</dt><dd>{{ latestDisplaySource }}</dd></div>
          <div><dt>analysis_source</dt><dd>{{ latestAnalysisSource }}</dd></div>
          <div><dt>pose_points</dt><dd>{{ poseKeypointCount }}</dd></div>
          <div><dt>target</dt><dd>{{ latest ? targetLabel(latest) : "-" }}</dd></div>
          <div><dt>fall_state</dt><dd>{{ latest?.fall_state ?? "-" }}</dd></div>
          <div><dt>risk</dt><dd>{{ latest?.risk ?? "-" }}</dd></div>
          <div><dt>fall_prob</dt><dd>{{ formatNumber(latest?.fall_prob, 2) }}</dd></div>
          <div><dt>snapshot_url</dt><dd>{{ latest?.snapshot_url ?? "-" }}</dd></div>
          <div><dt>camera_lost</dt><dd>{{ latest?.camera_lost ? "true" : "false" }}</dd></div>
          <div><dt>capture_stale</dt><dd>{{ latest?.capture_stale ? "true" : "false" }}</dd></div>
          <div><dt>timestamp</dt><dd>{{ formatTimestamp(latest?.timestamp) }}</dd></div>
        </dl>
      </article>
    </section>

    <section class="panel video-bridge-demo-panel">
      <div class="video-bridge-demo-panel__copy">
        <p class="section-eyebrow">Vision Pull Mode</p>
        <h2>轮询状态与提升结果</h2>
        <p class="subtle-copy">
          主系统会定期访问配置好的视觉服务，读取 health、stream source 和 latest result，并在满足条件时自动进入告警链路。
        </p>
      </div>
      <div class="video-bridge-vision-tools">
        <dl class="video-bridge-fields">
          <div><dt>base_url</dt><dd>{{ visionService.base_url ?? "-" }}</dd></div>
          <div><dt>camera_id</dt><dd>{{ visionService.camera_id ?? "camera_01" }}</dd></div>
          <div><dt>poll_hz</dt><dd>{{ visionService.poll_hz ?? "-" }}</dd></div>
          <div><dt>timeout_seconds</dt><dd>{{ visionService.timeout_seconds ?? "-" }}</dd></div>
          <div><dt>last_ok_at</dt><dd>{{ formatTimestamp(visionService.last_ok_at) }}</dd></div>
          <div><dt>last_promoted_at</dt><dd>{{ formatTimestamp(visionService.last_promoted_at) }}</dd></div>
          <div><dt>last_promoted_key</dt><dd>{{ visionService.last_promoted_key ?? "-" }}</dd></div>
          <div><dt>last_source_ip</dt><dd>{{ visionService.last_source_ip ?? "-" }}</dd></div>
          <div><dt>last_suppression</dt><dd>{{ visionService.last_suppression_reason ?? "-" }}</dd></div>
          <div><dt>target_device_mac</dt><dd>{{ visionService.target_device_mac ?? "-" }}</dd></div>
          <div><dt>target_elder_id</dt><dd>{{ visionService.target_elder_id ?? "-" }}</dd></div>
          <div><dt>target_family_ids</dt><dd>{{ (visionService.target_family_ids ?? []).join(", ") || "-" }}</dd></div>
          <div><dt>last_error</dt><dd>{{ visionService.last_error ?? "-" }}</dd></div>
        </dl>
        <div class="video-bridge-host-row">
          <input v-model="visionHost" type="text" aria-label="摄像头 IP" />
          <button type="button" class="ghost-btn" :disabled="loading" @click="probeVisionHost">探测</button>
          <button type="button" class="ghost-btn" :disabled="loading" @click="switchVisionHost">切换拉流</button>
        </div>
      </div>
    </section>

    <section class="panel video-bridge-demo-panel video-bridge-demo-panel--alarm">
      <div class="video-bridge-demo-panel__copy">
        <p class="section-eyebrow">Alarm Loop Demo</p>
        <h2>模拟跌倒告警</h2>
        <p class="subtle-copy">
          点击后会调用 <strong>/api/v1/video-bridge/simulate-fall-alarm</strong>，进入现有
          <strong>/ws/alarms</strong> 实时告警链路，供社区网页和 Flutter 家属端联调。
        </p>
        <button
          type="button"
          class="video-bridge-alert-btn video-bridge-alert-btn--large"
          :disabled="simulatingFall"
          @click="simulateFallAlarm"
        >
          <Siren :size="18" />
          {{ simulatingFall ? "正在推送告警" : "模拟跌倒告警" }}
        </button>
      </div>
      <dl class="video-bridge-fields">
        <div><dt>alarm_id</dt><dd>{{ simulatedAlarm?.id ?? "-" }}</dd></div>
        <div><dt>alarm_type</dt><dd>{{ simulatedAlarm?.alarm_type ?? "fall_injury_risk" }}</dd></div>
        <div><dt>device_mac</dt><dd>{{ simulatedAlarm?.device_mac ?? "-" }}</dd></div>
        <div><dt>risk</dt><dd>high</dd></div>
        <div><dt>fall_prob</dt><dd>{{ formatNumber(simulatedAlarm?.anomaly_probability, 2) }}</dd></div>
        <div><dt>created_at</dt><dd>{{ formatTimestamp(simulatedAlarm?.created_at) }}</dd></div>
        <div><dt>alarm_queue</dt><dd>{{ alarmQueueCount === null ? "-" : `${alarmQueueCount} active` }}</dd></div>
        <div><dt>delivery</dt><dd>community web / Flutter family websocket</dd></div>
      </dl>
    </section>

    <section class="panel video-bridge-table">
      <div class="video-bridge-table__header">
        <div>
          <p class="section-eyebrow">Reserved Cameras</p>
          <h2>最近视频分析结果</h2>
        </div>
        <span class="meta-pill">{{ cameras.length }} 路</span>
      </div>

      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>camera_id</th>
              <th>stream</th>
              <th>state</th>
              <th>fps</th>
              <th>track</th>
              <th>risk</th>
              <th>fall_prob</th>
              <th>received_at</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="item in cameras" :key="`${item.camera_id}:${item.stream_name}`">
              <td><strong>{{ item.camera_id }}</strong></td>
              <td>{{ item.stream_name }}</td>
              <td>{{ item.service_state }}</td>
              <td>{{ formatNumber(item.video_fps) }} / {{ formatNumber(item.overlay_fps) }}</td>
              <td>{{ item.track_id ?? "-" }}</td>
              <td>{{ item.risk }}</td>
              <td>{{ formatNumber(item.fall_prob, 2) }}</td>
              <td>{{ formatTimestamp(item.received_at) }}</td>
            </tr>
            <tr v-if="!cameras.length">
              <td colspan="8">暂无视频分析推送，等待独立视觉服务接入。</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </section>
</template>

<style scoped>
.video-bridge-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.25fr) minmax(320px, 0.75fr);
  gap: 18px;
  align-items: stretch;
}

.video-bridge-alert-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border: 1px solid rgba(220, 38, 38, 0.28);
  border-radius: 12px;
  background: #dc2626;
  color: #fff7ed;
  font-weight: 800;
  cursor: pointer;
  transition: transform 160ms ease, box-shadow 160ms ease, opacity 160ms ease;
  box-shadow: 0 8px 18px rgba(220, 38, 38, 0.18);
}

.video-bridge-alert-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 12px 24px rgba(220, 38, 38, 0.24);
}

.video-bridge-alert-btn:disabled {
  cursor: not-allowed;
  opacity: 0.65;
}

.video-bridge-alert-btn--large {
  width: fit-content;
  padding: 12px 18px;
  border-radius: 10px;
}

.video-bridge-hero {
  display: grid;
  grid-template-columns: minmax(0, 0.85fr) minmax(320px, 1.15fr);
  gap: 22px;
  align-items: center;
}

.video-bridge-hero__copy h2,
.video-bridge-status h2,
.video-bridge-table h2,
.video-bridge-demo-panel__copy h2 {
  margin: 0;
  color: var(--text-main);
}

.video-bridge-stage {
  position: relative;
  min-height: 320px;
  border-radius: var(--radius-lg);
  overflow: hidden;
  background:
    linear-gradient(90deg, rgba(15, 23, 42, 0.06) 1px, transparent 1px),
    linear-gradient(0deg, rgba(15, 23, 42, 0.06) 1px, transparent 1px),
    linear-gradient(135deg, #eef6ff 0%, #f7fbf8 100%);
  background-size: 32px 32px, 32px 32px, auto;
  border: 1px solid var(--line-medium);
}

.video-bridge-stage__frame {
  position: absolute;
  inset: 0;
  display: grid;
  place-content: center;
  gap: 10px;
  text-align: center;
  color: #2563eb;
  font-weight: 800;
}

.video-bridge-stage__bbox {
  position: absolute;
  left: 28%;
  top: 18%;
  width: 34%;
  height: 68%;
  border: 2px solid #2563eb;
  border-radius: 10px;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.72);
}

.video-bridge-stage__bbox span {
  position: absolute;
  left: 8px;
  top: 8px;
  padding: 4px 8px;
  border-radius: 8px;
  background: #2563eb;
  color: #ffffff;
  font-size: 0.78rem;
  font-weight: 800;
}

.video-bridge-stage__bbox--high,
.video-bridge-stage__bbox--critical {
  border-color: var(--risk-high);
}

.video-bridge-stage__bbox--high span,
.video-bridge-stage__bbox--critical span {
  background: var(--risk-high);
}

.video-bridge-status {
  display: grid;
  gap: 18px;
}

.video-bridge-status__heading {
  display: flex;
  align-items: center;
  gap: 12px;
}

.video-bridge-status__heading > svg {
  color: #2563eb;
}

.video-bridge-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.video-bridge-metrics span {
  display: grid;
  gap: 4px;
  padding: 14px;
  border-radius: var(--radius-md);
  background: var(--panel-tinted);
  border: 1px solid var(--line);
}

.video-bridge-metrics strong {
  font-size: 1.35rem;
  color: var(--text-main);
}

.video-bridge-metrics small,
.video-bridge-fields dt {
  color: var(--text-sub);
  font-size: 0.78rem;
}

.video-bridge-fields {
  display: grid;
  gap: 10px;
  margin: 0;
}

.video-bridge-fields div {
  display: grid;
  grid-template-columns: 140px minmax(0, 1fr);
  gap: 10px;
  align-items: baseline;
}

.video-bridge-fields dd {
  margin: 0;
  min-width: 0;
  overflow-wrap: anywhere;
  color: var(--text-main);
  font-weight: 700;
}

.video-bridge-table {
  display: grid;
  gap: 14px;
}

.video-bridge-demo-panel {
  display: grid;
  grid-template-columns: minmax(0, 0.8fr) minmax(320px, 1.2fr);
  gap: 18px;
  align-items: start;
  border-color: rgba(37, 99, 235, 0.14);
}

.video-bridge-demo-panel--alarm {
  background:
    linear-gradient(135deg, rgba(254, 242, 242, 0.9), rgba(255, 255, 255, 0.98) 54%),
    var(--panel);
}

.video-bridge-demo-panel__copy {
  display: grid;
  gap: 8px;
}

.video-bridge-demo-panel__copy strong {
  color: var(--text-main);
  font-weight: 800;
}

.video-bridge-vision-tools {
  display: grid;
  gap: 14px;
}

.video-bridge-config-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.video-bridge-config-grid label {
  display: grid;
  gap: 6px;
}

.video-bridge-config-grid span {
  font-size: 0.78rem;
  color: var(--text-sub);
  font-weight: 700;
}

.video-bridge-config-grid input {
  min-width: 0;
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--line-medium);
  border-radius: var(--radius-sm);
  color: var(--text-main);
  background: #ffffff;
  font: inherit;
}

.video-bridge-config-grid__checkbox {
  display: flex !important;
  align-items: center;
  gap: 10px;
}

.video-bridge-config-grid__checkbox input {
  width: 18px;
  height: 18px;
}

.video-bridge-config-grid__actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.video-bridge-host-row {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.video-bridge-host-row input {
  min-width: 220px;
  flex: 1 1 220px;
  padding: 10px 12px;
  border: 1px solid var(--line-medium);
  border-radius: var(--radius-sm);
  color: var(--text-main);
  background: #ffffff;
  font: inherit;
}

.video-bridge-table__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}

code {
  font-family: var(--font-mono);
}

@media (max-width: 1100px) {
  .video-bridge-layout,
  .video-bridge-hero,
  .video-bridge-demo-panel,
  .video-bridge-config-grid {
    grid-template-columns: 1fr;
  }
}
</style>
