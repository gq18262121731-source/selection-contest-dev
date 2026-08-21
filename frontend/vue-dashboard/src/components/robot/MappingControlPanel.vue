<script setup lang="ts">
import { computed, ref } from "vue";
import { Map, Save, ScanLine, Square } from "lucide-vue-next";
import type { RobotMap, RobotMappingState } from "../../types/robot";
import { robotMappingStateLabel } from "../../utils/robotPresentation";

const props = defineProps<{
  mappingState?: RobotMappingState;
  activeMap: RobotMap | null;
  activeOperation: string | null;
}>();

const emit = defineEmits<{
  start: [sessionName: string];
  stop: [];
  preview: [];
  save: [payload: { name: string; replaceConfirmed: boolean }];
}>();

const sessionName = ref("养老活动区模拟建图");
const mapName = ref("养老活动区演示地图");
const replaceConfirmed = ref(false);
const isBusy = computed(() => Boolean(props.activeOperation));
const isMapping = computed(() => props.mappingState === "mapping");
const canPreview = computed(() => props.mappingState === "preview_ready");
const canSave = computed(() => props.mappingState === "preview_ready" || props.mappingState === "saved");

function submitStart() {
  const value = sessionName.value.trim();
  if (value) emit("start", value);
}

function submitSave() {
  const value = mapName.value.trim();
  if (value) emit("save", { name: value, replaceConfirmed: replaceConfirmed.value });
}
</script>

<template>
  <section class="control-card">
    <div class="control-card__heading">
      <span class="control-card__icon"><ScanLine :size="18" /></span>
      <div>
        <h3>Mock 建图流程</h3>
        <p>只生成模拟地图数据，不启动雷达或 SLAM。</p>
      </div>
      <span class="state-pill">{{ robotMappingStateLabel(mappingState) }}</span>
    </div>

    <label class="field">
      <span>建图会话名称</span>
      <input v-model="sessionName" :disabled="isBusy || isMapping" maxlength="160" />
    </label>
    <p class="remote-guidance">
      请使用 Go2 遥控器手动带机器人完成场地扫描；本页面不提供任何方向控制。
    </p>

    <div class="button-row">
      <button
        type="button"
        class="button button--primary"
        :disabled="isBusy || isMapping"
        @click="submitStart"
      >
        <Map :size="16" />开始 Mock 建图
      </button>
      <button
        type="button"
        class="button"
        :disabled="isBusy || !isMapping"
        @click="emit('stop')"
      >
        <Square :size="14" />停止
      </button>
      <button
        type="button"
        class="button"
        :disabled="isBusy || !canPreview"
        @click="emit('preview')"
      >
        生成预览
      </button>
    </div>

    <div class="save-zone">
      <label class="field">
        <span>地图名称</span>
        <input v-model="mapName" :disabled="isBusy" maxlength="160" />
      </label>
      <label v-if="mappingState === 'preview_ready'" class="confirm-line">
        <input v-model="replaceConfirmed" type="checkbox" />
        <span v-if="activeMap">
          覆盖确认：将当前激活地图“{{ activeMap.name }}”替换为本次预览。保存后旧点位和路线将失效；
          本操作只影响 Mock 数据，仍需人工验收。
        </span>
        <span v-else>
          首次保存确认：将当前预览保存为激活模拟地图；此确认不代表真实建图或导航能力验收通过。
        </span>
      </label>
      <button
        type="button"
        class="button button--save"
        :disabled="isBusy || !canSave || (mappingState === 'preview_ready' && !replaceConfirmed)"
        @click="submitSave"
      >
        <Save :size="16" />保存并激活地图
      </button>
    </div>

    <p v-if="activeOperation" class="busy-copy">正在执行：{{ activeOperation }}，已锁定重复提交。</p>
  </section>
</template>

<style scoped>
.control-card {
  display: grid;
  gap: 16px;
  padding: 20px;
  border: 1px solid #dbe4ee;
  border-radius: 18px;
  background: #fff;
}

.control-card__heading {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: start;
  gap: 11px;
}

.control-card__icon {
  display: grid;
  width: 36px;
  height: 36px;
  place-items: center;
  border-radius: 10px;
  background: #eaf2ff;
  color: #2563eb;
}

h3 { margin: 0 0 3px; color: #0f172a; font-size: .98rem; }
p { margin: 0; color: #64748b; font-size: .77rem; line-height: 1.5; }
.state-pill { padding: 5px 8px; border-radius: 999px; background: #eff6ff; color: #1d4ed8; font-size: .68rem; font-weight: 800; }

.field { display: grid; gap: 6px; color: #475569; font-size: .76rem; font-weight: 700; }
.field input {
  width: 100%;
  box-sizing: border-box;
  padding: 10px 11px;
  border: 1px solid #cbd5e1;
  border-radius: 10px;
  color: #0f172a;
  background: #fff;
}
.field input:focus { outline: 3px solid rgba(59, 130, 246, .14); border-color: #3b82f6; }

.button-row { display: flex; flex-wrap: wrap; gap: 8px; }
.button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  min-height: 38px;
  padding: 8px 12px;
  border: 1px solid #cbd5e1;
  border-radius: 10px;
  background: #fff;
  color: #334155;
  font-weight: 750;
  cursor: pointer;
}
.button:hover:not(:disabled) { border-color: #94a3b8; background: #f8fafc; }
.button:disabled { cursor: not-allowed; opacity: .48; }
.button--primary { border-color: #2563eb; background: #2563eb; color: #fff; }
.button--primary:hover:not(:disabled) { background: #1d4ed8; }
.button--save { width: 100%; border-color: #166534; background: #f0fdf4; color: #166534; }

.save-zone { display: grid; gap: 11px; padding-top: 15px; border-top: 1px solid #edf2f7; }
.confirm-line { display: flex; gap: 8px; color: #92400e; font-size: .73rem; line-height: 1.45; }
.confirm-line input { margin-top: 2px; }
.busy-copy { color: #1d4ed8; font-weight: 700; }
.remote-guidance { padding: 9px 10px; border-radius: 9px; background: #f8fafc; color: #475569; }
</style>
