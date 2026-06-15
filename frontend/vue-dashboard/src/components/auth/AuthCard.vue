<script setup lang="ts">
defineProps<{
  variant?: "login" | "register" | "complete";
}>();
</script>

<template>
  <div class="modern-auth-card" :class="`modern-auth-card--${variant || 'login'}`">
    <slot />
  </div>
</template>

<style scoped>
.modern-auth-card {
  position: relative;
  width: 100%;
  max-width: 480px;
  animation: fadeInUp 0.6s ease-out;
}

.modern-auth-card--register {
  max-width: 680px;
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
