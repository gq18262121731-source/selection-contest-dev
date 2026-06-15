<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { Bug, ChevronDown, Wrench } from "lucide-vue-next";
import type { PageKey } from "../../composables/useHashRouting";

const props = defineProps<{
  activePage: PageKey;
  canAccessDebug: boolean;
}>();

const emit = defineEmits<{
  navigate: [page: PageKey];
}>();

const isOpen = ref(false);
const menuRef = ref<HTMLElement | null>(null);

const debugActive = computed(() => props.activePage === "debug");

function closeMenu() {
  isOpen.value = false;
}

function toggleMenu() {
  isOpen.value = !isOpen.value;
}

function handleDocumentClick(event: MouseEvent) {
  if (!menuRef.value) return;
  if (event.target instanceof Node && !menuRef.value.contains(event.target)) {
    closeMenu();
  }
}

function goToDebug() {
  emit("navigate", "debug");
  closeMenu();
}

onMounted(() => {
  document.addEventListener("click", handleDocumentClick);
});

onUnmounted(() => {
  document.removeEventListener("click", handleDocumentClick);
});
</script>

<template>
  <div v-if="canAccessDebug" ref="menuRef" class="modern-tool-entry">
    <button
      type="button"
      class="modern-tool-entry__trigger"
      :class="{ 'modern-tool-entry__trigger--active': isOpen || debugActive }"
      @click="toggleMenu"
    >
      <Wrench :size="16" />
      <span>工具入口</span>
      <ChevronDown :size="16" :class="{ 'rotate-180': isOpen }" />
    </button>

    <div v-if="isOpen" class="modern-tool-entry__panel">
      <button 
        type="button" 
        class="modern-tool-entry__item" 
        :class="{ 'modern-tool-entry__item--active': debugActive }" 
        @click="goToDebug"
      >
        <div class="modern-tool-entry__icon">
          <Bug :size="18" />
        </div>
        <div class="modern-tool-entry__content">
          <strong class="modern-tool-entry__title">调试看板</strong>
          <small class="modern-tool-entry__description">查看设备原始样本、实时字段与趋势调试信息</small>
        </div>
      </button>
    </div>
  </div>
</template>

<style scoped>
.modern-tool-entry {
  position: relative;
}

.modern-tool-entry__trigger {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 12px 16px;
  border: 2px solid #e2e8f0;
  border-radius: 14px;
  background: #ffffff;
  color: #1e40af;
  font-size: 0.9rem;
  font-weight: 700;
  cursor: pointer;
  transition: all 200ms ease;
}

.modern-tool-entry__trigger span {
  flex: 1;
  text-align: left;
}

.modern-tool-entry__trigger svg {
  transition: transform 200ms ease;
  flex-shrink: 0;
}

.modern-tool-entry__trigger .rotate-180 {
  transform: rotate(180deg);
}

.modern-tool-entry__trigger:hover {
  background: #eff6ff;
  border-color: #3b82f6;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.15);
}

.modern-tool-entry__trigger--active {
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
  border-color: #3b82f6;
  color: #1e40af;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.2);
}

.modern-tool-entry__panel {
  position: absolute;
  left: 0;
  right: 0;
  top: calc(100% + 8px);
  padding: 8px;
  border-radius: 16px;
  border: 1px solid #e2e8f0;
  background: #ffffff;
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.15);
  z-index: 1000;
  animation: slideDown 200ms ease;
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateY(-8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.modern-tool-entry__item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  width: 100%;
  padding: 14px 16px;
  border: 2px solid transparent;
  border-radius: 12px;
  background: #ffffff;
  text-align: left;
  cursor: pointer;
  transition: all 200ms ease;
}

.modern-tool-entry__item:hover {
  background: #f8fafc;
  border-color: #cbd5e1;
}

.modern-tool-entry__item--active {
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
  border-color: #3b82f6;
}

.modern-tool-entry__icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: #f1f5f9;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #64748b;
  flex-shrink: 0;
  transition: all 200ms ease;
}

.modern-tool-entry__item:hover .modern-tool-entry__icon {
  background: #e2e8f0;
  color: #475569;
}

.modern-tool-entry__item--active .modern-tool-entry__icon {
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  color: #ffffff;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
}

.modern-tool-entry__content {
  flex: 1;
  display: grid;
  gap: 4px;
  min-width: 0;
}

.modern-tool-entry__title {
  font-size: 0.95rem;
  font-weight: 700;
  color: #1e40af;
  letter-spacing: -0.01em;
}

.modern-tool-entry__description {
  font-size: 0.8rem;
  color: #64748b;
  line-height: 1.5;
}

.modern-tool-entry__item--active .modern-tool-entry__title {
  color: #1e40af;
}

.modern-tool-entry__item--active .modern-tool-entry__description {
  color: #3b82f6;
}
</style>
