<script setup lang="ts">
import { computed } from "vue";
import type { AlarmRecord } from "../../api/client";

const props = defineProps<{
  alarm: AlarmRecord | null;
  additionalCount: number;
  acknowledging?: boolean;
}>();

const emit = defineEmits<{
  acknowledge: [];
}>();

const triggerLabel = computed(() => {
  const trigger = props.alarm?.metadata?.sos_trigger;
  if (trigger === "long_press") return "长按求助";
  if (trigger === "double_click") return "双击求助";
  return "紧急求助";
});

const deviceName = computed(() => {
  const value = props.alarm?.metadata?.device_name;
  return typeof value === "string" && value.trim() ? value : "T10-WATCH";
});

const elderName = computed(() => {
  const value = props.alarm?.metadata?.elder_name;
  return typeof value === "string" && value.trim() ? value : "未归属设备";
});

const triggeredAt = computed(() => {
  if (!props.alarm?.created_at) return "--";
  return new Date(props.alarm.created_at).toLocaleString("zh-CN", { hour12: false });
});
</script>

<template>
  <transition name="sos-overlay">
    <div v-if="alarm" class="sos-overlay">
      <div class="sos-overlay__pulse" />
      <div class="sos-overlay__panel">
        <p class="sos-overlay__eyebrow">Emergency SOS</p>
        <h2>社区值守紧急呼叫</h2>
        <p class="sos-overlay__lead">
          已定位到设备 {{ deviceName }}，请立即查看对应老人状态并完成人工确认。
        </p>

        <div class="sos-overlay__grid">
          <article class="sos-card">
            <span>老人/设备</span>
            <strong>{{ elderName }} / {{ deviceName }}</strong>
          </article>
          <article class="sos-card">
            <span>触发方式</span>
            <strong>{{ triggerLabel }}</strong>
          </article>
          <article class="sos-card">
            <span>设备 MAC</span>
            <strong>{{ alarm.device_mac }}</strong>
          </article>
          <article class="sos-card">
            <span>触发时间</span>
            <strong>{{ triggeredAt }}</strong>
          </article>
        </div>

        <div class="sos-overlay__actions">
          <p v-if="additionalCount > 0" class="sos-overlay__queue">
            当前还有 {{ additionalCount }} 条 SOS 待处理。
          </p>
          <p v-else class="sos-overlay__queue-placeholder"></p>
          <button
            type="button"
            class="sos-overlay__button"
            :disabled="acknowledging"
            @click="emit('acknowledge')"
          >
            {{ acknowledging ? "处理中..." : "确认处理并解除警报" }}
          </button>
        </div>
      </div>
    </div>
  </transition>
</template>

<style scoped>
.sos-overlay {
  position: fixed;
  inset: 0;
  z-index: 1200;
  display: grid;
  place-items: center;
  padding: 28px;
  background:
    radial-gradient(circle at 50% 20%, rgba(255, 240, 240, 0.28), transparent 36%),
    rgba(74, 3, 15, 0.78);
  backdrop-filter: blur(10px);
}

.sos-overlay__pulse {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at center, rgba(255, 99, 99, 0.28), transparent 45%),
    linear-gradient(135deg, rgba(255, 92, 92, 0.24), rgba(125, 8, 24, 0.12));
  animation: sos-pulse 1.15s ease-in-out infinite;
}

.sos-overlay__panel {
  position: relative;
  width: min(900px, 100%);
  display: grid;
  gap: 22px;
  padding: 28px;
  border-radius: 30px;
  border: 1px solid rgba(255, 214, 214, 0.24);
  background:
    linear-gradient(180deg, rgba(104, 9, 24, 0.95), rgba(56, 5, 16, 0.92));
  box-shadow: 0 28px 90px rgba(34, 0, 0, 0.36);
  color: #fff6f6;
}

.sos-overlay__eyebrow {
  margin: 0;
  color: rgba(255, 228, 228, 0.82);
  letter-spacing: 0.18em;
  text-transform: uppercase;
  font-size: 0.76rem;
  font-weight: 700;
}

.sos-overlay__panel h2 {
  margin: 0;
  font-family: var(--font-display);
  font-size: clamp(2rem, 5vw, 3.3rem);
  line-height: 1;
}

.sos-overlay__lead,
.sos-overlay__queue,
.sos-card span {
  color: rgba(255, 231, 231, 0.84);
}

.sos-overlay__lead,
.sos-overlay__queue {
  margin: 0;
  line-height: 1.7;
}

.sos-overlay__grid {
  display: grid;
  gap: 14px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.sos-card {
  display: grid;
  gap: 8px;
  padding: 16px 18px;
  border-radius: 22px;
  background: rgba(255, 248, 248, 0.08);
  border: 1px solid rgba(255, 218, 218, 0.12);
}

.sos-card strong {
  font-size: 1.08rem;
  line-height: 1.5;
}

.sos-overlay__actions {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  min-height: 48px;
}

.sos-overlay__queue-placeholder {
  margin: 0;
  flex: 1;
}

.sos-overlay__button {
  border: none;
  border-radius: 999px;
  padding: 14px 22px;
  background: linear-gradient(135deg, #fff2f2, #ffd7d7);
  color: #730719;
  font-weight: 800;
  cursor: pointer;
  flex-shrink: 0;
  box-shadow: 0 14px 28px rgba(0, 0, 0, 0.18);
}

.sos-overlay__button:disabled {
  cursor: wait;
  opacity: 0.72;
}

.sos-overlay-enter-active,
.sos-overlay-leave-active {
  transition: opacity 180ms ease;
}

.sos-overlay-enter-from,
.sos-overlay-leave-to {
  opacity: 0;
}

@keyframes sos-pulse {
  0%,
  100% {
    opacity: 0.58;
    transform: scale(1);
  }

  50% {
    opacity: 0.96;
    transform: scale(1.02);
  }
}

@media (max-width: 760px) {
  .sos-overlay {
    padding: 18px;
  }

  .sos-overlay__panel {
    padding: 22px;
    border-radius: 24px;
  }

  .sos-overlay__grid {
    grid-template-columns: 1fr;
  }

  .sos-overlay__actions {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
