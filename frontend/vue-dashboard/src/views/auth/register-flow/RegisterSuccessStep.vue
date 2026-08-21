<script setup lang="ts">
import type { AuthCompletedCredentials, RegisterFlowForm } from "../../../composables/useAuthFlow";

defineProps<{
  form: RegisterFlowForm;
  successText: string;
  completedCredentials: AuthCompletedCredentials | null;
  summary: string[];
}>();

const emit = defineEmits<{
  prev: [];
  submit: [];
}>();
</script>

<template>
  <div class="auth-step-page auth-step-page--complete">
    <div class="auth-complete-simple">
      <span class="auth-complete-mark">OK</span>
      <div class="auth-complete-simple__copy">
        <p class="section-eyebrow">注册成功</p>
        <h2>账号已经准备好了</h2>
        <p class="subtle-copy">{{ successText }}</p>
        <div class="auth-complete-account">
          <span>登录账号</span>
          <strong>{{ completedCredentials?.username || form.loginUsername }}</strong>
        </div>
        <ul class="list-copy compact auth-complete-list">
          <li v-for="item in summary" :key="item">{{ item }}</li>
        </ul>
      </div>
    </div>

    <div class="auth-step-actions">
      <button type="button" class="ghost-btn" @click="emit('prev')">上一步</button>
      <button type="button" class="primary-btn" @click="emit('submit')">进入系统</button>
    </div>
  </div>
</template>
