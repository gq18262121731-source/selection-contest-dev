<script setup lang="ts">
import { computed } from "vue";
import {
  Activity,
  Cpu,
  Network,
  SquareTerminal,
  type LucideIcon,
  UsersRound,
} from "lucide-vue-next";
import type { PageKey } from "../../composables/useHashRouting";

const props = defineProps<{
  activePage: PageKey;
  allowedPages: PageKey[];
}>();

const emit = defineEmits<{
  navigate: [page: PageKey];
}>();

type NavItem = {
  page: PageKey;
  label: string;
  description: string;
  icon: LucideIcon;
};

const navItems = computed<NavItem[]>(() =>
  ([
    {
      page: "overview" as PageKey,
      label: "总览监护",
      description: "实时曲线与告警",
      icon: Activity,
    },
    {
      page: "topology" as PageKey,
      label: "设备拓扑",
      description: "老人、家属与设备关系",
      icon: Network,
    },
    {
      page: "members" as PageKey,
      label: "成员设备",
      description: "注册、绑定与台账",
      icon: UsersRound,
    },
    {
      page: "agent" as PageKey,
      label: "智能体工作台",
      description: "问答、分析与工具",
      icon: SquareTerminal,
    },
    {
      page: "family" as PageKey,
      label: "家属视图",
      description: "家庭成员查看页面",
      icon: Cpu,
    },
  ] satisfies NavItem[]).filter((item) => props.allowedPages.includes(item.page)),
);
</script>

<template>
  <nav v-if="navItems.length" class="modern-primary-nav" aria-label="主导航">
    <div class="modern-primary-nav__header">
      <h3 class="modern-primary-nav__title">社区工作台</h3>
      <p class="modern-primary-nav__subtitle">监护、拓扑、成员设备等智能体分区协作</p>
    </div>
    
    <div class="modern-primary-nav__items">
      <button
        v-for="item in navItems"
        :key="item.page"
        type="button"
        class="modern-primary-nav__item"
        :class="{ 'modern-primary-nav__item--active': activePage === item.page }"
        @click="emit('navigate', item.page)"
      >
        <div class="modern-primary-nav__icon">
          <component :is="item.icon" :size="20" />
        </div>
        <div class="modern-primary-nav__content">
          <strong class="modern-primary-nav__label">{{ item.label }}</strong>
          <small class="modern-primary-nav__description">{{ item.description }}</small>
        </div>
        <div class="modern-primary-nav__indicator"></div>
      </button>
    </div>
  </nav>
</template>

<style scoped>
.modern-primary-nav {
  display: grid;
  gap: 20px;
  padding: 24px 20px;
  background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
  border: 1px solid #e2e8f0;
  border-radius: 24px;
  box-shadow: 0 4px 16px rgba(15, 23, 42, 0.04);
}

.modern-primary-nav__header {
  padding-bottom: 16px;
  border-bottom: 2px solid #e2e8f0;
}

.modern-primary-nav__title {
  margin: 0 0 6px 0;
  font-size: 1.25rem;
  font-weight: 800;
  color: #0f172a;
  letter-spacing: -0.02em;
}

.modern-primary-nav__subtitle {
  margin: 0;
  font-size: 0.82rem;
  color: #64748b;
  line-height: 1.6;
}

.modern-primary-nav__items {
  display: grid;
  gap: 8px;
}

.modern-primary-nav__item {
  position: relative;
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 14px;
  padding: 14px 16px;
  border: 2px solid transparent;
  border-radius: 16px;
  background: #ffffff;
  text-align: left;
  cursor: pointer;
  transition: all 200ms ease;
  overflow: hidden;
}

.modern-primary-nav__item::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 4px;
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  opacity: 0;
  transition: opacity 200ms ease;
}

.modern-primary-nav__item:hover {
  background: #f8fafc;
  border-color: #cbd5e1;
  transform: translateX(4px);
}

.modern-primary-nav__item--active {
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
  border-color: #3b82f6;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.15);
}

.modern-primary-nav__item--active::before {
  opacity: 1;
}

.modern-primary-nav__icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background: #f1f5f9;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #64748b;
  transition: all 200ms ease;
  flex-shrink: 0;
}

.modern-primary-nav__item:hover .modern-primary-nav__icon {
  background: #e2e8f0;
  color: #475569;
}

.modern-primary-nav__item--active .modern-primary-nav__icon {
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  color: #ffffff;
  box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
}

.modern-primary-nav__content {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.modern-primary-nav__label {
  font-size: 0.95rem;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.01em;
}

.modern-primary-nav__description {
  font-size: 0.8rem;
  color: #64748b;
  line-height: 1.4;
}

.modern-primary-nav__item--active .modern-primary-nav__label {
  color: #1e40af;
}

.modern-primary-nav__item--active .modern-primary-nav__description {
  color: #3b82f6;
}

.modern-primary-nav__indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: transparent;
  transition: all 200ms ease;
  flex-shrink: 0;
}

.modern-primary-nav__item--active .modern-primary-nav__indicator {
  background: #3b82f6;
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.2);
}
</style>
