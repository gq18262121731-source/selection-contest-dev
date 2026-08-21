<script setup lang="ts">
import { ChevronLeft } from "lucide-vue-next";
import familyImage from "../../../assets/家人.png";
import communityImage from "../../../assets/社区.png";
import elderImage from "../../../assets/老人.png";
import type { AuthFlowRole, RegisterFlowForm } from "../../../composables/useAuthFlow";
import RoleSelectCard from "../../../components/auth/RoleSelectCard.vue";

defineProps<{
  form: RegisterFlowForm;
  roleOptions: ReadonlyArray<{
    key: AuthFlowRole;
    badge: string;
    label: string;
    description: string;
  }>;
}>();

const emit = defineEmits<{
  "update:form": [value: RegisterFlowForm];
  next: [];
  prev: [];
}>();

const roleImages: Record<AuthFlowRole, string> = {
  elder: elderImage,
  family: familyImage,
  community: communityImage,
};

function updateRole(form: RegisterFlowForm, role: AuthFlowRole) {
  emit("update:form", {
    ...form,
    role,
    loginUsername: role === "elder" ? form.phone || form.loginUsername : form.loginUsername,
  });
  emit("next");
}

function roleLabel(role: AuthFlowRole, fallback: string) {
  return role === "community" ? "社区端" : fallback;
}
</script>

<template>
  <div class="auth-step-page auth-step-page--identity">
    <header class="register-identity-header">
      <button
        type="button"
        class="register-identity-header__back"
        aria-label="返回登录"
        @click="emit('prev')"
      >
        <ChevronLeft :size="18" />
      </button>
      <h2>请选择您的角色</h2>
      <span class="register-identity-header__spacer" aria-hidden="true"></span>
    </header>

    <div class="register-identity-grid">
      <RoleSelectCard
        v-for="item in roleOptions"
        :key="item.key"
        :label="roleLabel(item.key, item.label)"
        :active="form.role === item.key"
        @select="updateRole(form, item.key)"
      >
        <template #icon>
          <img
            class="auth-role-select-card__image"
            :src="roleImages[item.key]"
            :alt="roleLabel(item.key, item.label)"
          />
        </template>
      </RoleSelectCard>
    </div>
  </div>
</template>
