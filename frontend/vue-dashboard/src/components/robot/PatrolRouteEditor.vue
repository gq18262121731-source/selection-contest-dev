<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { ArrowDown, ArrowUp, Flag, Play, Plus, Route, X } from "lucide-vue-next";
import type {
  RobotMap,
  RobotMapPoint,
  RobotPatrolRoute,
  RobotRouteDetail,
} from "../../types/robot";
import { validateRobotRoutePointIds } from "../../utils/robotNavigationPolicy";

const props = defineProps<{
  activeMap: RobotMap | null;
  points: RobotMapPoint[];
  routes: RobotPatrolRoute[];
  selectedRoute: RobotRouteDetail | null;
  activeOperation: string | null;
}>();

const emit = defineEmits<{
  save: [payload: { name: string; pointIds: string[] }];
  load: [routeId: string];
  start: [routeId: string];
}>();

const name = ref("日常巡查路线");
const pointIds = ref<string[]>([]);
const selectedPointId = ref("");
const selectedRouteId = ref("");
const validPoints = computed(() => (
  props.points.filter((point) => point.status === "valid" && point.point_type === "patrol")
));
const validation = computed(() => validateRobotRoutePointIds(pointIds.value, props.points));
const busy = computed(() => Boolean(props.activeOperation));

watch(
  () => props.selectedRoute,
  (detail) => {
    if (!detail) return;
    selectedRouteId.value = detail.route.route_id;
    name.value = detail.route.name;
    pointIds.value = [...detail.points]
      .sort((a, b) => a.sequence - b.sequence)
      .map((item) => item.point_id);
  },
);

function pointName(pointId: string) {
  return props.points.find((point) => point.point_id === pointId)?.name ?? pointId;
}

function addPoint() {
  if (!selectedPointId.value || pointIds.value.includes(selectedPointId.value)) return;
  pointIds.value = [...pointIds.value, selectedPointId.value];
  selectedPointId.value = "";
}

function removePoint(index: number) {
  pointIds.value = pointIds.value.filter((_, current) => current !== index);
}

function move(index: number, direction: -1 | 1) {
  const target = index + direction;
  if (target < 0 || target >= pointIds.value.length) return;
  const next = [...pointIds.value];
  [next[index], next[target]] = [next[target], next[index]];
  pointIds.value = next;
}

function selectRoute() {
  if (selectedRouteId.value) emit("load", selectedRouteId.value);
}
</script>

<template>
  <section class="route-card">
    <div class="route-card__heading">
      <span class="icon"><Route :size="18" /></span>
      <div>
        <h3>巡逻路线</h3>
        <p>按列表从上到下执行；使用上移、下移调整巡逻顺序，路线状态由后端统一管理。</p>
      </div>
      <span class="count">{{ routes.length }} 条</span>
    </div>

    <label v-if="routes.length" class="field">
      <span>已有路线</span>
      <div class="inline">
        <select v-model="selectedRouteId" :disabled="busy">
          <option value="">选择路线</option>
          <option v-for="route in routes" :key="route.route_id" :value="route.route_id">
            {{ route.name }} · {{ route.status }}
          </option>
        </select>
        <button type="button" :disabled="busy || !selectedRouteId" @click="selectRoute">载入</button>
      </div>
    </label>

    <label class="field">
      <span>路线名称</span>
      <input v-model="name" maxlength="160" :disabled="busy" />
    </label>

    <div class="field">
      <span>添加有效点位</span>
      <div class="inline">
        <select v-model="selectedPointId" :disabled="busy || !activeMap">
          <option value="">选择点位</option>
          <option
            v-for="point in validPoints"
            :key="point.point_id"
            :value="point.point_id"
            :disabled="pointIds.includes(point.point_id)"
          >
            {{ point.name }} · {{ point.point_type }}
          </option>
        </select>
        <button type="button" :disabled="busy || !selectedPointId" @click="addPoint">
          <Plus :size="15" />添加
        </button>
      </div>
    </div>

    <ol v-if="pointIds.length" class="route-list">
      <li v-for="(pointId, index) in pointIds" :key="pointId">
        <span class="sequence">{{ index + 1 }}</span>
        <span class="route-name">{{ pointName(pointId) }}</span>
        <button type="button" title="上移" :disabled="busy || index === 0" @click="move(index, -1)">
          <ArrowUp :size="14" />
        </button>
        <button
          type="button"
          title="下移"
          :disabled="busy || index === pointIds.length - 1"
          @click="move(index, 1)"
        >
          <ArrowDown :size="14" />
        </button>
        <button type="button" title="移除" :disabled="busy" @click="removePoint(index)">
          <X :size="14" />
        </button>
      </li>
    </ol>
    <div v-else class="empty-route"><Flag :size="20" />至少添加一个有效巡逻点</div>

    <p class="validation" :class="{ 'validation--ok': validation.valid }">
      {{ validation.message }}
      <code v-if="validation.code">{{ validation.code }}</code>
    </p>

    <div class="actions">
      <button
        type="button"
        class="save"
        :disabled="busy || !activeMap || !name.trim() || !validation.valid"
        @click="emit('save', { name: name.trim(), pointIds })"
      >
        保存新路线
      </button>
      <button
        type="button"
        class="start"
        :disabled="busy || !selectedRoute || selectedRoute.route.status === 'invalid'"
        @click="selectedRoute && emit('start', selectedRoute.route.route_id)"
      >
        <Play :size="15" />启动 Mock 巡逻
      </button>
    </div>
  </section>
