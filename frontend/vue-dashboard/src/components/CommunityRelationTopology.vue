<script setup lang="ts">
import { computed } from "vue";
import type { CommunityRelationTopology } from "../api/client";

const props = defineProps<{
  topology: CommunityRelationTopology | null;
  selectedDeviceMac: string;
}>();

const emit = defineEmits<{
  (event: "select-device", mac: string): void;
}>();

const lanes = computed(() => props.topology?.lanes ?? []);
const unassignedDevices = computed(() => props.topology?.unassigned_devices ?? []);

function isSelectedDevice(id: string) {
  return id === props.selectedDeviceMac;
}
</script>

<template>
  <section class="panel topology-panel">
    <div class="topology-head">
      <div>
        <p class="section-eyebrow">社交关系图谱</p>
        <h2>社区关系拓扑</h2>
        <p class="topology-subtitle">理清社区、老人、家属和手环之间的归属关系，并突出当前选中的实时监护设备。</p>
      </div>
      <div v-if="topology" class="topology-community">
        <span>Community Hub</span>
        <strong>{{ topology.community.label }}</strong>
        <small>{{ topology.community.subtitle }}</small>
      </div>
    </div>

    <div v-if="!lanes.length" class="topology-empty">
      当前还没有可展示的拓扑关系。请先注册老人、家属并完成设备绑定。
    </div>

    <div v-else class="lane-list">
      <article v-for="lane in lanes" :key="lane.elder.id" class="topology-lane">
        <div class="lane-column lane-families">
          <span class="lane-label">家属</span>
          <button
            v-for="family in lane.families"
            :key="family.id"
            type="button"
            class="node-chip node-chip--family"
          >
            <strong>{{ family.label }}</strong>
            <small>{{ family.subtitle }}</small>
          </button>
          <div v-if="!lane.families.length" class="node-chip node-chip--ghost">
            <strong>暂无家属</strong>
            <small>待建立关系</small>
          </div>
        </div>

        <div class="lane-column lane-elder">
          <span class="lane-label">老人</span>
          <div class="node-core" :data-risk="lane.elder.risk_level ?? 'low'">
            <strong>{{ lane.elder.label }}</strong>
            <small>{{ lane.elder.subtitle }}</small>
            <em>{{ lane.elder.status }}</em>
          </div>
        </div>

        <div class="lane-column lane-devices">
          <span class="lane-label">设备</span>
          <button
            v-for="device in lane.devices"
            :key="device.id"
            type="button"
            class="node-chip node-chip--device"
            :class="{ 'node-chip--selected': isSelectedDevice(device.id) }"
            :data-risk="device.risk_level ?? 'low'"
            @click="emit('select-device', device.id)"
          >
            <strong>{{ device.label }}</strong>
            <small>{{ device.subtitle }}</small>
            <em>{{ device.status }}</em>
          </button>
          <div v-if="!lane.devices.length" class="node-chip node-chip--ghost">
            <strong>暂无设备</strong>
            <small>待绑定手环</small>
          </div>
        </div>
      </article>
    </div>

    <div v-if="unassignedDevices.length" class="orphan-strip">
      <span class="lane-label">未归属设备</span>
      <div class="orphan-row">
        <button
          v-for="device in unassignedDevices"
          :key="device.id"
          type="button"
          class="node-chip node-chip--device"
          :class="{ 'node-chip--selected': isSelectedDevice(device.id) }"
          @click="emit('select-device', device.id)"
        >
          <strong>{{ device.label }}</strong>
          <small>{{ device.subtitle }}</small>
          <em>{{ device.status }}</em>
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.topology-panel {
  display: grid;
  gap: 28px;
  background: #ffffff;
  padding: 28px;
  border-radius: 20px;
  box-shadow: 0 2px 12px rgba(15, 23, 42, 0.04);
  border: 2px solid #e2e8f0;
  width: 100%;
  max-width: 100%;
  position: relative;
  overflow-x: hidden;
}

.topology-head,
.lane-list,
.orphan-row {
  display: grid;
  gap: 24px;
  max-width: 100%;
}

.topology-head {
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: start;
  padding-bottom: 24px;
  border-bottom: 2px solid #e2e8f0;
}

.topology-head h2 {
  margin: 0;
  font-family: var(--font-display);
  color: #0f172a;
  font-size: 1.5rem;
  font-weight: 700;
}

.topology-subtitle {
  margin: 12px 0 0;
  color: #64748b;
  line-height: 1.7;
  font-size: 0.95rem;
}

