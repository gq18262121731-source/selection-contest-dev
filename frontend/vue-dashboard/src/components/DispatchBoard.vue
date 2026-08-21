<script setup lang="ts">
export interface DispatchTask {
  stage: string;
  title: string;
  summary: string;
  owner: string;
  eta: string;
  tone: "critical" | "warning" | "stable";
}

defineProps<{
  tasks: DispatchTask[];
}>();
</script>

<template>
  <section class="panel dispatch-panel">
    <div class="panel-head">
      <div>
        <h2>调度闭环看板</h2>
        <p class="panel-subtitle">把告警、重点设备和社区分层转成值守人员可直接执行的行动清单。</p>
      </div>
      <span>{{ tasks.length }} 项建议</span>
    </div>
    <div class="dispatch-list">
      <article
        v-for="task in tasks"
        :key="`${task.stage}-${task.title}`"
        class="dispatch-card"
        :class="`dispatch-${task.tone}`"
      >
        <div class="dispatch-stage">
          <span>{{ task.stage }}</span>
          <strong>{{ task.eta }}</strong>
        </div>
        <div class="dispatch-main">
          <h3>{{ task.title }}</h3>
          <p>{{ task.summary }}</p>
          <div class="dispatch-meta">
            <span>责任人 {{ task.owner }}</span>
          </div>
        </div>
      </article>
      <p v-if="!tasks.length" class="empty-copy">当前没有待分派的调度任务。</p>
    </div>
  </section>
</template>
