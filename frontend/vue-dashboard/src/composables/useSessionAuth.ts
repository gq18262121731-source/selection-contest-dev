import { computed, ref } from "vue";
import { ApiError, api, type SessionUser } from "../api/client";

export const SESSION_KEY = "ai_health_demo_session_token";

export function getStoredSessionToken() {
  return localStorage.getItem(SESSION_KEY) ?? "";
}

function formatAuthError(error: unknown, fallback: string) {
  if (error instanceof ApiError && error.detail) return error.detail;
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

export function useSessionAuth() {
  const sessionUser = ref<SessionUser | null>(null);
  const loginUsername = ref("");
  const loginPassword = ref("123456");
  const authLoading = ref(false);
  const authError = ref("");

  const isLoggedIn = computed(() => sessionUser.value !== null);

  async function login() {
    authError.value = "";

    if (!loginUsername.value.trim()) {
      authError.value = "请输入账号、登录名或手机号。";
      return null;
    }

    if (!loginPassword.value.trim()) {
      authError.value = "请输入密码。";
      return null;
    }

    authLoading.value = true;
    try {
      const result = await api.login({
        username: loginUsername.value.trim(),
        password: loginPassword.value,
      });
      sessionUser.value = result.user;
      localStorage.setItem(SESSION_KEY, result.token);
      return result.user;
    } catch (error) {
      authError.value = formatAuthError(error, "登录失败，请检查账号和密码。");
      return null;
    } finally {
      authLoading.value = false;
    }
  }

  async function restoreSession() {
    const token = getStoredSessionToken();
    if (!token) return;

    const user = await api.me(token).catch(() => null);
    if (!user) {
      localStorage.removeItem(SESSION_KEY);
      return;
    }

    sessionUser.value = user;
  }

  function logoutSession() {
    localStorage.removeItem(SESSION_KEY);
  }

  return {
    authError,
    authLoading,
    isLoggedIn,
    login,
    loginPassword,
    loginUsername,
    logoutSession,
    restoreSession,
    sessionUser,
  };
}
