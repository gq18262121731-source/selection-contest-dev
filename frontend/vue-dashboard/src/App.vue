<script setup lang="ts">
import { defineAsyncComponent, onMounted, onUnmounted, watch } from "vue";
import AppShell from "./components/layout/AppShell.vue";
import { useHashRouting } from "./composables/useHashRouting";
import { useSessionAuth } from "./composables/useSessionAuth";
import AccessDeniedPage from "./views/AccessDeniedPage.vue";
import CommunityAgentPage from "./views/CommunityAgentPage.vue";
import CommunityPage from "./views/CommunityPage.vue";
import DebugPage from "./views/DebugPage.vue";
import FamilyPage from "./views/FamilyPage.vue";
import LoginPage from "./views/LoginPage.vue";
import MemberDevicePage from "./views/MemberDevicePage.vue";
import RobotFollowPage from "./views/RobotFollowPage.vue";
import RobotStatusPage from "./views/RobotStatusPage.vue";
import RobotTaskCenterPage from "./views/RobotTaskCenterPage.vue";

const RobotNavigationPage = defineAsyncComponent(() => import("./views/RobotNavigationPage.vue"));
const RobotEmergencyPage = defineAsyncComponent(() => import("./views/RobotEmergencyPage.vue"));
const Go2CompanionPage = defineAsyncComponent(() => import("./views/Go2CompanionPage.vue"));

const {
  authError,
  authLoading,
  isLoggedIn,
  login,
  loginPassword,
  loginUsername,
  logoutSession,
  restoreSession,
  sessionUser,
} = useSessionAuth();

const {
  activePage,
  activeIncidentId,
  allowedPages,
  canAccessDebug,
  disposeHashRouting,
  initHashRouting,
  resetToDefaultPage,
  routeTo,
  routeToEmergency,
  routeToNonce,
} = useHashRouting(sessionUser);

async function submitLogin() {
  const user = await login();
  if (!user) return;

  if (user.role === "family") {
    routeTo("family");
    return;
  }

  if (user.role === "community" || user.role === "admin") {
    routeTo("overview");
    return;
  }

  resetToDefaultPage();
}

function applyRegistrationLoginPrefill(payload: { username: string; password: string }) {
  loginUsername.value = payload.username;
  loginPassword.value = payload.password;
  authError.value = "";
}

function logout() {
  sessionUser.value = null;
  logoutSession();
  resetToDefaultPage();
}

watch(canAccessDebug, (allowed) => {
  if (!allowed && activePage.value === "debug") {
    const fallbackPage = allowedPages.value[0];
    if (fallbackPage && fallbackPage !== "none") {
      routeTo(fallbackPage);
      return;
    }
    resetToDefaultPage();
  }
});

onMounted(async () => {
  await restoreSession();
  initHashRouting();
});

onUnmounted(() => {
  disposeHashRouting();
});
</script>

<template>
  <LoginPage
    v-if="!isLoggedIn"
    :login-username="loginUsername"
    :login-password="loginPassword"
    :auth-loading="authLoading"
    :auth-error="authError"
    @update:login-username="loginUsername = $event"
    @update:login-password="loginPassword = $event"
    @submit-login="submitLogin"
    @prefill-login="applyRegistrationLoginPrefill"
  />

  <AppShell
    v-else-if="sessionUser"
    :session-user="sessionUser"
    :active-page="activePage === 'report' ? 'agent' : activePage"
    :allowed-pages="allowedPages"
    :can-access-debug="canAccessDebug"
    @logout="logout"
    @navigate="routeTo"
    @open-emergency="routeToEmergency"
  >
    <DebugPage
      v-if="activePage === 'debug'"
      :can-go-community="allowedPages.includes('overview')"
      @navigate="routeTo"
    />

    <CommunityPage
      v-else-if="activePage === 'overview'"
      :session-user="sessionUser"
      :can-access-debug="canAccessDebug"
    />

    <CommunityAgentPage
      v-else-if="activePage === 'agent' || activePage === 'report'"
      :session-user="sessionUser"
      :initial-report-open="activePage === 'report'"
      :refresh-key="routeToNonce"
    />

    <FamilyPage
      v-else-if="activePage === 'family'"
      :session-user="sessionUser"
    />

    <MemberDevicePage
      v-else-if="activePage === 'members'"
      :session-user="sessionUser"
    />

    <Go2CompanionPage v-else-if="activePage === 'companion'" />

    <RobotTaskCenterPage v-else-if="activePage === 'robot-tasks'" />

    <RobotStatusPage v-else-if="activePage === 'robot-status'" />

    <RobotNavigationPage v-else-if="activePage === 'robot-navigation'" />

    <RobotEmergencyPage
      v-else-if="activePage === 'robot-emergency'"
      :key="activeIncidentId ?? 'invalid'"
      :incident-id="activeIncidentId"
      :session-user="sessionUser"
    />

    <RobotFollowPage v-else-if="activePage === 'robot-follow'" />

    <AccessDeniedPage v-else />
  </AppShell>
</template>
