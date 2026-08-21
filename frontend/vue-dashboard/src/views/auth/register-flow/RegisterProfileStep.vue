<script setup lang="ts">
import { ref } from "vue";
import type { RegisterFlowForm } from "../../../composables/useAuthFlow";
import AuthFormField from "../../../components/auth/AuthFormField.vue";
import AuthStepHeader from "../../../components/auth/AuthStepHeader.vue";

const props = defineProps<{
  form: RegisterFlowForm;
  submitting?: boolean;
  errorText?: string;
}>();

const emit = defineEmits<{
  "update:form": [value: RegisterFlowForm];
  prev: [];
  submit: [];
}>();

const localError = ref("");

function updateField(field: keyof RegisterFlowForm, value: string) {
  emit("update:form", {
    ...props.form,
    [field]: value,
  });
  localError.value = "";
}

function handleSubmit() {
  if (!props.form.name.trim()) {
    localError.value = "请填写姓名。";
    return;
  }

  if (props.form.role === "elder") {
    if (!props.form.age.trim()) {
      localError.value = "请填写年龄。";
      return;
    }
    if (!props.form.apartment.trim()) {
      localError.value = "请填写房间号。";
      return;
    }
    localError.value = "";
    emit("submit");
    return;
  }

  if (!props.form.phone.trim()) {
    localError.value = "请填写手机号。";
    return;
  }

  if (props.form.role === "family" && !props.form.relationship.trim()) {
    localError.value = "请填写家属关系。";
    return;
  }

  localError.value = "";
  emit("submit");
}
</script>

<template>
  <div class="auth-step-page auth-step-page--register">
    <AuthStepHeader
      eyebrow="Step 3"
      title="补充必要资料"
      subtitle="这里只保留当前注册接口真正需要的字段。"
      back-label="上一步"
      @back="emit('prev')"
    />

    <section class="auth-register-section">
      <div class="auth-form-grid auth-form-grid--two">
        <AuthFormField label="姓名">
          <input
            :value="form.name"
            class="text-input"
            type="text"
            placeholder="请输入姓名"
            @input="updateField('name', ($event.target as HTMLInputElement).value)"
          />
        </AuthFormField>

        <template v-if="form.role === 'elder'">
          <AuthFormField label="年龄">
            <input
              :value="form.age"
              class="text-input"
              type="number"
              min="1"
              placeholder="例如 78"
              @input="updateField('age', ($event.target as HTMLInputElement).value)"
            />
          </AuthFormField>
          <AuthFormField class="auth-form-span-2" label="房间号">
            <input
              :value="form.apartment"
              class="text-input"
              type="text"
              placeholder="例如 A-302"
              @input="updateField('apartment', ($event.target as HTMLInputElement).value)"
            />
          </AuthFormField>
        </template>

        <template v-else>
          <AuthFormField label="手机号">
            <input
              :value="form.phone"
              class="text-input"
              type="text"
              placeholder="请输入手机号"
              @input="updateField('phone', ($event.target as HTMLInputElement).value)"
            />
          </AuthFormField>

          <AuthFormField v-if="form.role === 'family'" label="关系">
            <select
              :value="form.relationship"
              class="inline-select relation-select"
              @change="updateField('relationship', ($event.target as HTMLSelectElement).value)"
            >
              <option value="daughter">女儿</option>
              <option value="son">儿子</option>
              <option value="spouse">配偶</option>
              <option value="granddaughter">孙女</option>
              <option value="grandson">孙子</option>
              <option value="relative">亲属</option>
            </select>
          </AuthFormField>
        </template>
      </div>
    </section>

    <p v-if="localError" class="feedback-banner feedback-error">{{ localError }}</p>
    <p v-else-if="errorText" class="feedback-banner feedback-error">{{ errorText }}</p>

    <div class="auth-step-actions">
      <button type="button" class="ghost-btn" :disabled="submitting" @click="emit('prev')">上一步</button>
      <button type="button" class="primary-btn" :disabled="submitting" @click="handleSubmit">
        {{ submitting ? "注册中..." : "完成注册" }}
      </button>
    </div>
  </div>
</template>
