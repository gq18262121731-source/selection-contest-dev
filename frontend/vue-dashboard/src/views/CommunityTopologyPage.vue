<script setup lang="ts">
import { computed, toRef } from "vue";

import type { SessionUser } from "../api/client";
import CommunityDeviceInspector from "../components/CommunityDeviceInspector.vue";
import CommunityDeviceRail from "../components/CommunityDeviceRail.vue";
import CommunityRelationTopology from "../components/CommunityRelationTopology.vue";
import PageHeader from "../components/layout/PageHeader.vue";
import { useCommunityWorkspace } from "../composables/useCommunityWorkspace";

const props = defineProps<{
  sessionUser: SessionUser;
}>();

const workspace = useCommunityWorkspace(toRef(props, "sessionUser"));

const pageMeta = computed(() => [
  `关系链 ${workspace.relationTopology.value?.lanes.length ?? 0}`,
  `未归属设备 ${workspace.relationTopology.value?.unassigned_devices.length ?? 0}`,
  `当前设备 ${workspace.selectedDevice.value?.device_mac ?? "无"}`,
]);
</script>

<template>
  <section class="topology-page-container">
    <PageHeader
      eyebrow="Topology"
      title="设备拓扑"
      description="从老人、家属和设备关系中查看当前归属。这里同样按老人卡片选中对象，再联动右侧拓扑与绑定详情。"
      :meta="pageMeta"
    />

    <CommunityDeviceRail
      :elders="workspace.topRiskElders.value"
      :selected-elder-id="workspace.selectedElderId.value"
      @select="workspace.setSelectedElderId"
    />

    <div class="topology-two-column-layout">
      <div class="topology-left-column">
        <CommunityRelationTopology
          :topology="workspace.relationTopology.value ?? null"
          :selected-device-mac="workspace.selectedDeviceMac.value"
          @select-device="workspace.setSelectedDeviceMac"
        />
      </div>
      <div class="topology-right-column">
        <CommunityDeviceInspector
          :elder="workspace.selectedElder.value"
          :device="workspace.selectedDevice.value"
        />
      </div>
    </div>
  </section>
</template>

<style scoped>
.topology-page-container {
  display: flex;
  flex-direction: column;
  gap: 24px;
  padding-bottom: 40px;
  width: 100%;
  max-width: 100%;
  overflow-x: hidden;
}

.topology-two-column-layout {
  display: flex;
  gap: 24px;
  width: 100%;
  max-width: 100%;
  align-items: flex-start;
}

.topology-left-column {
  flex: 1;
  min-width: 0;
  max-width: 100%;
}

.topology-right-column {
  width: 400px;
  flex-shrink: 0;
}

@media (max-width: 1400px) {
  .topology-right-column {
    width: 360px;
  }
}

@media (max-width: 1280px) {
  .topology-two-column-layout {
    flex-direction: column;
    gap: 24px;
  }
  
  .topology-right-column {
    width: 100%;
  }
}
</style>