</template>

<style scoped>
.route-card { display: grid; gap: 15px; padding: 20px; border: 1px solid #dbe4ee; border-radius: 18px; background: #fff; }
.route-card__heading { display: grid; grid-template-columns: auto 1fr auto; gap: 11px; align-items: start; }
.icon { display: grid; width: 36px; height: 36px; place-items: center; border-radius: 10px; background: #eefbf3; color: #15803d; }
h3 { margin: 0 0 3px; color: #0f172a; font-size: .98rem; }
p { margin: 0; }
.route-card__heading p { color: #64748b; font-size: .76rem; line-height: 1.5; }
.count { padding: 5px 8px; border-radius: 999px; background: #f1f5f9; color: #475569; font-size: .68rem; font-weight: 800; }
.field { display: grid; gap: 6px; color: #475569; font-size: .75rem; font-weight: 700; }
input, select { box-sizing: border-box; width: 100%; min-width: 0; padding: 9px 10px; border: 1px solid #cbd5e1; border-radius: 9px; background: #fff; color: #0f172a; }
.inline { display: grid; grid-template-columns: 1fr auto; gap: 7px; }
button { display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-height: 36px; padding: 7px 11px; border: 1px solid #cbd5e1; border-radius: 9px; background: #fff; color: #334155; font-weight: 750; cursor: pointer; }
button:disabled { opacity: .45; cursor: not-allowed; }
.route-list { display: grid; gap: 7px; padding: 0; margin: 0; list-style: none; }
.route-list li { display: grid; grid-template-columns: auto 1fr auto auto auto; align-items: center; gap: 6px; padding: 7px; border: 1px solid #e2e8f0; border-radius: 10px; background: #f8fafc; }
.route-list button { min-height: 30px; padding: 5px 7px; }
.sequence { display: grid; width: 25px; height: 25px; place-items: center; border-radius: 50%; background: #dbeafe; color: #1d4ed8; font-size: .7rem; font-weight: 900; }
.route-name { overflow: hidden; color: #334155; font-size: .79rem; font-weight: 750; text-overflow: ellipsis; white-space: nowrap; }
.empty-route { display: flex; align-items: center; justify-content: center; gap: 8px; padding: 18px; border: 1px dashed #cbd5e1; border-radius: 10px; color: #64748b; font-size: .75rem; }
.validation { display: flex; flex-wrap: wrap; gap: 6px; color: #b45309; font-size: .72rem; line-height: 1.4; }
.validation--ok { color: #15803d; }
.validation code { padding: 1px 5px; border-radius: 4px; background: #f1f5f9; font-size: .65rem; }
.actions { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.actions .save { border-color: #2563eb; color: #1d4ed8; }
.actions .start { border-color: #166534; background: #166534; color: #fff; }
@media (max-width: 560px) { .actions { grid-template-columns: 1fr; } }
</style>
