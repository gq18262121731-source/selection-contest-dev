<script setup lang="ts">
defineProps<{
  eyebrow: string;
  title: string;
  description?: string;
  meta?: string[];
}>();
</script>

<template>
  <header class="modern-page-header">
    <div class="modern-page-header__main">
      <div class="modern-page-header__badge">
        <span class="modern-page-header__eyebrow">{{ eyebrow }}</span>
      </div>
      
      <div class="modern-page-header__content">
        <div class="modern-page-header__title-section">
          <h1 class="modern-page-header__title">{{ title }}</h1>
          <p v-if="description" class="modern-page-header__description">{{ description }}</p>
        </div>
        
        <div v-if="$slots.actions" class="modern-page-header__actions">
          <slot name="actions" />
        </div>
      </div>
      
      <div v-if="meta?.length" class="modern-page-header__meta">
        <span v-for="item in meta" :key="item" class="modern-page-header__meta-item">
          {{ item }}
        </span>
      </div>
    </div>
    
    <div v-if="$slots.extra" class="modern-page-header__extra">
      <slot name="extra" />
    </div>
  </header>
</template>

<style scoped>
.modern-page-header {
  background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
  border: 1px solid #e2e8f0;
  border-radius: 24px;
  padding: 28px 32px;
  box-shadow: 0 4px 16px rgba(15, 23, 42, 0.04);
  display: grid;
  gap: 20px;
}

.modern-page-header__main {
  display: grid;
  gap: 16px;
}

.modern-page-header__badge {
  display: inline-flex;
  align-items: center;
}

.modern-page-header__eyebrow {
  display: inline-flex;
  padding: 6px 14px;
  border-radius: 999px;
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
  border: 1px solid #bfdbfe;
  color: #1e40af;
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.modern-page-header__content {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 24px;
}

.modern-page-header__title-section {
  flex: 1;
  display: grid;
  gap: 8px;
}

.modern-page-header__title {
  margin: 0;
  font-size: clamp(1.75rem, 3vw, 2.25rem);
  font-weight: 800;
  color: #0f172a;
  letter-spacing: -0.03em;
  line-height: 1.2;
}

.modern-page-header__description {
  margin: 0;
  font-size: 0.95rem;
  color: #64748b;
  line-height: 1.7;
  max-width: 720px;
}

.modern-page-header__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

.modern-page-header__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.modern-page-header__meta-item {
  display: inline-flex;
  align-items: center;
  padding: 8px 14px;
  border-radius: 12px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  color: #475569;
  font-size: 0.85rem;
  font-weight: 600;
  box-shadow: 0 2px 4px rgba(15, 23, 42, 0.02);
}

.modern-page-header__extra {
  padding-top: 16px;
  border-top: 1px solid #e2e8f0;
}

@media (max-width: 960px) {
  .modern-page-header {
    padding: 20px 24px;
  }

  .modern-page-header__content {
    flex-direction: column;
    align-items: stretch;
  }

  .modern-page-header__actions {
    justify-content: flex-start;
  }
}

@media (max-width: 640px) {
  .modern-page-header {
    padding: 18px 20px;
  }

  .modern-page-header__title {
    font-size: 1.5rem;
  }
}
</style>
