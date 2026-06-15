<script setup lang="ts">
import { computed, onMounted, ref, toRef, watch } from "vue";
import type { DeviceBindLogRecord, SessionUser, SystemInfoResponse } from "../api/client";
import { ApiError, api } from "../api/client";
import PageHeader from "../components/layout/PageHeader.vue";
import { useCareDirectoryDashboard } from "../composables/useCareDirectoryDashboard";
import { useRelationActions } from "../composables/useRelationActions";
import { SELECTED_DEVICE_STORAGE_KEY } from "../composables/useCommunityWorkspace";

const props = defineProps<{
  sessionUser: SessionUser;
}>();

const sessionUser = toRef(props, "sessionUser");
const {
  allFamilies,
  community,
  dashboardLoadError,
  dashboardLoading,
  devices,
  elders,
  lastSyncAt,
  refreshDashboardData,
} = useCareDirectoryDashboard(sessionUser, {
  includeAllDevices: true,
  pollIntervalMs: 15000,
});

const deviceHistoryMac = ref("");
const bindHistory = ref<DeviceBindLogRecord[]>([]);
const bindHistoryLoading = ref(false);
const bindHistoryError = ref("");
const deletingMac = ref("");
const lastDeletedDeviceMac = ref("");
const systemInfo = ref<SystemInfoResponse | null>(null);
const systemInfoError = ref("");

const unbindingMac = ref("");
const unbindError = ref("");
const unbindReason = ref("");

const {
  deviceForm,
  elderForm,
  lastRegisteredDeviceMac,
  relationBusy,
  relationError,
  relationStatus,
  submitDeviceAction,
  submitElderRegistration,
} = useRelationActions({
  sessionUser,
  refreshDashboardData,
  getToken: sessionToken,
});

function sessionToken() {
  return localStorage.getItem("ai_health_demo_session_token") ?? "";
}

async function unbindDeviceRecord(mac: string) {
  unbindingMac.value = mac;
  unbindError.value = "";
  deviceForm.value.mode = "unbind";
  deviceForm.value.macAddress = mac;
  deviceForm.value.reason = unbindReason.value;
  await submitDeviceAction();
  unbindReason.value = "";
  unbindingMac.value = "";
  deviceForm.value.mode = "register";
}

