<script setup lang="ts">
import { Zap } from "lucide-vue-next";
import type { AuthAccountPreview } from "../../api/client";

defineProps<{
  accounts: AuthAccountPreview[];
  helperText: string;
  selectedAccount: string;
  disabled?: boolean;
}>();

const emit = defineEmits<{
  "update:selectedAccount": [value: string];
  fill: [];
}>();

function updateSelect(event: Event) {
  emit("update:selectedAccount", (event.target as HTMLSelectElement).value);
}
</script>

<template>
  <article class="modern-quick-login">
    <div class="modern-quick-login__header">
      <div class="modern-quick-login__icon">
        <Zap :size="18" />
      </div>
      <div class="modern-quick-login__title">
        <h3>快速演示</h3>
        <p>{{ helperText }}</p>
      </div>
    </div>
    
    <div class="modern-quick-login__content">
      <select 
        class="modern-quick-login__select" 
        :value="selectedAccount" 
        :disabled="disabled || !accounts.length" 
        @change="updateSelect"
      >
        <option v-for="account in accounts" :key="account.username" :value="account.username">
          {{ account.display_name }} ({{ account.role }})
        </option>
      </select>
      
      <button 
        type="button" 
        class="modern-quick-login__button" 
        :disabled="disabled || !accounts.length" 
        @click="emit('fill')"
      >
        <Zap :size="16" />
        一键填充
      </button>
    </div>
    
    <p class="modern-quick-login__hint">
      选择演示账号后点击"一键填充"即可快速登录体验系统
    </p>
  </article>
</template>

<style scoped>
.modern-quick-login {
  position: relative;
  z-index: 10;
  width: 440px;
  padding: 20px 24px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 16px;
  backdrop-filter: blur(20px);
  animation: fadeInUp 0.6s ease-out 0.2s both;
  pointer-events: auto;
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.modern-quick-login__header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 16px;
}

.modern-quick-login__icon {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: linear-gradient(135deg, rgba(245, 158, 11, 0.2), rgba(251, 191, 36, 0.2));
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fbbf24;
  flex-shrink: 0;
}

.modern-quick-login__title {
  flex: 1;
  min-width: 0;
}

.modern-quick-login__title h3 {
  margin: 0 0 4px 0;
  font-size: 16px;
  font-weight: 700;
  color: #ffffff;
  letter-spacing: -0.01em;
}

.modern-quick-login__title p {
  margin: 0;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.65);
  line-height: 1.5;
}

.modern-quick-login__content {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 12px;
}

.modern-quick-login__select {
  width: 100%;
  height: 44px;
  padding: 0 14px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.1);
  color: #ffffff;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 200ms ease;
  outline: none;
}

.modern-quick-login__select:hover:not(:disabled) {
  border-color: rgba(255, 255, 255, 0.25);
  background: rgba(255, 255, 255, 0.15);
}

.modern-quick-login__select:focus {
  border-color: #fbbf24;
  box-shadow: 0 0 0 3px rgba(251, 191, 36, 0.2);
}

.modern-quick-login__select:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.modern-quick-login__select option {
  background: #1e293b;
  color: #ffffff;
}

.modern-quick-login__button {
  width: 100%;
  height: 44px;
  padding: 0 20px;
  border: none;
  border-radius: 10px;
  background: linear-gradient(135deg, #f59e0b 0%, #fbbf24 100%);
  color: #0f172a;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  transition: all 200ms ease;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  box-shadow: 0 4px 12px rgba(245, 158, 11, 0.3);
}

.modern-quick-login__button:hover:not(:disabled) {
  background: linear-gradient(135deg, #fbbf24 0%, #fcd34d 100%);
  box-shadow: 0 6px 16px rgba(245, 158, 11, 0.4);
  transform: translateY(-1px);
}

.modern-quick-login__button:active:not(:disabled) {
  transform: translateY(0);
}

.modern-quick-login__button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}

.modern-quick-login__hint {
  margin: 0;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.5);
  line-height: 1.6;
}

/* 响应式 */
@media (max-width: 640px) {
  .modern-quick-login {
    width: 100%;
    max-width: 440px;
  }
}
</style>
