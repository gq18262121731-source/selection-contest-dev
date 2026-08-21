<script setup lang="ts">
defineProps<{
  label: string;
  active?: boolean;
}>();

const emit = defineEmits<{
  select: [];
}>();
</script>

<template>
  <button
    type="button"
    class="register-role-card auth-role-select-card"
    :class="{ active }"
    @click="emit('select')"
  >
    <div v-if="$slots.icon" class="auth-role-select-card__icon">
      <slot name="icon" />
    </div>
    <strong>{{ label }}</strong>
  </button>
</template>
