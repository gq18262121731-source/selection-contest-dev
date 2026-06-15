<script setup lang="ts">
import { User, Lock, Heart } from "lucide-vue-next";
import heartImage from "../../assets/爱心.png";

defineProps<{
  loginUsername: string;
  loginPassword: string;
  authLoading: boolean;
  authError: string;
}>();

const emit = defineEmits<{
  "update:loginUsername": [value: string];
  "update:loginPassword": [value: string];
  submit: [];
  openRegister: [];
}>();

function updateText(event: Event, field: "username" | "password") {
  const value = (event.target as HTMLInputElement).value;
  if (field === "username") {
    emit("update:loginUsername", value);
    return;
  }
  emit("update:loginPassword", value);
}
</script>

<template>
  <div class="modern-login-container">
    <!-- 品牌标识 -->
    <div class="modern-login-brand">
      <div class="modern-login-brand__icon">
        <Heart :size="32" :stroke-width="2" />
      </div>
      <h1 class="modern-login-brand__title">智慧养老健康监测平台</h1>
      <p class="modern-login-brand__subtitle">AI-Powered Health Monitoring System</p>
    </div>

    <!-- 登录表单 -->
    <form class="modern-login-form" @submit.prevent="emit('submit')">
      <div class="modern-login-header">
        <h2>欢迎回来</h2>
        <p>请登录您的账号以继续</p>
      </div>

      <!-- 错误提示 -->
      <div v-if="authError" class="modern-login-error">
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
          <path d="M10 6V10M10 14H10.01M19 10C19 14.9706 14.9706 19 10 19C5.02944 19 1 14.9706 1 10C1 5.02944 5.02944 1 10 1C14.9706 1 19 5.02944 19 10Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        <span>{{ authError }}</span>
      </div>

      <!-- 账号输入 -->
      <div class="modern-login-field">
        <label class="modern-login-label">账号</label>
        <div class="modern-login-input-wrapper">
          <div class="modern-login-input-icon">
            <User :size="20" />
          </div>
          <input
            data-testid="login-username"
            :value="loginUsername"
            type="text"
            class="modern-login-input"
            placeholder="请输入您的账号"
            autocomplete="username"
            :disabled="authLoading"
            @input="updateText($event, 'username')"
          />
        </div>
      </div>

      <!-- 密码输入 -->
      <div class="modern-login-field">
        <label class="modern-login-label">密码</label>
        <div class="modern-login-input-wrapper">
          <div class="modern-login-input-icon">
            <Lock :size="20" />
          </div>
          <input
            data-testid="login-password"
            :value="loginPassword"
            type="password"
            class="modern-login-input"
            placeholder="请输入您的密码"
            autocomplete="current-password"
            :disabled="authLoading"
            @input="updateText($event, 'password')"
          />
        </div>
      </div>

      <!-- 登录按钮 -->
      <button
        data-testid="login-submit"
        type="submit"
        class="modern-login-button"
        :disabled="authLoading || !loginUsername.trim() || !loginPassword.trim()"
      >
        <span v-if="authLoading" class="modern-login-spinner"></span>
        <span>{{ authLoading ? "登录中..." : "登录" }}</span>
      </button>

      <!-- 底部链接 -->
      <div class="modern-login-footer">
        <button type="button" class="modern-login-link modern-login-link--muted" disabled>
          忘记密码？
        </button>
        <button
          data-testid="open-registration"
          type="button"
          class="modern-login-link modern-login-link--primary"
          :disabled="authLoading"
          @click="emit('openRegister')"
        >
          注册新账号
        </button>
      </div>
    </form>
  </div>
</template>

<style scoped>
.modern-login-container {
  position: relative;
  z-index: 10;
  width: 100%;
  max-width: 440px;
  display: flex;
  flex-direction: column;
  gap: 32px;
  pointer-events: auto;
}

/* 品牌标识 */
.modern-login-brand {
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}

.modern-login-brand__icon {
  width: 64px;
  height: 64px;
  border-radius: 20px;
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  box-shadow: 0 8px 24px rgba(59, 130, 246, 0.3);
  margin-bottom: 8px;
}

