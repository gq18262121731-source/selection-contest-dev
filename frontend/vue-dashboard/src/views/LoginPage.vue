<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { ApiError, api, type AuthAccountPreview } from "../api/client";
import AuthCard from "../components/auth/AuthCard.vue";
import AuthShell from "../components/auth/AuthShell.vue";
import QuickLoginPanel from "../components/auth/QuickLoginPanel.vue";
import { useAuthFlow, type AuthCompletedCredentials, type AuthFlowRole } from "../composables/useAuthFlow";
import AuthLoginPage from "./auth/AuthLoginPage.vue";
import RegisterFlow from "./auth/RegisterFlow.vue";

const props = defineProps<{
  loginUsername: string;
  loginPassword: string;
  authLoading: boolean;
  authError: string;
}>();

const emit = defineEmits<{
  "update:loginUsername": [value: string];
  "update:loginPassword": [value: string];
  submitLogin: [];
  prefillLogin: [payload: { username: string; password: string; role: AuthFlowRole }];
}>();

const authFlow = useAuthFlow();
const quickAccounts = ref<AuthAccountPreview[]>([]);
const selectedAccount = ref("");
const quickLoginError = ref("");

const authCardVariant = computed(() => {
  return authFlow.currentStep.value === "register" ? "register" : "login";
});

const quickLoginHelperText = computed(() => {
  if (quickLoginError.value) return quickLoginError.value;
  if (!quickAccounts.value.length) return "当前没有可用的演示账号。";
  return "可直接选择演示账号并回填到登录表单，默认密码会同步写入。";
});

function handleRegistrationComplete(payload: AuthCompletedCredentials) {
  authFlow.goToLogin();
  emit("prefillLogin", payload);
}

function applyQuickAccount(username: string) {
  const account = quickAccounts.value.find((item) => item.username === username);
  if (!account) return;
  selectedAccount.value = account.username;
  emit("update:loginUsername", account.username);
  emit("update:loginPassword", account.default_password);
}

async function loadQuickAccounts() {
  try {
    quickLoginError.value = "";
    const accounts = await api.listMockAccounts();
    quickAccounts.value = accounts;
    if (!accounts.length) return;

    selectedAccount.value = props.loginUsername.trim() || accounts[0].username;
    if (!props.loginUsername.trim()) {
      applyQuickAccount(selectedAccount.value);
    }
  } catch (error) {
    quickAccounts.value = [];
    if (error instanceof ApiError && error.detail) {
      quickLoginError.value = error.detail;
      return;
    }
    quickLoginError.value = "演示账号加载失败，请稍后重试。";
  }
}

onMounted(() => {
  void loadQuickAccounts();
});
</script>

<template>
  <AuthShell>
    <div class="login-page-layout">
      <AuthCard :variant="authCardVariant">
        <AuthLoginPage
          v-if="authFlow.currentStep.value === 'login'"
          :login-username="loginUsername"
          :login-password="loginPassword"
          :auth-loading="authLoading"
          :auth-error="authError"
          @update:login-username="emit('update:loginUsername', $event)"
          @update:login-password="emit('update:loginPassword', $event)"
          @submit="emit('submitLogin')"
          @open-register="authFlow.openRegister()"
        />

        <RegisterFlow
          v-else-if="authFlow.currentStep.value === 'register'"
          @cancel="authFlow.goToLogin()"
          @complete="handleRegistrationComplete"
        />
      </AuthCard>

      <QuickLoginPanel
        v-if="authFlow.currentStep.value === 'login'"
        :accounts="quickAccounts"
        :helper-text="quickLoginHelperText"
        :selected-account="selectedAccount"
        :disabled="authLoading"
        @update:selected-account="selectedAccount = $event"
        @fill="applyQuickAccount(selectedAccount)"
      />
    </div>
  </AuthShell>
</template>

<style scoped>
.login-page-layout {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 24px;
  width: 100%;
}
</style>
