<script setup lang="ts">
defineProps<{
  label: string;
  note?: string;
  error?: string;
}>();
</script>

<template>
  <label class="auth-form-field">
    <span class="auth-form-field-label">{{ label }}</span>
    <slot />
    <small v-if="note && !error" class="auth-form-field-note">{{ note }}</small>
    <small v-if="error" class="auth-form-field-error">{{ error }}</small>
  </label>
</template>