.modern-login-brand__title {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  color: #ffffff;
  letter-spacing: -0.02em;
  text-shadow: 0 2px 12px rgba(0, 0, 0, 0.3);
}

.modern-login-brand__subtitle {
  margin: 0;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.75);
  font-weight: 500;
  letter-spacing: 0.5px;
}

/* 登录表单 */
.modern-login-form {
  background: rgba(255, 255, 255, 0.98);
  border-radius: 24px;
  padding: 40px 36px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.2);
}

.modern-login-header {
  margin-bottom: 32px;
  text-align: center;
}

.modern-login-header h2 {
  margin: 0 0 8px 0;
  font-size: 28px;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.02em;
}

.modern-login-header p {
  margin: 0;
  font-size: 14px;
  color: #64748b;
  font-weight: 500;
}

/* 错误提示 */
.modern-login-error {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 12px;
  color: #dc2626;
  font-size: 14px;
  font-weight: 500;
  margin-bottom: 24px;
}

.modern-login-error svg {
  flex-shrink: 0;
}

/* 表单字段 */
.modern-login-field {
  margin-bottom: 24px;
}

.modern-login-label {
  display: block;
  margin-bottom: 8px;
  font-size: 14px;
  font-weight: 600;
  color: #334155;
  letter-spacing: -0.01em;
}

.modern-login-input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}

.modern-login-input-icon {
  position: absolute;
  left: 16px;
  display: flex;
  align-items: center;
  color: #94a3b8;
  pointer-events: none;
  z-index: 1;
}

.modern-login-input {
  width: 100%;
  height: 52px;
  padding: 0 16px 0 48px;
  border: 2px solid #e2e8f0;
  border-radius: 12px;
  background: #ffffff;
  color: #0f172a;
  font-size: 15px;
  font-weight: 500;
  transition: all 200ms ease;
  outline: none;
}

.modern-login-input::placeholder {
  color: #cbd5e1;
  font-weight: 400;
}

.modern-login-input:hover {
  border-color: #cbd5e1;
}

.modern-login-input:focus {
  border-color: #3b82f6;
  box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.1);
}

.modern-login-input:focus + .modern-login-input-icon {
  color: #3b82f6;
}

.modern-login-input:disabled {
  background: #f8fafc;
  cursor: not-allowed;
  opacity: 0.6;
}

/* 登录按钮 */
.modern-login-button {
  width: 100%;
  height: 52px;
  margin-top: 8px;
  border: none;
  border-radius: 12px;
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  color: #ffffff;
  font-size: 16px;
  font-weight: 700;
  cursor: pointer;
  transition: all 200ms ease;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  box-shadow: 0 4px 16px rgba(59, 130, 246, 0.3);
}

.modern-login-button:hover:not(:disabled) {
  background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
  box-shadow: 0 6px 20px rgba(59, 130, 246, 0.4);
  transform: translateY(-1px);
}

.modern-login-button:active:not(:disabled) {
  transform: translateY(0);
}

.modern-login-button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  transform: none;
}

/* 加载动画 */
.modern-login-spinner {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #ffffff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 底部链接 */
.modern-login-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 24px;
  padding-top: 24px;
  border-top: 1px solid #e2e8f0;
}

.modern-login-link {
  border: none;
  background: none;
  padding: 0;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 200ms ease;
}

.modern-login-link--muted {
  color: #94a3b8;
}

.modern-login-link--muted:hover:not(:disabled) {
  color: #64748b;
}

.modern-login-link--primary {
  color: #3b82f6;
}

.modern-login-link--primary:hover:not(:disabled) {
  color: #2563eb;
  text-decoration: underline;
}

.modern-login-link:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 响应式设计 */
@media (max-width: 640px) {
  .modern-login-container {
    max-width: 100%;
    gap: 24px;
  }

  .modern-login-form {
    padding: 32px 24px;
  }

  .modern-login-brand__title {
    font-size: 20px;
  }

  .modern-login-header h2 {
    font-size: 24px;
  }
}
</style>
