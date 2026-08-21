<script setup lang="ts">
import { computed, toRef } from "vue";

import type { SessionUser } from "../api/client";
import CommunityHandoverReport from "../components/CommunityHandoverReport.vue";
import PageHeader from "../components/layout/PageHeader.vue";
import { useCommunityWorkspace } from "../composables/useCommunityWorkspace";

const props = defineProps<{
  sessionUser: SessionUser;
}>();

const workspace = useCommunityWorkspace(toRef(props, "sessionUser"));

const pageMeta = computed(() => [
  `社区 ${workspace.community.value?.name ?? "当前社区"}`,
  `设备 ${workspace.deviceStatuses.value.length}`,
  `告警 ${workspace.recentAlerts.value.length}`,
]);
</script>

<template>
  <section class="page-stack">
    <PageHeader
      eyebrow="社区运营报告"
      title="社区报告"
      description="集中查看社区健康运营交接报告，支持刷新、时间窗口切换与 PDF 导出。"
      :meta="pageMeta"
    />

    <p v-if="workspace.dashboardLoadError.value" class="feedback-banner feedback-error">
      {{ workspace.dashboardLoadError.value }}
    </p>

    <CommunityHandoverReport
      v-else
      :community-name="workspace.community.value?.name ?? '当前社区'"
      :device-macs="workspace.deviceStatuses.value.map((item) => item.device_mac)"
      :device-statuses="workspace.deviceStatuses.value"
      :recent-alerts="workspace.recentAlerts.value"
    />
  </section>
</template>