function formatUiError(error: unknown, fallback: string) {
  if (error instanceof ApiError && error.detail) return error.detail;
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

function describeBootstrapReason(reason: string | undefined) {
  if (!reason) return "采集器暂未接入";
  if (reason === "shouhuan_missing") return "等待采集器接入";
  if (reason.startsWith("shouhuan_parse_failed")) return "采集配置待检查";
  if (reason === "pyserial_missing") return "采集组件未就绪";
  if (reason.startsWith("serial_open_failed")) return "采集器暂未连接";
  if (reason === "serial_port_available") return "采集器已就绪";
  return "采集器状态待确认";
}

const syncLabel = computed(() =>
  lastSyncAt.value ? lastSyncAt.value.toLocaleTimeString("zh-CN", { hour12: false }) : "尚未同步",
);
const pageMeta = computed(() => [
  `社区 ${community.value?.name || "未分配"}`,
  `老人 ${elders.value.length}`,
  `家属 ${allFamilies.value.length}`,
  `设备 ${devices.value.length}`,
  `同步 ${syncLabel.value}`,
]);
const selectedHistoryDevice = computed(
  () => devices.value.find((device) => device.mac_address === deviceHistoryMac.value) ?? null,
);
const serialRuntime = computed(() => systemInfo.value?.serial_runtime ?? null);
const runtimeMode = computed(() => systemInfo.value?.runtime_mode ?? serialRuntime.value?.runtime_mode ?? "mock");
const serialRuntimeSummary = computed(() => {
  const runtime = serialRuntime.value;
  if (!runtime) return "当前未读取到串口采集配置。";
  const collectionStrategy = runtime.collection_strategy ?? "single_target";
  const targetLabel = runtime.active_target_mac ?? "未锁定目标";
  if (runtimeMode.value === "serial") {
    return `串口已启用 · ${runtime.port} · ${runtime.baudrate} baud · ${collectionStrategy} · ${targetLabel}`;
  }
  const fallbackReason = describeBootstrapReason(runtime.bootstrap_reason ?? systemInfo.value?.bootstrap_reason);
  return `社区样本链路 · ${fallbackReason}`;
});
const collectorPortLabel = computed(() => {
  if (runtimeMode.value !== "serial") return "待识别";
  return serialRuntime.value?.port || "auto-detect";
});
const collectorStatusLabel = computed(() => {
  if (runtimeMode.value === "serial") return "串口已启用，等待完整 A/B 双包";
  return `${describeBootstrapReason(serialRuntime.value?.bootstrap_reason ?? systemInfo.value?.bootstrap_reason)}，可先完成台账登记`;
});
const activeTargetLabel = computed(() => {
  if (runtimeMode.value !== "serial") return "采集器接入后自动锁定";
  const runtime = serialRuntime.value;
  if (!runtime?.active_target_mac) return "未锁定";
  return runtime.active_target_device_name
    ? `${runtime.active_target_device_name} / ${runtime.active_target_mac}`
    : runtime.active_target_mac;
});
const packetMergeLabel = computed(() =>
  serialRuntime.value?.merge_mode === "wait_for_ab" ? "等待 A+B 完整双包" : "未识别",
);
const macInputExamples = computed(() => ["5410260100DF", "54:10:26:01:00:DF"]);
const pendingDeviceCount = computed(() => devices.value.filter((device) => device.status === "pending").length);
const hasElders = computed(() => elders.value.length > 0);
const selectedTargetElder = computed(
  () => elders.value.find((elder) => elder.id === deviceForm.value.targetUserId) ?? null,
);
const lastRegisteredDevice = computed(
  () => devices.value.find((device) => device.mac_address === lastRegisteredDeviceMac.value) ?? null,
);

async function loadSystemInfo() {
  systemInfoError.value = "";
  try {
    systemInfo.value = await api.getSystemInfo();
  } catch (error) {
    systemInfo.value = null;
    systemInfoError.value = formatUiError(error, "系统运行配置读取失败，请稍后重试。");
  }
}

async function refreshBindHistory(mac: string) {
  bindHistoryLoading.value = true;
  bindHistoryError.value = "";
  try {
    bindHistory.value = await api.listDeviceBindLogs(mac);
  } catch (error) {
    bindHistory.value = [];
    bindHistoryError.value = formatUiError(error, "绑定历史加载失败，请稍后重试。");
  } finally {
    bindHistoryLoading.value = false;
  }
}

async function deleteDeviceRecord(mac: string) {
  deletingMac.value = mac;
  try {
    await api.deleteDevice(mac, sessionToken());
    lastDeletedDeviceMac.value = mac;
    await refreshDashboardData();
    await loadSystemInfo();
    if (deviceHistoryMac.value === mac) {
      deviceHistoryMac.value = "";
      bindHistory.value = [];
    }
  } catch (error) {
    bindHistoryError.value = formatUiError(error, "设备删除失败，请稍后重试。");
  } finally {
    deletingMac.value = "";
  }
}

function goToOverviewForRegisteredDevice() {
  if (!lastRegisteredDeviceMac.value) return;
  if (typeof window !== "undefined") {
    window.sessionStorage.setItem(SELECTED_DEVICE_STORAGE_KEY, lastRegisteredDeviceMac.value);
    window.location.hash = "#/overview";
  }
}

function dismissRegisteredDevicePrompt() {
  lastRegisteredDeviceMac.value = "";
}

function submitPrimaryRegisterAction() {
  deviceForm.value.mode = "register";
  void submitDeviceAction();
}

watch(
  elders,
  (list) => {
    if (!list.length) {
      deviceForm.value.targetUserId = "";
      return;
    }
    if (deviceForm.value.targetUserId && !list.some((elder) => elder.id === deviceForm.value.targetUserId)) {
      deviceForm.value.targetUserId = "";
    }
  },
  { immediate: true },
);

watch(
  devices,
  (list) => {
    if (!list.length) {
      deviceHistoryMac.value = "";
      bindHistory.value = [];
      bindHistoryError.value = "";
      return;
    }

    if (!list.some((item) => item.mac_address === deviceHistoryMac.value)) {
      deviceHistoryMac.value = list[0].mac_address;
      return;
    }

    if (deviceHistoryMac.value) void refreshBindHistory(deviceHistoryMac.value);
  },
  { immediate: true },
);

watch(deviceHistoryMac, (mac) => {
  if (!mac) {
    bindHistory.value = [];
    bindHistoryError.value = "";
    return;
  }
  void refreshBindHistory(mac);
});

watch(lastRegisteredDeviceMac, (mac) => {
  if (mac) void loadSystemInfo();
});

onMounted(() => {
  deviceForm.value.mode = "register";
  void loadSystemInfo();
});
</script>

<template>
  <section class="page-stack">
    <PageHeader
      eyebrow="成员与设备管理"
      title="成员设备"
      description="先登记真实 T10 手环，可选择立即绑定老人，也可以先空挂设备台账；采集器收到完整 A/B 双包后，设备会从 pending 自动切到在线监控。"
      :meta="pageMeta"
    />

    <p v-if="dashboardLoadError" class="feedback-banner feedback-error">{{ dashboardLoadError }}</p>

    <section class="member-device-grid">
      <article class="panel member-device-panel">
        <div class="panel-head">
          <div>
            <p class="section-eyebrow">配置新设备</p>
            <h2>注册真实 T10 手环</h2>
            <p class="subtle-copy">
              运营人员只需要输入手环 MAC。你可以直接绑定老人，也可以先登记到设备台账，后续再补绑定关系。
            </p>
          </div>
          <div class="badge-row">
            <span class="summary-badge">{{ serialRuntimeSummary }}</span>
            <span class="summary-badge">待激活设备 {{ pendingDeviceCount }}</span>
            <span v-if="selectedTargetElder" class="summary-badge">默认老人 {{ selectedTargetElder.name }}</span>
          </div>
        </div>

        <div class="form-grid">
          <label class="form-field">
            <span>设备 MAC</span>
            <input
              v-model="deviceForm.macAddress"
              class="text-input"
              type="text"
              placeholder="例如 5410260100DF 或 54:10:26:01:00:DF"
            />
          </label>
          <label class="form-field">
            <span>目标老人（可选）</span>
            <select v-model="deviceForm.targetUserId" class="inline-select relation-select" :disabled="!hasElders">
              <option value="">暂不绑定，先登记设备</option>
              <option v-for="elder in elders" :key="elder.id" :value="elder.id">{{ elder.name }} / {{ elder.apartment }}</option>
            </select>
          </label>
        </div>

        <div class="readout-grid">
          <div class="readout-card">
            <span>采集器串口</span>
            <strong>{{ collectorPortLabel }}</strong>
          </div>
          <div class="readout-card">
            <span>串口状态</span>
            <strong>{{ collectorStatusLabel }}</strong>
          </div>
          <div class="readout-card">
            <span>当前采集目标</span>
            <strong>{{ activeTargetLabel }}</strong>
          </div>
          <div class="readout-card">
            <span>合并模式</span>
            <strong>{{ packetMergeLabel }}</strong>
          </div>
          <div class="readout-card">
            <span>设备名称</span>
            <strong>{{ deviceForm.deviceName }}</strong>
          </div>
          <div class="readout-card">
            <span>型号编码</span>
            <strong>{{ deviceForm.modelCode }}</strong>
          </div>
          <div class="readout-card">
            <span>接入方式</span>
            <strong>{{ deviceForm.ingestMode }}</strong>
          </div>
          <div class="readout-card wide">
            <span>服务 UUID</span>
            <strong>{{ deviceForm.serviceUuid }}</strong>
          </div>
          <div class="readout-card wide">
            <span>设备 UUID</span>
            <strong>{{ deviceForm.deviceUuid }}</strong>
          </div>
          <div class="readout-card wide">
            <span>MAC 输入格式</span>
            <strong>{{ macInputExamples.join(" / ") }}</strong>
          </div>
        </div>

        <div class="tips-block">
          <strong>接入说明</strong>
          <p>
            当前串口链路对齐 `shouhuan.py`：采集器锁定一个目标 MAC，并等待两个响应包都到达。只有 A/B 双包合并成功后，系统才会推送实时心率、血氧、血压和体温。
          </p>
        </div>

        <div class="action-row">
          <button
            type="button"
            class="primary-btn"
            :disabled="relationBusy === 'device'"
            @click="submitPrimaryRegisterAction"
          >
            {{ relationBusy === "device" ? "正在注册..." : "注册手环并等待接入" }}
          </button>
          <p class="helper-copy">
            注册成功后设备会先显示为 <code>pending</code>。可以先空挂到设备台账，后续再补绑定；真实串口接入后，采集器收到完整 A/B 双包就会刷新实时面板。
          </p>
        </div>

        <p v-if="systemInfoError" class="error-copy">{{ systemInfoError }}</p>
        <div v-if="relationStatus" class="status-banner status-success">{{ relationStatus }}</div>
        <div v-if="unbindError" class="status-banner status-error">{{ unbindError }}</div>
        <div v-if="relationError" class="status-banner status-error">{{ relationError }}</div>

        <div v-if="lastRegisteredDeviceMac" class="register-prompt">
          <div>
            <strong>{{ lastRegisteredDevice?.device_name ?? "T10-WATCH" }} 已注册</strong>
            <p>
              {{ lastRegisteredDeviceMac }} 已进入设备台账，当前状态为 {{ lastRegisteredDevice?.status ?? "pending" }}。
              {{ lastRegisteredDevice?.user_id ? "该设备已写入成员关系。" : "该设备当前处于未归属状态，后续可再补绑定。" }}
              采集器接入后，这台设备会被自动锁定为当前采集目标，待完整 A/B 双包到达后即可进入实时监控。
            </p>
          </div>
          <div class="table-actions">
            <button type="button" class="primary-btn" @click="goToOverviewForRegisteredDevice">前往总览监控</button>
            <button type="button" class="ghost-btn" @click="dismissRegisteredDevicePrompt">留在当前页面</button>
          </div>
        </div>
      </article>

      <article class="panel member-device-panel" v-if="!hasElders">
        <div class="panel-head">
          <div>
            <p class="section-eyebrow">新成员档案</p>
            <h2>先补一位老人账号</h2>
            <p class="subtle-copy">如果当前社区还没有老人资料，可以先在这里补一位老人，再回来绑定手环。</p>
          </div>
        </div>

        <div class="form-grid">
          <label class="form-field">
            <span>姓名</span>
            <input v-model="elderForm.name" class="text-input" type="text" placeholder="请输入老人姓名" />
          </label>
          <label class="form-field">
            <span>手机号</span>
            <input v-model="elderForm.phone" class="text-input" type="text" placeholder="请输入手机号" />
          </label>
          <label class="form-field">
            <span>年龄</span>
            <input v-model="elderForm.age" class="text-input" type="number" min="1" />
          </label>
          <label class="form-field">
            <span>房间</span>
            <input v-model="elderForm.apartment" class="text-input" type="text" placeholder="例如 A-302" />
          </label>
        </div>

        <div class="action-row">
          <button type="button" class="primary-btn" :disabled="relationBusy === 'elder'" @click="submitElderRegistration">
            {{ relationBusy === "elder" ? "正在提交..." : "登记老人" }}
          </button>
        </div>
      </article>

      <article class="panel member-device-panel">
        <div class="panel-head">
          <div>
            <p class="section-eyebrow">资产清单管理</p>
            <h2>设备清单</h2>
            <p class="subtle-copy">新注册的 T10 会先以 pending 展示；收到完整双包后自动变为 online。</p>
          </div>
          <span v-if="lastDeletedDeviceMac" class="meta-pill">最近删除 {{ lastDeletedDeviceMac }}</span>
        </div>

        <p v-if="dashboardLoading && !devices.length" class="helper-copy">正在加载设备清单...</p>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>设备</th>
                <th>状态</th>
                <th>激活</th>
                <th>绑定</th>
                <th>当前归属</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="device in devices"
                :key="device.mac_address"
                :class="{ current: device.mac_address === deviceHistoryMac }"
                @click="deviceHistoryMac = device.mac_address"
              >
                <td>
                  <strong>{{ device.device_name }}</strong>
                  <small>{{ device.mac_address }}</small>
                </td>
                <td>{{ device.status }}</td>
                <td>{{ device.activation_state ?? "-" }}</td>
                <td>{{ device.bind_status ?? "-" }}</td>
                <td>{{ elders.find((elder) => elder.id === device.user_id)?.name ?? "未归属" }}</td>
                <td>
                  <div class="table-actions">
                    <button type="button" class="ghost-btn" @click.stop="deviceHistoryMac = device.mac_address">查看历史</button>
                    <button
                      v-if="device.bind_status === 'bound'"
                      type="button"
                      class="ghost-btn"
                      :disabled="unbindingMac === device.mac_address || relationBusy === 'device'"
                      @click.stop="unbindDeviceRecord(device.mac_address)"
                    >
                      {{ unbindingMac === device.mac_address ? "解绑中..." : "解绑设备" }}
                    </button>
                    <button
                      type="button"
                      class="ghost-btn danger-btn"
                      :disabled="deletingMac === device.mac_address"
                      @click.stop="deleteDeviceRecord(device.mac_address)"
                    >
                      {{ deletingMac === device.mac_address ? "删除中..." : "删除设备" }}
                    </button>
                  </div>
                </td>
              </tr>
              <tr v-if="!devices.length">
                <td colspan="6">当前还没有设备清单。</td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>

      <article class="panel member-device-panel">
        <div class="panel-head">
          <div>
            <p class="section-eyebrow">行为日志轴</p>
            <h2>绑定历史</h2>
            <p class="subtle-copy">
              {{
                selectedHistoryDevice
                  ? `当前查看 ${selectedHistoryDevice.device_name} / ${selectedHistoryDevice.mac_address}`
                  : "请选择一台设备查看绑定历史。"
              }}
            </p>
          </div>
        </div>

        <p v-if="bindHistoryError" class="error-copy">{{ bindHistoryError }}</p>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>时间</th>
                <th>操作</th>
                <th>原对象</th>
                <th>新对象</th>
                <th>原因</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="bindHistoryLoading">
                <td colspan="5">绑定历史加载中...</td>
              </tr>
              <tr v-for="item in bindHistory" :key="item.id">
                <td>{{ new Date(item.created_at).toLocaleString("zh-CN", { hour12: false }) }}</td>
                <td>{{ item.action_type }}</td>
                <td>{{ item.old_user_id ?? "-" }}</td>
                <td>{{ item.new_user_id ?? "-" }}</td>
                <td>{{ item.reason ?? "-" }}</td>
              </tr>
              <tr v-if="!bindHistoryLoading && !bindHistory.length">
                <td colspan="5">{{ deviceHistoryMac ? "当前设备还没有绑定历史。" : "请选择一台设备查看绑定历史。" }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>
    </section>
  </section>
</template>

<style scoped>
.member-device-grid {
  display: grid;
  gap: 24px;
  max-width: 100%;
}

.member-device-panel {
  display: grid;
  gap: 24px;
  padding: 32px;
  background: #ffffff;
  border-radius: 20px;
  border: 2px solid #e2e8f0;
  box-shadow: 0 4px 16px rgba(15, 23, 42, 0.06);
}

.panel-head {
  display: flex;
  gap: 24px;
  justify-content: space-between;
  align-items: flex-start;
  padding-bottom: 20px;
  border-bottom: 2px solid #e2e8f0;
}

.panel-head h2 {
  margin: 0;
  color: #0f172a;
  font-family: var(--font-display);
  font-size: 1.5rem;
  font-weight: 700;
}

.subtle-copy {
  margin: 10px 0 0;
  color: #64748b;
  line-height: 1.7;
  font-size: 0.95rem;
}

.badge-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  justify-content: flex-end;
}

.summary-badge {
  padding: 8px 16px;
  border-radius: 999px;
  background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%);
  color: #1e40af;
  font-size: 0.85rem;
  font-weight: 600;
  border: 2px solid #3b82f6;
  white-space: nowrap;
}

