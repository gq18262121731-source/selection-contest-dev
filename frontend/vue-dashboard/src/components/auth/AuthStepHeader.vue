<script setup lang="ts">
defineProps<{
  eyebrow: string;
  title: string;
  subtitle?: string;
  tag?: string;
  backLabel?: string;
}>();

const emit = defineEmits<{
  back: [];
}>();
</script>

<template>
  <header class="auth-step-header">
    <div>
      <p class="section-eyebrow">{{ eyebrow }}</p>
      <h2>{{ title }}</h2>
      <p v-if="subtitle" class="subtle-copy">{{ subtitle }}</p>
    </div>
    <div class="auth-step-header-actions">
      <span v-if="tag" class="status-tag tone-stable">{{ tag }}</span>
      <button v-if="backLabel" type="button" class="ghost-btn" @click="emit('back')">{{ backLabel }}</button>
    </div>
  </header>
</template>
