<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { Crosshair, LocateFixed, Minus, Plus } from "lucide-vue-next";
import type {
  RobotMap,
  RobotMapPoint,
  RobotNavigationState,
  RobotPatrolRoutePoint,
} from "../../types/robot";
import {
  clampRobotMapZoom,
  DEFAULT_ROBOT_MAP_VIEWPORT,
  robotMapScreenToWorld,
  worldToRobotMapScreen,
} from "../../utils/robotMapCoordinates";

const props = defineProps<{
  map: RobotMap | null;
  points: RobotMapPoint[];
  state: RobotNavigationState | null;
  routePoints?: RobotPatrolRoutePoint[];
  editMode: boolean;
}>();

const emit = defineEmits<{
  "map-click": [point: { x: number; y: number }];
  "select-point": [point: RobotMapPoint];
  "cancel-edit": [];
}>();

const svg = ref<SVGSVGElement | null>(null);
const viewport = reactive({ ...DEFAULT_ROBOT_MAP_VIEWPORT });
const pointerStart = reactive({ x: 0, y: 0, panX: 0, panY: 0 });
let pointerId: number | null = null;
let dragged = false;

const projectedPoints = computed(() => props.points.map((point) => ({
  point,
  screen: worldToRobotMapScreen(point, viewport),
})));

const routePolyline = computed(() => {
  if (!props.routePoints?.length) return "";
  const byId = new Map(props.points.map((point) => [point.point_id, point]));
  return [...props.routePoints]
    .sort((a, b) => a.sequence - b.sequence)
    .map((item) => byId.get(item.point_id))
    .filter((point): point is RobotMapPoint => Boolean(point))
    .map((point) => {
      const screen = worldToRobotMapScreen(point, viewport);
      return `${screen.x},${screen.y}`;
    })
    .join(" ");
});

const robotScreen = computed(() => {
  const pose = props.state?.current_pose;
  return pose ? worldToRobotMapScreen(pose, viewport) : null;
});

const targetScreen = computed(() => {
  const pose = props.state?.target_pose;
  return pose ? worldToRobotMapScreen(pose, viewport) : null;
});

function pointColor(point: RobotMapPoint) {
  if (point.status !== "valid") return "#94a3b8";
  if (point.point_type === "home") return "#16a34a";
  if (point.point_type === "observation") return "#d97706";
  return "#2563eb";
}

function clientPoint(event: PointerEvent | MouseEvent) {
  const bounds = svg.value?.getBoundingClientRect();
  if (!bounds) return null;
  return {
    x: ((event.clientX - bounds.left) / bounds.width) * viewport.width,
    y: ((event.clientY - bounds.top) / bounds.height) * viewport.height,
  };
}

function pointerDown(event: PointerEvent) {
  if (props.editMode || event.button !== 0) return;
  pointerId = event.pointerId;
  dragged = false;
  pointerStart.x = event.clientX;
  pointerStart.y = event.clientY;
  pointerStart.panX = viewport.panX;
  pointerStart.panY = viewport.panY;
  svg.value?.setPointerCapture(event.pointerId);
}

function pointerMove(event: PointerEvent) {
  if (pointerId !== event.pointerId) return;
  const dx = event.clientX - pointerStart.x;
  const dy = event.clientY - pointerStart.y;
  if (Math.abs(dx) + Math.abs(dy) > 4) dragged = true;
  viewport.panX = pointerStart.panX + dx;
  viewport.panY = pointerStart.panY + dy;
}

function pointerUp(event: PointerEvent) {
  if (pointerId !== event.pointerId) return;
  svg.value?.releasePointerCapture(event.pointerId);
  pointerId = null;
}

function clickMap(event: MouseEvent) {
  if (!props.editMode || dragged) return;
  const point = clientPoint(event);
  if (!point) return;
  const world = robotMapScreenToWorld(point, viewport);
  emit("map-click", {
    x: Number(world.x.toFixed(2)),
    y: Number(world.y.toFixed(2)),
  });
}

function zoomBy(delta: number) {
  viewport.zoom = clampRobotMapZoom(viewport.zoom + delta);
}

