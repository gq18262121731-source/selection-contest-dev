<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import {
  Box,
  CircleAlert,
  CloudCog,
  MapPinned,
  RefreshCw,
  ShieldCheck,
  Wifi,
  WifiOff,
} from "lucide-vue-next";
import MapPointEditor from "../components/robot/MapPointEditor.vue";
import MappingControlPanel from "../components/robot/MappingControlPanel.vue";
import NavigationEventTimeline from "../components/robot/NavigationEventTimeline.vue";
import NavigationMap from "../components/robot/NavigationMap.vue";
import NavigationSafetyPanel from "../components/robot/NavigationSafetyPanel.vue";
import NavigationTaskPanel from "../components/robot/NavigationTaskPanel.vue";
import PatrolRouteEditor from "../components/robot/PatrolRouteEditor.vue";
import PointCloudViewer from "../components/robot/PointCloudViewer.vue";
import { useRobotNavigation } from "../composables/useRobotNavigation";
import { useRobotPointCloud } from "../composables/useRobotPointCloud";
import type { RobotMapPoint } from "../types/robot";
import {
  MOCK_ENVIRONMENT_NOTICE,
  robotConnectionLabel,
  robotControlOwnerLabel,
  robotExecutionStateLabel,
  robotMappingStateLabel,
} from "../utils/robotPresentation";

const navigation = useRobotNavigation();
const pointCloud = useRobotPointCloud();
const pointDraft = ref<{ x: number; y: number } | null>(null);
const selectedPoint = ref<RobotMapPoint | null>(null);
const editMode = ref(false);

const mockContractHealthy = computed(() => (
  !navigation.contractIssue.value
  && !pointCloud.contractIssue.value
  && navigation.state.value?.provider === "mock"
  && navigation.state.value?.real_motion_enabled === false
));

const selectedRoutePoints = computed(() => navigation.selectedRoute.value?.points ?? []);
const navigationInteractionLock = computed(() => (
  navigation.state.value?.mapping_state === "mapping"
    ? "mapping-active"
    : navigation.activeOperation.value
));

function beginPointCreate() {
  selectedPoint.value = null;
  pointDraft.value = null;
  editMode.value = true;
}

function cancelPointEdit() {
  pointDraft.value = null;
  selectedPoint.value = null;
  editMode.value = false;
}

function selectPoint(point: RobotMapPoint) {
  selectedPoint.value = point;
  pointDraft.value = null;
  editMode.value = false;
}

async function savePoint(payload: Parameters<typeof navigation.savePoint>[0]) {
  const result = await navigation.savePoint(payload);
  if (result) cancelPointEdit();
}

async function invalidatePoint(pointId: string) {
  const result = await navigation.invalidatePoint(pointId);
  if (result) cancelPointEdit();
}

async function saveRoute(payload: { name: string; pointIds: string[] }) {
  const route = await navigation.saveRoute(payload.name, payload.pointIds);
  if (route) await navigation.loadRoute(route.route_id);
}

onMounted(navigation.refresh);
</script>