.form-grid {
  display: grid;
  gap: 20px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.form-field {
  display: grid;
  gap: 8px;
}

.form-field > span {
  color: #475569;
  font-size: 0.9rem;
  font-weight: 600;
}

.text-input,
.inline-select {
  padding: 12px 16px;
  border-radius: 12px;
  border: 2px solid #cbd5e1;
  background: #ffffff;
  color: #0f172a;
  font-size: 0.95rem;
  transition: all 200ms ease;
}

.text-input:focus,
.inline-select:focus {
  outline: none;
  border-color: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.text-input:disabled,
.inline-select:disabled {
  background: #f1f5f9;
  color: #94a3b8;
  cursor: not-allowed;
}

.readout-grid {
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.readout-card {
  display: grid;
  gap: 8px;
  padding: 18px 20px;
  border-radius: 16px;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border: 2px solid #cbd5e1;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
  transition: all 200ms ease;
}

.readout-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08);
}

.readout-card.wide {
  grid-column: span 2;
}

.readout-card span {
  color: #64748b;
  font-size: 0.8rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.readout-card strong {
  color: #0f172a;
  font-size: 0.95rem;
  font-weight: 700;
  word-break: break-all;
}

.tips-block {
  padding: 20px 24px;
  border-radius: 16px;
  background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
  border: 2px solid #fcd34d;
  color: #92400e;
  box-shadow: 0 2px 8px rgba(245, 158, 11, 0.1);
}

.tips-block strong {
  color: #78350f;
  font-size: 1rem;
  display: block;
  margin-bottom: 8px;
}

.tips-block p {
  margin: 0;
  line-height: 1.7;
  font-size: 0.95rem;
}

.register-prompt {
  padding: 24px;
  border-radius: 16px;
  background: linear-gradient(135deg, #dcfce7 0%, #bbf7d0 100%);
  border: 2px solid #4ade80;
  color: #14532d;
  box-shadow: 0 4px 12px rgba(34, 197, 94, 0.15);
  display: grid;
  gap: 16px;
}

.register-prompt strong {
  color: #14532d;
  font-size: 1.1rem;
  display: block;
  margin-bottom: 8px;
}

.register-prompt p {
  margin: 0;
  line-height: 1.7;
  font-size: 0.95rem;
  color: #166534;
}

.action-row {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.primary-btn {
  padding: 12px 24px;
  border-radius: 12px;
  border: none;
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  color: #ffffff;
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 200ms ease;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
}

.primary-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(59, 130, 246, 0.4);
}

.primary-btn:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
  box-shadow: none;
}

.ghost-btn {
  padding: 10px 20px;
  border-radius: 12px;
  border: 2px solid #cbd5e1;
  background: #ffffff;
  color: #475569;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 200ms ease;
}

.ghost-btn:hover:not(:disabled) {
  border-color: #3b82f6;
  color: #1e40af;
  background: #eff6ff;
}

.ghost-btn:disabled {
  background: #f1f5f9;
  color: #94a3b8;
  cursor: not-allowed;
}

.danger-btn {
  border-color: #fca5a5;
  color: #dc2626;
}

.danger-btn:hover:not(:disabled) {
  border-color: #ef4444;
  background: #fef2f2;
}

.helper-copy {
  color: #64748b;
  font-size: 0.9rem;
  line-height: 1.6;
  margin: 0;
}

.meta-pill {
  padding: 8px 16px;
  border-radius: 999px;
  background: #f1f5f9;
  color: #64748b;
  font-size: 0.85rem;
  font-weight: 600;
  border: 2px solid #cbd5e1;
}

.error-copy {
  color: #dc2626;
  background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
  padding: 16px 20px;
  border-radius: 12px;
  border: 2px solid #fca5a5;
  margin: 0;
  font-size: 0.95rem;
}

.status-banner {
  padding: 16px 20px;
  border-radius: 12px;
  font-size: 0.95rem;
  font-weight: 600;
}

.status-success {
  background: linear-gradient(135deg, #dcfce7 0%, #bbf7d0 100%);
  color: #14532d;
  border: 2px solid #4ade80;
}

.status-error {
  background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
  color: #991b1b;
  border: 2px solid #fca5a5;
}

.feedback-banner {
  padding: 16px 20px;
  border-radius: 12px;
  font-size: 0.95rem;
  margin: 0;
}

.feedback-error {
  background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
  color: #991b1b;
  border: 2px solid #fca5a5;
}

.table-wrap {
  overflow-x: auto;
  border-radius: 16px;
  border: 2px solid #e2e8f0;
  background: #ffffff;
}

.table-wrap table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.9rem;
}

.table-wrap thead {
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border-bottom: 2px solid #e2e8f0;
}

.table-wrap th {
  padding: 16px 20px;
  text-align: left;
  color: #475569;
  font-weight: 700;
  font-size: 0.85rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.table-wrap td {
  padding: 16px 20px;
  color: #0f172a;
  border-bottom: 1px solid #f1f5f9;
}

.table-wrap tbody tr {
  transition: all 200ms ease;
  cursor: pointer;
}

.table-wrap tbody tr:hover {
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
}

.table-wrap tbody tr.current {
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
  border-left: 4px solid #3b82f6;
}

.table-wrap td strong {
  display: block;
  color: #0f172a;
  font-weight: 700;
  font-size: 0.95rem;
}

.table-wrap td small {
  display: block;
  margin-top: 4px;
  color: #64748b;
  font-size: 0.8rem;
  font-family: var(--font-mono);
}

.table-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

@media (max-width: 960px) {
  .member-device-panel {
    padding: 24px;
  }

  .form-grid,
  .readout-grid {
    grid-template-columns: 1fr;
  }

  .readout-card.wide {
    grid-column: span 1;
  }

  .panel-head {
    flex-direction: column;
  }

  .badge-row {
    justify-content: flex-start;
  }

  .table-wrap {
    overflow-x: scroll;
  }
}
</style>