function wheel(event: WheelEvent) {
  event.preventDefault();
  zoomBy(event.deltaY < 0 ? 0.12 : -0.12);
}

function resetView() {
  viewport.zoom = 1;
  viewport.panX = 0;
  viewport.panY = 0;
}

function handleEscape(event: KeyboardEvent) {
  if (event.key === "Escape" && props.editMode) emit("cancel-edit");
}

onMounted(() => window.addEventListener("keydown", handleEscape));
onBeforeUnmount(() => window.removeEventListener("keydown", handleEscape));
</script>

<template>
  <section class="map-stage" :class="{ 'map-stage--editing': editMode }">
    <header class="map-stage__header">
      <div>
        <span class="eyebrow">二维 Mock 地图</span>
        <h2>{{ map?.name ?? "尚未激活地图" }}</h2>
        <p>{{ editMode ? "点击地图落点；按 Esc 取消编辑。" : "拖拽平移，滚轮缩放；点击点位可编辑。" }}</p>
      </div>
      <div class="map-stage__tools" aria-label="地图视图工具">
        <button type="button" title="缩小" @click="zoomBy(-0.2)"><Minus :size="16" /></button>
        <span>{{ Math.round(viewport.zoom * 100) }}%</span>
        <button type="button" title="放大" @click="zoomBy(0.2)"><Plus :size="16" /></button>
        <button type="button" title="复位视图" @click="resetView"><LocateFixed :size="16" /></button>
      </div>
    </header>

    <div class="map-stage__canvas">
      <svg
        ref="svg"
        class="map-stage__svg"
        :viewBox="`0 0 ${viewport.width} ${viewport.height}`"
        role="img"
        aria-label="Mock 建图与巡逻点位地图"
        @pointerdown="pointerDown"
        @pointermove="pointerMove"
        @pointerup="pointerUp"
        @pointercancel="pointerUp"
        @click="clickMap"
        @wheel="wheel"
      >
        <defs>
          <pattern id="minor-grid" width="36" height="36" patternUnits="userSpaceOnUse">
            <path d="M 36 0 L 0 0 0 36" fill="none" stroke="#dbe5ef" stroke-width="1" />
          </pattern>
          <pattern id="major-grid" width="180" height="180" patternUnits="userSpaceOnUse">
            <rect width="180" height="180" fill="url(#minor-grid)" />
            <path d="M 180 0 L 0 0 0 180" fill="none" stroke="#c8d5e3" stroke-width="1.4" />
          </pattern>
          <filter id="point-shadow" x="-50%" y="-50%" width="200%" height="200%">
            <feDropShadow dx="0" dy="3" stdDeviation="3" flood-color="#0f172a" flood-opacity=".18" />
          </filter>
        </defs>
        <rect width="900" height="560" fill="#f8fafc" />
        <rect width="900" height="560" fill="url(#major-grid)" />

        <g class="mock-walls" :transform="`translate(${viewport.panX} ${viewport.panY}) scale(${viewport.zoom})`">
          <path d="M105 90H355V200H480V90H790V455H610V330H420V455H105Z" />
          <path d="M355 90V155M610 330V250M235 455V385M480 90V155" />
        </g>

        <polyline
          v-if="routePolyline"
          :points="routePolyline"
          fill="none"
          stroke="#2563eb"
          stroke-width="5"
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-dasharray="10 9"
          opacity=".7"
        />

        <g
          v-for="{ point, screen } in projectedPoints"
          :key="point.point_id"
          class="map-point"
          :class="{ 'map-point--invalid': point.status !== 'valid' }"
          :transform="`translate(${screen.x} ${screen.y})`"
          role="button"
          tabindex="0"
          @click.stop="emit('select-point', point)"
          @keydown.enter.prevent="emit('select-point', point)"
        >
          <circle r="15" :fill="pointColor(point)" filter="url(#point-shadow)" />
          <circle r="6" fill="#fff" opacity=".92" />
          <text y="-23" text-anchor="middle">{{ point.name }}</text>
        </g>

        <g v-if="targetScreen" :transform="`translate(${targetScreen.x} ${targetScreen.y})`">
          <circle r="20" fill="none" stroke="#d97706" stroke-width="4" stroke-dasharray="5 4" />
          <circle r="4" fill="#d97706" />
        </g>

        <g
          v-if="robotScreen"
          class="robot-pose"
          :transform="`translate(${robotScreen.x} ${robotScreen.y}) rotate(${-(state?.current_pose?.yaw ?? 0) * 57.2958})`"
        >
          <path d="M20 0L-14 13L-7 0L-14-13Z" />
        </g>

      </svg>

      <div v-if="!map" class="map-stage__empty">
        <Crosshair :size="30" />
        <strong>先完成 Mock 建图并保存地图</strong>
        <span>没有激活地图时不会开放点位和巡逻操作。</span>
      </div>
    </div>

    <footer class="map-stage__legend">
      <span><i class="legend-dot legend-dot--home"></i>待命点</span>
      <span><i class="legend-dot legend-dot--observation"></i>观察点</span>
      <span><i class="legend-dot legend-dot--patrol"></i>巡逻点</span>
      <span><i class="legend-dot legend-dot--invalid"></i>已失效</span>
    </footer>
  </section>
