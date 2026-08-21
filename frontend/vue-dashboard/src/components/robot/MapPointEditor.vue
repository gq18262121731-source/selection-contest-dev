<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { MapPin, Plus, Trash2, X } from "lucide-vue-next";
import type { RobotMap, RobotMapPoint, RobotMapPointType } from "../../types/robot";

const props = defineProps<{
  activeMap: RobotMap | null;
  points: RobotMapPoint[];
  draft: { x: number; y: number } | null;
  selectedPoint: RobotMapPoint | null;
  activeOperation: string | null;
}>();

const emit = defineEmits<{
  "begin-create": [];
  cancel: [];
  save: [payload: {
    pointId?: string;
    name: string;
    pointType: RobotMapPointType;
    x: number;
    y: number;
    yaw: number;
    areaId?: string;
  }];
  invalidate: [pointId: string];
}>();

const name = ref("");
const pointType = ref<RobotMapPointType>("patrol");
const yaw = ref(0);
const areaId = ref("");
const confirmInvalidation = ref(false);

const editing = computed(() => Boolean(props.draft || props.selectedPoint));
const coordinates = computed(() => props.draft ?? props.selectedPoint ?? null);
const busy = computed(() => Boolean(props.activeOperation));
const valid = computed(() => Boolean(
  props.activeMap
  && coordinates.value
  && name.value.trim()
  && Number.isFinite(Number(yaw.value)),
));

watch(
  () => props.selectedPoint,
  (point) => {
    if (!point) {
      if (props.draft) name.value = `巡逻点 ${props.points.filter((item) => item.status === "valid").length + 1}`;
      return;
    }
    name.value = point.name;
    pointType.value = point.point_type;
    yaw.value = point.yaw;
    areaId.value = typeof point.metadata.area_id === "string" ? point.metadata.area_id : "";
    confirmInvalidation.value = false;
  },
  { immediate: true },
);

watch(
  () => props.draft,
  (draft) => {
    if (!draft) return;
    name.value = `巡逻点 ${props.points.filter((item) => item.status === "valid").length + 1}`;
    pointType.value = "patrol";
    yaw.value = 0;
    areaId.value = "";
  },
);

function submit() {
  if (!valid.value || !coordinates.value) return;
  emit("save", {
    pointId: props.selectedPoint?.point_id,
    name: name.value.trim(),
    pointType: pointType.value,
    x: coordinates.value.x,
    y: coordinates.value.y,
    yaw: Number(yaw.value),
    areaId: pointType.value === "observation" ? areaId.value.trim() || undefined : undefined,
  });
}
</script>

<template>
  <section class="point-card">
    <div class="point-card__heading">
      <span class="icon"><MapPin :size="18" /></span>
      <div>
        <h3>地图点位</h3>
        <p>坐标来自二维模拟地图；观察点的 area_id 用于匹配摄像头上报区域，不包含机器人控制字段。</p>
      </div>
      <span class="count">{{ points.filter((item) => item.status === "valid").length }} 有效</span>
    </div>

    <button
      v-if="!editing"
      type="button"
      class="create-button"
      :disabled="!activeMap || busy"
      @click="emit('begin-create')"
    >
      <Plus :size="17" />在地图上添加点位
    </button>

    <form v-else class="point-form" @submit.prevent="submit">
      <div class="coordinates">
        <span>X <strong>{{ coordinates?.x.toFixed(2) }}</strong> m</span>
        <span>Y <strong>{{ coordinates?.y.toFixed(2) }}</strong> m</span>
      </div>
      <label>
        <span>点位名称</span>
        <input v-model="name" maxlength="160" />
      </label>
      <div class="field-grid">
        <label>
          <span>点位类型</span>
          <select v-model="pointType">
            <option value="home">待命点</option>
            <option value="observation">观察点</option>
            <option value="patrol">巡逻点</option>
          </select>
        </label>
        <label>
          <span>朝向 yaw（弧度）</span>
          <input v-model.number="yaw" type="number" min="-3.142" max="3.142" step="0.05" />
        </label>
      </div>
      <label v-if="pointType === 'observation'">
        <span>关联区域 area_id（可选）</span>
        <input v-model="areaId" placeholder="例如 elderly_activity_area" maxlength="160" />
      </label>
      <div class="actions">
        <button type="button" class="primary" :disabled="busy || !valid" @click="submit">保存点位</button>
        <button type="button" :disabled="busy" @click="emit('cancel')"><X :size="15" />取消</button>
      </div>
      <div v-if="selectedPoint && selectedPoint.status === 'valid'" class="danger-zone">
        <label>
          <input v-model="confirmInvalidation" type="checkbox" />
          确认将点位标记为失效；已有路线不会被前端自动改写。
        </label>
        <button
          type="button"
          class="danger"
          :disabled="busy || !confirmInvalidation"
          @click="emit('invalidate', selectedPoint.point_id)"
        >
          <Trash2 :size="15" />使点位失效
        </button>
      </div>
    </form>
  </section>
</template>

<style scoped>
.point-card { display: grid; gap: 15px; padding: 20px; border: 1px solid #dbe4ee; border-radius: 18px; background: #fff; }
.point-card__heading { display: grid; grid-template-columns: auto 1fr auto; gap: 11px; align-items: start; }
.icon { display: grid; width: 36px; height: 36px; place-items: center; border-radius: 10px; background: #fff7ed; color: #c2410c; }
h3 { margin: 0 0 3px; color: #0f172a; font-size: .98rem; }
p { margin: 0; color: #64748b; font-size: .76rem; line-height: 1.5; }
.count { padding: 5px 8px; border-radius: 999px; background: #f1f5f9; color: #475569; font-size: .68rem; font-weight: 800; }
.create-button, button { display: inline-flex; align-items: center; justify-content: center; gap: 7px; min-height: 38px; padding: 8px 12px; border: 1px solid #cbd5e1; border-radius: 10px; background: #fff; color: #334155; font-weight: 750; cursor: pointer; }
button:disabled { opacity: .45; cursor: not-allowed; }
.create-button { width: 100%; border-style: dashed; color: #1d4ed8; }
.point-form { display: grid; gap: 12px; }
.coordinates { display: flex; gap: 9px; }
.coordinates span { flex: 1; padding: 8px 10px; border-radius: 9px; background: #f1f5f9; color: #64748b; font-size: .72rem; }
.coordinates strong { color: #0f172a; }
label { display: grid; gap: 6px; color: #475569; font-size: .75rem; font-weight: 700; }
input, select { box-sizing: border-box; width: 100%; padding: 9px 10px; border: 1px solid #cbd5e1; border-radius: 9px; background: #fff; color: #0f172a; }
input:focus, select:focus { outline: 3px solid rgba(59,130,246,.13); border-color: #3b82f6; }
.field-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.actions { display: flex; gap: 8px; }
.actions button { flex: 1; }
.actions .primary { border-color: #2563eb; background: #2563eb; color: #fff; }
.danger-zone { display: grid; gap: 9px; padding-top: 12px; border-top: 1px solid #fee2e2; }
.danger-zone label { display: flex; align-items: flex-start; gap: 8px; color: #991b1b; line-height: 1.4; }
.danger-zone input { width: auto; margin-top: 2px; }
.danger { border-color: #fecaca; background: #fff7f7; color: #b91c1c; }
@media (max-width: 560px) { .field-grid { grid-template-columns: 1fr; } }
</style>
