<script setup lang="ts">
import {
  Bot,
  ListChecks,
  MapPinned,
  RadioTower,
  type LucideIcon,
} from "lucide-vue-next";
import { computed } from "vue";
import type { PageKey } from "../../composables/useHashRouting";

const props = defineProps<{
  activePage: PageKey;
  allowedPages: PageKey[];
}>();

const emit = defineEmits<{
  navigate: [page: PageKey];
}>();

type RobotWorkspaceItem = {
  page: PageKey;
  label: string;
  icon: LucideIcon;
};

const robotWorkspaceItems = computed<RobotWorkspaceItem[]>(() =>
  ([
    {
      page: "robot-tasks" as PageKey,
      label: "机器人任务",
      icon: ListChecks,
    },
    {
      page: "robot-status" as PageKey,
      label: "机器人状态",
      icon: RadioTower,
    },
    {
      page: "robot-navigation" as PageKey,
      label: "建图巡航",
      icon: MapPinned,
    },
    {
      page: "robot-follow" as PageKey,
      label: "机器狗跟随",
      icon: Bot,
    },
  ] satisfies RobotWorkspaceItem[]).filter((item) => props.allowedPages.includes(item.page)),
);
</script>

<template>
  <div v-if="robotWorkspaceItems.length" class="robot-workspace-nav-shell">
    <nav class="robot-workspace-nav" aria-label="机器人工作区">
      <button
        v-for="item in robotWorkspaceItems"
        :key="item.page"
        type="button"
        class="robot-workspace-nav__item"
        :class="{ 'robot-workspace-nav__item--active': activePage === item.page }"
        :aria-current="activePage === item.page ? 'page' : undefined"
        @click="emit('navigate', item.page)"
      >
        <component :is="item.icon" :size="17" aria-hidden="true" />
        <span>{{ item.label }}</span>
      </button>
    </nav>
  </div>
</template>

<style scoped>
.robot-workspace-nav-shell {
  display: flex;
  justify-content: flex-end;
  width: 100%;
}

.robot-workspace-nav {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 100%;
  padding: 5px;
  border: 1px solid #dbe4f0;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 8px 22px rgba(15, 23, 42, 0.06);
}

.robot-workspace-nav__item {
  display: inline-flex;
  min-height: 42px;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 0 15px;
  border: 1px solid transparent;
  border-radius: 10px;
  background: transparent;
  color: #64748b;
  font: inherit;
  font-size: 0.88rem;
  font-weight: 700;
  white-space: nowrap;
  cursor: pointer;
  transition:
    background-color 160ms ease,
    border-color 160ms ease,
    color 160ms ease,
    box-shadow 160ms ease;
}

.robot-workspace-nav__item:hover {
  border-color: #dbeafe;
  background: #f8fbff;
  color: #1d4ed8;
}

.robot-workspace-nav__item:focus-visible {
  outline: 3px solid rgba(59, 130, 246, 0.3);
  outline-offset: 2px;
}

.robot-workspace-nav__item--active {
  border-color: #bfdbfe;
  background: #eff6ff;
  color: #1d4ed8;
  box-shadow: 0 3px 10px rgba(37, 99, 235, 0.1);
}

@media (max-width: 760px) {
  .robot-workspace-nav-shell {
    justify-content: flex-start;
    overflow-x: auto;
    padding-bottom: 3px;
    scrollbar-width: thin;
  }

  .robot-workspace-nav {
    min-width: max-content;
  }

  .robot-workspace-nav__item {
    min-height: 44px;
    padding-inline: 14px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .robot-workspace-nav__item {
    transition: none;
  }
}
</style>
