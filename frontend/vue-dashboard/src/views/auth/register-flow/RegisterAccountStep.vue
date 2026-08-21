<script setup lang="ts">
import { computed, ref } from "vue";
import type { RegisterFlowForm } from "../../../composables/useAuthFlow";
import AuthFormField from "../../../components/auth/AuthFormField.vue";
import AuthStepHeader from "../../../components/auth/AuthStepHeader.vue";

const props = defineProps<{
  form: RegisterFlowForm;
}>();

const emit = defineEmits<{
  "update:form": [value: RegisterFlowForm];
  next: [];
  prev: [];
}>();

const localError = ref("");

const accountMeta = computed(() => {
  if (props.form.role === "elder") {
    return {
      label: "手机号（登录账号）",
      placeholder: "请输入手机号",
      note: "老人当前使用手机号作为登录账号。",
    };
  }
  if (props.form.role === "community") {
    return {
      label: "登录账号",
      placeholder: "设置值守账号",
      note: "后续使用该账号和密码登录控制台。",
    };
  }
  return {
    label: "登录账号",
    placeholder: "设置你的登录账号",
    note: "后续使用该账号和密码直接登录。",
  };
});

function updateField(field: keyof RegisterFlowForm, value: string) {
  emit("update:form", {
    ...props.form,
    [field]: value,
  });
  localError.value = "";
}

function handleNext() {
  if (!props.form.loginUsername.trim()) {
    localError.value = `请先填写${accountMeta.value.label}。`;
    return;
  }
  if (!props.form.password.trim()) {
    localError.value = "请输入密码。";
    return;
  }
  if (props.form.password !== props.form.confirmPassword) {
    localError.value = "两次输入的密码不一致。";
    return;
  }
  localError.value = "";
  emit("next");
}
</script>

<template>
  <div class="auth-step-page auth-step-page--register">
    <AuthStepHeader
      eyebrow="Step 2"
      title="设置账号与密码"
      subtitle="当前卡片只处理登录凭证，完成后再进入资料卡片。"
      back-label="上一步"
      @back="emit('prev')"
    />

    <section class="auth-register-section">
      <div class="auth-form-grid auth-form-grid--two">
        <AuthFormField class="auth-form-span-2" :label="accountMeta.label" :note="accountMeta.note">
          <input
            :value="form.loginUsername"
            class="text-input"
            type="text"
            :placeholder="accountMeta.placeholder"
            @input="updateField('loginUsername', ($event.target as HTMLInputElement).value)"
          />
        </AuthFormField>

        <AuthFormField label="密码">
          <input
            :value="form.password"
            class="text-input"
            type="password"
            placeholder="请输入密码"
            @input="updateField('password', ($event.target as HTMLInputElement).value)"
          />
        </AuthFormField>

        <AuthFormField label="确认密码">
          <input
            :value="form.confirmPassword"
            class="text-input"
            type="password"
            placeholder="请再次输入密码"
            @input="updateField('confirmPassword', ($event.target as HTMLInputElement).value)"
          />
        </AuthFormField>
      </div>
    </section>

    <p v-if="localError" class="feedback-banner feedback-error">{{ localError }}</p>

    <div class="auth-step-actions">
      <button type="button" class="ghost-btn" @click="emit('prev')">上一步</button>
      <button type="button" class="primary-btn" @click="handleNext">下一步</button>
    </div>
  </div>
</template>
