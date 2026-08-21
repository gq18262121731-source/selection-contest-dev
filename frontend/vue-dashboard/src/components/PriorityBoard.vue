<script setup lang="ts">
import type { HealthSample } from "../api/client";

export interface PriorityBoardItem {
  deviceMac: string;
  deviceName: string;
  status: string;
  riskLabel: string;
  score: number;
  action: string;
  summary: string;
  sample: HealthSample | null;
}

defineProps<{
  items: PriorityBoardItem[];
}>();
</script>

<template>
  <section class="panel priority-panel">
    <div class="panel-head">
      <div>
        <h2>重点设备榜</h2>
        <p class="panel-subtitle">按综合风险和当前生命体征排序，帮助值守人员优先安排电话或现场核查。</p>
      </div>
      <span>Top {{ items.length }}</span>
    </div>
    <div class="priority-list">
      <article v-for="(item, index) in items" :key="item.deviceMac" class="priority-card">
        <div class="priority-rank">{{ index + 1 }}</div>
        <div class="priority-main">
          <div class="priority-head">
            <div>
              <p>{{ item.deviceName }}</p>
              <strong>{{ item.deviceMac }}</strong>
            </div>
            <span class="risk-chip" :class="`risk-${item.riskLabel}`">{{ item.riskLabel === 'high' ? '高风险' : item.riskLabel === 'medium' ? '中风险' : item.riskLabel === 'low' ? '低风险' : '待同步' }}</span>
          </div>
          <p class="priority-summary">{{ item.summary }}</p>
          <div class="priority-meta">
            <span>状态 {{ item.status }}</span>
            <span>优先分 {{ item.score }}</span>
          </div>
          <small>{{ item.action }}</small>
        </div>
      </article>
      <p v-if="!items.length" class="empty-copy">暂无可排序的设备。</p>
    </div>
  </section>
</template>
