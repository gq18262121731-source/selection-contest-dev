<script setup lang="ts">
import type { CapabilityState } from "../../types/robot";

withDefaults(defineProps<{
  state?: CapabilityState | null;
}>(), {
  state: "not_verified",
});

const labels: Record<CapabilityState, string> = {
  mock: "模拟",
  unavailable: "不可用",
  not_verified: "未验证",
  blocked: "阻塞",
  ready: "正常",
};
</script>

<template>
  <span class="robot-capability-badge" :class="`robot-capability-badge--${state ?? 'not_verified'}`">
    {{ labels[state ?? "not_verified"] }}
  </span>
</template>

<style scoped>
.robot-capability-badge {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  min-height: 24px;
  padding: 3px 8px;
  border: 1px solid #cbd8e4;
  border-radius: 999px;
  background: #f4f7fa;
  color: #526b82;
  font-size: 0.68rem;
  font-weight: 780;
  line-height: 1;
}

.robot-capability-badge--mock {
  border-color: #bbd4ef;
  background: #eef6ff;
  color: #245d97;
}

.robot-capability-badge--ready {
  border-color: #a9ddca;
  background: #edf9f4;
  color: #087653;
}

.robot-capability-badge--blocked {
  border-color: #edca8f;
  background: #fff8e8;
  color: #8b5a0a;
}

.robot-capability-badge--unavailable {
  border-color: #efc1bc;
  background: #fff3f1;
  color: #a53630;
}
</style>
