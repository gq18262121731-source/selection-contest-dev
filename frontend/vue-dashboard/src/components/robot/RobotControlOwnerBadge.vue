<script setup lang="ts">
import { computed } from "vue";
import type { RobotControlOwner } from "../../types/robot";

const props = withDefaults(defineProps<{
  owner?: RobotControlOwner | null;
}>(), {
  owner: "NONE",
});

const label = computed(() => ({
  NONE: "无控制方",
  MANUAL: "人工接管",
  NAVIGATION: "Mock 导航",
  FOLLOW: "跟随模式",
  EMERGENCY_STOP: "急停锁定",
})[props.owner ?? "NONE"]);
</script>

<template>
  <span class="robot-owner-badge" :class="`robot-owner-badge--${(owner ?? 'NONE').toLowerCase()}`">
    {{ label }}
  </span>
</template>

<style scoped>
.robot-owner-badge {
  display: inline-flex;
  width: fit-content;
  padding: 5px 9px;
  border: 1px solid #cbd8e4;
  border-radius: 8px;
  background: #f4f7fa;
  color: #456178;
  font-size: 0.72rem;
  font-weight: 760;
}

.robot-owner-badge--navigation,
.robot-owner-badge--follow {
  border-color: #bbd4ef;
  background: #eef6ff;
  color: #245d97;
}

.robot-owner-badge--manual {
  border-color: #edca8f;
  background: #fff8e8;
  color: #8b5a0a;
}

.robot-owner-badge--emergency_stop {
  border-color: #efc1bc;
  background: #fff3f1;
  color: #a53630;
}
</style>