</template>

<style scoped>
.map-stage {
  overflow: hidden;
  border: 1px solid #dbe4ee;
  border-radius: 20px;
  background: #fff;
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.05);
}

.map-stage--editing {
  border-color: #60a5fa;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.12);
}

.map-stage__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  padding: 20px 22px 16px;
  border-bottom: 1px solid #edf2f7;
}

.eyebrow {
  color: #2563eb;
  font-size: .72rem;
  font-weight: 800;
  letter-spacing: .12em;
  text-transform: uppercase;
}

h2 { margin: 5px 0 3px; color: #0f172a; font-size: 1.15rem; }
p { margin: 0; color: #64748b; font-size: .82rem; }

.map-stage__tools {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 4px;
  border: 1px solid #dbe4ee;
  border-radius: 12px;
  background: #f8fafc;
  color: #475569;
}

.map-stage__tools button {
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: inherit;
  cursor: pointer;
}

.map-stage__tools button:hover { background: #eaf1f8; color: #1d4ed8; }
.map-stage__tools span { min-width: 45px; text-align: center; font-size: .72rem; font-weight: 700; }

.map-stage__canvas { position: relative; min-height: 420px; background: #f8fafc; }
.map-stage__svg { display: block; width: 100%; min-height: 420px; touch-action: none; cursor: grab; }
.map-stage--editing .map-stage__svg { cursor: crosshair; }

.mock-walls {
  transform-origin: 450px 280px;
  fill: none;
  stroke: #73869a;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 11;
  opacity: .56;
  pointer-events: none;
}

.map-point { cursor: pointer; outline: none; }
.map-point text { fill: #334155; font-size: 12px; font-weight: 800; paint-order: stroke; stroke: #fff; stroke-width: 4px; }
.map-point:focus circle:first-child { stroke: #0f172a; stroke-width: 3; }
.map-point--invalid { opacity: .62; }
.robot-pose path { fill: #0f172a; stroke: #fff; stroke-width: 3; filter: drop-shadow(0 3px 3px rgba(15,23,42,.25)); }
.map-stage__empty {
  position: absolute;
  inset: 0;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 7px;
  background: rgba(248, 250, 252, .84);
  color: #64748b;
  text-align: center;
  backdrop-filter: blur(2px);
}
.map-stage__empty strong { color: #334155; }
.map-stage__empty span { font-size: .8rem; }

.map-stage__legend {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  padding: 12px 20px;
  border-top: 1px solid #edf2f7;
  color: #64748b;
  font-size: .74rem;
}
.map-stage__legend span { display: inline-flex; align-items: center; gap: 6px; }
.legend-dot { width: 8px; height: 8px; border-radius: 50%; }
.legend-dot--home { background: #16a34a; }
.legend-dot--observation { background: #d97706; }
.legend-dot--patrol { background: #2563eb; }
.legend-dot--invalid { background: #94a3b8; }

@media (max-width: 720px) {
  .map-stage__header { flex-direction: column; }
  .map-stage__canvas, .map-stage__svg { min-height: 360px; }
}
</style>