.topology-community {
  display: grid;
  gap: 6px;
  padding: 18px 20px;
  min-width: 200px;
  border-radius: 16px;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  color: #0f172a;
  border: 2px solid #cbd5e1;
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.06);
}

.topology-community span,
.lane-label {
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: #64748b;
  font-weight: 600;
}

.topology-community span {
  color: #64748b;
}

.topology-community strong {
  font-size: 1.15rem;
  color: #1e40af;
  font-weight: 700;
}

.topology-community small {
  color: #64748b;
  font-size: 0.85rem;
}

.lane-list {
  gap: 28px;
}

.topology-lane {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1.2fr);
  gap: 24px;
  align-items: center;
  padding: 24px;
  border-radius: 20px;
  background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
  border: 2px solid #e2e8f0;
  box-shadow: 0 6px 20px rgba(15, 23, 42, 0.05);
  position: relative;
  max-width: 100%;
}

.topology-lane::before,
.topology-lane::after {
  content: "";
  position: absolute;
  top: 50%;
  height: 3px;
  background: linear-gradient(90deg, transparent 0%, #cbd5e1 50%, transparent 100%);
  transform: translateY(-50%);
}

.topology-lane::before {
  left: 32%;
  width: 12%;
}

.topology-lane::after {
  right: 32%;
  width: 12%;
}

.lane-column {
  display: grid;
  gap: 12px;
  min-width: 0;
}

.lane-families,
.lane-devices {
  align-content: start;
}

.lane-elder {
  justify-items: center;
}

.lane-label {
  margin-bottom: 4px;
}

.node-core,
.node-chip {
  border-radius: 16px;
  border: 2px solid #cbd5e1;
  background: #ffffff;
  padding: 16px 18px;
  display: grid;
  gap: 6px;
  text-align: left;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
  transition: all 200ms ease;
  position: relative;
  min-width: 0;
  word-wrap: break-word;
}

.node-core {
  min-width: 180px;
  justify-items: center;
  text-align: center;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border: 2px solid #94a3b8;
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08);
}

.node-core[data-risk="high"] {
  background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
  border-color: #f87171;
  box-shadow: 0 4px 16px rgba(239, 68, 68, 0.15);
}

.node-core[data-risk="medium"] {
  background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
  border-color: #fbbf24;
  box-shadow: 0 4px 16px rgba(245, 158, 11, 0.15);
}

.node-chip {
  cursor: default;
}

.node-chip--family {
  background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%);
  border-color: #7dd3fc;
}

.node-chip--device {
  cursor: pointer;
  background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
}

.node-chip--device:hover {
  transform: translateY(-2px);
  border-color: #3b82f6;
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
  box-shadow: 0 8px 20px rgba(37, 99, 235, 0.15);
}

.node-chip--selected {
  transform: translateY(-2px);
  border-color: #2563eb;
  background: linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%);
  box-shadow: 0 8px 24px rgba(37, 99, 235, 0.25);
}

.node-chip--device[data-risk="high"] {
  border-color: #fca5a5;
}

.node-chip--device[data-risk="medium"] {
  border-color: #fcd34d;
}

.node-chip strong,
.node-core strong {
  color: #0f172a;
  font-size: 1rem;
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
}

.node-chip small,
.node-core small {
  color: #64748b;
  font-style: normal;
  font-size: 0.85rem;
  overflow: hidden;
  text-overflow: ellipsis;
}

.node-chip em,
.node-core em {
  color: #94a3b8;
  font-style: normal;
  font-size: 0.8rem;
  overflow: hidden;
  text-overflow: ellipsis;
}

.node-chip--ghost {
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border-style: dashed;
  border-color: #cbd5e1;
}

.orphan-strip {
  display: grid;
  gap: 18px;
  padding-top: 24px;
  margin-top: 24px;
  border-top: 2px solid #cbd5e1;
  max-width: 100%;
}

.orphan-row {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  max-width: 100%;
}

.topology-empty {
  padding: 40px;
  border-radius: 20px;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border: 2px dashed #cbd5e1;
  color: #64748b;
  text-align: center;
  font-size: 1.05rem;
}

@media (max-width: 1200px) {
  .topology-panel {
    padding: 20px;
  }

  .topology-lane {
    grid-template-columns: 1fr;
    gap: 20px;
    padding: 20px;
  }

  .topology-lane::before,
  .topology-lane::after {
    display: none;
  }

  .lane-elder {
    justify-items: stretch;
  }

  .node-core {
    min-width: 0;
  }
}
</style>