<template>
  <main class="navigation-page">
    <section class="hero">
      <div class="hero__identity">
        <span class="hero__icon"><MapPinned :size="25" /></span>
        <div>
          <span class="eyebrow">Go2 Mock Navigation Workspace</span>
          <h1>建图巡航</h1>
          <p>在不触发真实运动的前提下，验证地图、点位、巡逻与控制权状态机。</p>
        </div>
      </div>
      <div class="hero__status">
        <span :class="`socket socket--${navigation.connectionState.value}`">
          <Wifi v-if="navigation.connectionState.value === 'connected'" :size="14" />
          <WifiOff v-else :size="14" />
          导航 {{ robotConnectionLabel(navigation.connectionState.value) }}
        </span>
        <span :class="`socket socket--${pointCloud.connectionState.value}`">
          <CloudCog :size="14" />
          点云 {{ robotConnectionLabel(pointCloud.connectionState.value) }}
        </span>
        <span class="socket">建图 {{ robotMappingStateLabel(navigation.state.value?.mapping_state) }}</span>
        <span class="socket">任务 {{ robotExecutionStateLabel(navigation.state.value?.execution_state) }}</span>
        <span class="socket">控制权 {{ robotControlOwnerLabel(navigation.state.value?.control_owner) }}</span>
        <button type="button" :disabled="navigation.loading.value" @click="navigation.refresh">
          <RefreshCw :size="15" :class="{ spinning: navigation.loading.value }" />刷新
        </button>
      </div>
    </section>

    <section class="mock-banner" :class="{ 'mock-banner--error': !mockContractHealthy }">
      <ShieldCheck v-if="mockContractHealthy" :size="18" />
      <CircleAlert v-else :size="18" />
      <div>
        <strong>{{ MOCK_ENVIRONMENT_NOTICE }}</strong>
        <span>
          provider=mock · real_motion_enabled=false。本页没有方向或速度控制；浏览器只连接主系统。
        </span>
      </div>
    </section>

    <section v-if="navigation.operationError.value" class="error-banner" role="alert">
      <CircleAlert :size="18" />
      <div>
        <strong>{{ navigation.operationError.value.code }}</strong>
        <span>{{ navigation.operationError.value.message }}</span>
      </div>
    </section>

    <section v-if="navigation.contractIssue.value || pointCloud.contractIssue.value" class="security-banner" role="alert">
      <CircleAlert :size="19" />
      <div>
        <strong>已停止异常数据源连接</strong>
        <span>
          {{ navigation.contractIssue.value?.message ?? pointCloud.contractIssue.value?.message }}
          （{{ navigation.contractIssue.value?.endpoint ?? pointCloud.contractIssue.value?.endpoint }}）
          页面不会自动重连违反 Mock 合同的数据源。
        </span>
      </div>
    </section>

    <section class="workspace-grid">
      <div class="workspace-grid__main">
        <NavigationMap
          :map="navigation.activeMap.value"
          :points="navigation.points.value"
          :state="navigation.state.value"
          :route-points="selectedRoutePoints"
          :edit-mode="editMode"
          @map-click="pointDraft = $event"
          @select-point="selectPoint"
          @cancel-edit="cancelPointEdit"
        />

        <section class="point-cloud-card">
          <header>
            <span class="point-cloud-card__icon"><Box :size="19" /></span>
            <div>
              <span class="eyebrow">Three.js Mock Point Cloud</span>
              <h2>三维环境预览</h2>
              <p>模拟三维点云，仅用于界面与流程验证；最多 5,000 点，不接入真实雷达点云。</p>
            </div>
            <div class="stream-meta">
              <strong>{{ pointCloud.latestFrame.value?.point_count ?? 0 }}</strong>
              <span>points · seq {{ pointCloud.latestFrame.value?.sequence ?? "—" }}</span>
            </div>
          </header>
          <div v-if="pointCloud.streamError.value" class="inline-warning">
            {{ pointCloud.streamError.value.code }} · {{ pointCloud.streamError.value.message }}
          </div>
          <div v-if="pointCloud.stale.value" class="inline-warning">
            POINT_CLOUD_STREAM_STALE · Mock 点云已超过预期刷新窗口
          </div>
          <PointCloudViewer
            :frame="pointCloud.latestFrame.value"
            :stale="pointCloud.stale.value"
          />
          <footer>
            <span>frame: {{ pointCloud.streamInfo.value?.frame_id ?? "等待中" }}</span>
            <span>scenario: {{ pointCloud.streamInfo.value?.scenario ?? "—" }}</span>
            <span>target: {{ pointCloud.streamInfo.value?.target_fps ?? "—" }} fps</span>
            <span>latest: {{ pointCloud.latestFrame.value?.timestamp ?? "—" }}</span>
            <button
              type="button"
              :disabled="Boolean(pointCloud.contractIssue.value)"
              @click="pointCloud.reconnect"
            >
              重连点云
            </button>
          </footer>
        </section>
      </div>

      <aside class="workspace-grid__side">
        <MappingControlPanel
          :mapping-state="navigation.state.value?.mapping_state"
          :active-map="navigation.activeMap.value"
          :active-operation="navigation.activeOperation.value"
          @start="navigation.startMapping"
          @stop="navigation.stopMapping"
          @preview="navigation.previewMap"
          @save="navigation.saveMap($event.name, $event.replaceConfirmed)"
        />
        <MapPointEditor
          :active-map="navigation.activeMap.value"
          :points="navigation.points.value"
          :draft="pointDraft"
          :selected-point="selectedPoint"
          :active-operation="navigationInteractionLock"
          @begin-create="beginPointCreate"
          @cancel="cancelPointEdit"
          @save="savePoint"
          @invalidate="invalidatePoint"
        />
        <PatrolRouteEditor
          :active-map="navigation.activeMap.value"
          :points="navigation.points.value"
          :routes="navigation.routes.value"
          :selected-route="navigation.selectedRoute.value"
          :active-operation="navigationInteractionLock"
          @save="saveRoute"
          @load="navigation.loadRoute"
          @start="navigation.startPatrol"
        />
        <NavigationTaskPanel
          :task="navigation.currentTask.value"
          :execution-state="navigation.state.value?.execution_state"
          :control-owner="navigation.state.value?.control_owner"
          :active-operation="navigationInteractionLock"
          @pause="navigation.pauseTask"
          @resume="navigation.resumeTask"
          @stop="navigation.stopTask"
          @manual-acquire="navigation.acquireManualControl"
          @manual-release="navigation.releaseManualControl"
        />
        <NavigationSafetyPanel :state="navigation.state.value" />
        <NavigationEventTimeline :items="navigation.timeline.value" />
      </aside>
    </section>
  </main>
