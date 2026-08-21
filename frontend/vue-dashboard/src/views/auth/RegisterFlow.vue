<script setup lang="ts">
import { computed, ref } from "vue";
import { ApiError, api } from "../../api/client";
import {
  authRoleOptions,
  createRegisterFlowForm,
  type AuthCompletedCredentials,
  type RegisterFlowForm,
} from "../../composables/useAuthFlow";
import RegisterAccountStep from "./register-flow/RegisterAccountStep.vue";
import RegisterIdentityStep from "./register-flow/RegisterIdentityStep.vue";
import RegisterProfileStep from "./register-flow/RegisterProfileStep.vue";
import RegisterSuccessStep from "./register-flow/RegisterSuccessStep.vue";
import StepIndicator, { type RegisterFlowStep } from "./register-flow/StepIndicator.vue";

const emit = defineEmits<{
  cancel: [];
  complete: [payload: AuthCompletedCredentials];
}>();

const currentStep = ref<RegisterFlowStep>("identity");
const form = ref<RegisterFlowForm>(createRegisterFlowForm());
const submitting = ref(false);
const errorText = ref("");
const successText = ref("");
const completedCredentials = ref<AuthCompletedCredentials | null>(null);

const currentComponent = computed(() => {
  switch (currentStep.value) {
    case "identity":
      return RegisterIdentityStep;
    case "account":
      return RegisterAccountStep;
    case "profile":
      return RegisterProfileStep;
    default:
      return RegisterSuccessStep;
  }
});

const currentComponentProps = computed(() => {
  if (currentStep.value === "identity") {
    return {
      form: form.value,
      roleOptions: authRoleOptions,
    };
  }

  if (currentStep.value === "account") {
    return {
      form: form.value,
    };
  }

  if (currentStep.value === "profile") {
    return {
      form: form.value,
      errorText: errorText.value,
      submitting: submitting.value,
    };
  }

  return {
    form: form.value,
    successText: successText.value,
    completedCredentials: completedCredentials.value,
    summary: registerSummary.value,
  };
});

const registerSummary = computed(() => {
  if (form.value.role === "elder") {
    return [
      `老人姓名：${form.value.name || "未填写"}`,
      `房间号：${form.value.apartment || "未填写"}`,
    ];
  }
  if (form.value.role === "family") {
    return [
      `家属姓名：${form.value.name || "未填写"}`,
      `关系：${form.value.relationship || "未填写"}`,
    ];
  }
  return [
    `社区人员：${form.value.name || "未填写"}`,
    `联系电话：${form.value.phone || "未填写"}`,
  ];
});

function formatError(error: unknown, fallback: string) {
  if (error instanceof ApiError && error.detail) {
    if (error.status === 404) {
      return "当前环境未启用正式注册接口，请确认后端服务是否已正常启动。";
    }
    return error.detail;
  }
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

function handleNext() {
  errorText.value = "";

  if (currentStep.value === "identity") {
    currentStep.value = "account";
    return;
  }

  if (currentStep.value === "account") {
    currentStep.value = "profile";
  }
}

function handlePrev() {
  errorText.value = "";

  if (currentStep.value === "identity") {
    emit("cancel");
    return;
  }

  if (currentStep.value === "account") {
    currentStep.value = "identity";
    return;
  }

  if (currentStep.value === "profile") {
    currentStep.value = "account";
    return;
  }

  currentStep.value = "profile";
}

async function submitRegistration() {
  errorText.value = "";
  submitting.value = true;

  try {
    if (form.value.role === "elder") {
      await api.publicRegisterElder({
        name: form.value.name.trim(),
        phone: form.value.loginUsername.trim(),
        password: form.value.password,
        age: Number(form.value.age) || 78,
        apartment: form.value.apartment.trim(),
        community_id: "community-haitang",
      });
    } else if (form.value.role === "family") {
      await api.publicRegisterFamily({
        name: form.value.name.trim(),
        phone: form.value.phone.trim(),
        password: form.value.password,
        relationship: form.value.relationship,
        community_id: "community-haitang",
        login_username: form.value.loginUsername.trim(),
      });
    } else {
      await api.publicRegisterCommunityStaff({
        name: form.value.name.trim(),
        phone: form.value.phone.trim(),
        password: form.value.password,
        community_id: "community-haitang",
        login_username: form.value.loginUsername.trim(),
      });
    }

    completedCredentials.value = {
      username: form.value.loginUsername.trim(),
      password: form.value.password,
      role: form.value.role,
    };
    successText.value = "注册成功，账号已经准备好，可以直接进入系统。";
    currentStep.value = "success";
  } catch (error) {
    errorText.value = formatError(error, "注册失败，请稍后重试。");
  } finally {
    submitting.value = false;
  }
}

function handleSubmit() {
  if (currentStep.value === "success") {
    if (completedCredentials.value) {
      emit("complete", completedCredentials.value);
    }
    return;
  }

  void submitRegistration();
}

function updateForm(value: RegisterFlowForm) {
  form.value = value;
  errorText.value = "";
}
</script>

<template>
  <div class="register-flow">
    <StepIndicator :current-step="currentStep" />

    <transition name="card-slide" mode="out-in">
      <component
        :is="currentComponent"
        :key="currentStep"
        v-bind="currentComponentProps"
        @update:form="updateForm"
        @next="handleNext"
        @prev="handlePrev"
        @submit="handleSubmit"
      />
    </transition>
  </div>
</template>
