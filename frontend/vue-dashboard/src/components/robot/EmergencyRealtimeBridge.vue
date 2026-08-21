<script setup lang="ts">
import { watch } from "vue";
import type { RobotContractError } from "../../api/robotContractPolicy";
import { useRobotWebSocket } from "../../composables/useRobotWebSocket";
import type { RobotConnectionState, RobotStatusEvent } from "../../types/robot";

const props = defineProps<{
  incidentId: string;
}>();

const emit = defineEmits<{
  snapshot: [event: RobotStatusEvent];
  event: [event: RobotStatusEvent];
  refresh: [];
  contractError: [error: RobotContractError];
  connection: [state: RobotConnectionState];
}>();

const { connectionState } = useRobotWebSocket({
  path: `/ws/robot/emergency/${encodeURIComponent(props.incidentId)}`,
  onSnapshot: (event) => emit("snapshot", event),
  onEvent: (event) => emit("event", event),
  refreshSnapshot: () => emit("refresh"),
  onContractError: (error) => emit("contractError", error),
});

watch(connectionState, (state) => emit("connection", state), { immediate: true });
</script>

<template>
  <span class="emergency-realtime-bridge" aria-hidden="true"></span>
</template>

<style scoped>
.emergency-realtime-bridge { display: none; }
</style>
