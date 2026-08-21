<script setup lang="ts">
export type RegisterFlowStep = "identity" | "account" | "profile" | "success";

const props = defineProps<{
  currentStep: RegisterFlowStep;
}>();

const stepOrder: RegisterFlowStep[] = ["identity", "account", "profile", "success"];

const stepLabels: Record<RegisterFlowStep, string> = {
  identity: "身份",
  account: "账号",
  profile: "资料",
  success: "完成",
};

function isActive(step: RegisterFlowStep) {
  return step === props.currentStep;
}

function isCompleted(step: RegisterFlowStep) {
  return stepOrder.indexOf(step) < stepOrder.indexOf(props.currentStep);
}
</script>

<template>
  <div class="auth-progress-strip" aria-label="注册进度">
    <div
      v-for="step in stepOrder"
      :key="step"
      class="auth-progress-step"
      :class="{ active: isActive(step), completed: isCompleted(step) }"
      :aria-label="stepLabels[step]"
      :title="stepLabels[step]"
    >
      <span aria-hidden="true"></span>
    </div>
  </div>
</template>