</template>

<style scoped>
.navigation-page {
  display: grid;
  gap: 18px;
  padding-bottom: 32px;
  color: #0f172a;
}

.hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 22px 24px;
  border: 1px solid #dbe4ee;
  border-radius: 22px;
  background: #fff;
  box-shadow: 0 12px 30px rgba(15, 23, 42, .05);
}

.hero__identity { display: flex; align-items: center; gap: 16px; }
.hero__icon {
  display: grid;
  width: 54px;
  height: 54px;
  flex: 0 0 auto;
  place-items: center;
  border-radius: 16px;
  background: #2563eb;
  color: #fff;
  box-shadow: 0 8px 20px rgba(37, 99, 235, .24);
}
.eyebrow { color: #2563eb; font-size: .67rem; font-weight: 850; letter-spacing: .12em; text-transform: uppercase; }
h1 { margin: 4px 0 4px; font-size: 1.7rem; letter-spacing: -.035em; }
.hero p, .point-cloud-card p { margin: 0; color: #64748b; font-size: .8rem; line-height: 1.5; }
.hero__status { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 7px; }
.hero__status > span, .hero__status > button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 34px;
  padding: 7px 10px;
  border: 1px solid #dbe4ee;
  border-radius: 10px;
  background: #fff;
  color: #475569;
  font-size: .7rem;
  font-weight: 750;
}
.hero__status > button { cursor: pointer; }
.socket--connected { border-color: #bbf7d0 !important; color: #166534 !important; }
.socket--error { border-color: #fecaca !important; color: #b91c1c !important; }

.mock-banner, .error-banner, .security-banner {
  display: grid;
  grid-template-columns: auto 1fr;
  align-items: start;
  gap: 10px;
  padding: 13px 16px;
  border: 1px solid #bfdbfe;
  border-radius: 14px;
  background: #eff6ff;
  color: #1e40af;
}
.mock-banner div, .error-banner div, .security-banner div { display: grid; gap: 2px; }
.mock-banner strong, .error-banner strong, .security-banner strong { font-size: .78rem; }
.mock-banner span, .error-banner span, .security-banner span { font-size: .72rem; line-height: 1.5; }
.mock-banner--error, .security-banner { border-color: #fecaca; background: #fef2f2; color: #991b1b; }
.error-banner { border-color: #fed7aa; background: #fff7ed; color: #9a3412; }

.workspace-grid { display: grid; grid-template-columns: minmax(0, 1.75fr) minmax(320px, .78fr); gap: 18px; align-items: start; }
.workspace-grid__main, .workspace-grid__side { display: grid; gap: 18px; min-width: 0; }

.point-cloud-card {
  display: grid;
  gap: 15px;
  padding: 20px;
  border: 1px solid #dbe4ee;
  border-radius: 20px;
  background: #fff;
  box-shadow: 0 12px 28px rgba(15, 23, 42, .05);
}
.point-cloud-card > header { display: grid; grid-template-columns: auto 1fr auto; gap: 12px; align-items: start; }
.point-cloud-card__icon { display: grid; width: 40px; height: 40px; place-items: center; border-radius: 11px; background: #eef2ff; color: #4f46e5; }
.point-cloud-card h2 { margin: 3px 0; font-size: 1.05rem; }
.stream-meta { display: grid; justify-items: end; color: #64748b; }
.stream-meta strong { color: #0f172a; font-size: 1.15rem; }
.stream-meta span { font-size: .66rem; }
.point-cloud-card > footer { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 14px; color: #64748b; font-family: ui-monospace, monospace; font-size: .65rem; }
.point-cloud-card > footer button { margin-left: auto; padding: 6px 9px; border: 1px solid #cbd5e1; border-radius: 8px; background: #fff; color: #334155; font-family: inherit; cursor: pointer; }
.point-cloud-card > footer button:disabled { opacity: .45; cursor: not-allowed; }
.inline-warning { padding: 9px 11px; border-radius: 9px; background: #fffbeb; color: #92400e; font-size: .7rem; }

.spinning { animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

@media (max-width: 1220px) {
  .workspace-grid { grid-template-columns: 1fr; }
  .workspace-grid__side { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 780px) {
  .hero { align-items: flex-start; flex-direction: column; }
  .hero__status { justify-content: flex-start; }
  .workspace-grid__side { grid-template-columns: 1fr; }
  .point-cloud-card > header { grid-template-columns: auto 1fr; }
  .stream-meta { grid-column: 1 / -1; justify-items: start; }
}
</style>
