<script setup lang="ts">
import { computed } from "vue";
import type { AlarmRecord } from "../../api/client";
import { extractRobotAlarmExtension } from "../../utils/robotEmergencyPolicy";

const props = defineProps<{
  alarm: AlarmRecord | null;
  additionalCount: number;
  acknowledging?: boolean;
}>();

const emit = defineEmits<{
  acknowledge: [];
  openEmergency: [incidentId: string];
}>();

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

const eventPayload = computed(() => {
  const metadata = asRecord(props.alarm?.metadata);
  return asRecord(metadata?.event) ?? asRecord(metadata?.raw_event) ?? metadata ?? null;
});

const elderName = computed(() => {
  const metadata = asRecord(props.alarm?.metadata);
  const value = metadata?.elder_name;
  return typeof value === "string" && value.trim() ? value : "待人工确认老人";
});

const cameraId = computed(() => {
  const value = eventPayload.value?.camera_id;
  return typeof value === "string" && value.trim() ? value : "--";
});

const riskLevel = computed(() => {
  const value = eventPayload.value?.risk_level ?? eventPayload.value?.risk;
  return typeof value === "string" && value.trim() ? value : "high";
});

const incidentId = computed(() => {
  const value = eventPayload.value?.incident_id;
  return typeof value === "string" && value.trim() ? value : "--";
});

const emergencyExtension = computed(() =>
  props.alarm ? extractRobotAlarmExtension(props.alarm) : null,
);

const fallScore = computed(() => {
  const value = eventPayload.value?.fall_score ?? eventPayload.value?.fall_prob ?? props.alarm?.anomaly_probability;
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed.toFixed(2) : "--";
});

const fallState = computed(() => {
  const value = eventPayload.value?.state ?? eventPayload.value?.status;
  return typeof value === "string" && value.trim() ? value : "confirmed_fall";
});

const triggeredAt = computed(() => {
  const raw = eventPayload.value?.timestamp ?? props.alarm?.created_at;
  if (typeof raw !== "string" || !raw.trim()) return "--";
  return new Date(raw).toLocaleString("zh-CN", { hour12: false });
});
</script>

<template>
  <transition name="fall-overlay">
    <div v-if="alarm" class="fall-overlay">
      <div class="fall-overlay__pulse" />
      <div class="fall-overlay__panel">
        <p class="fall-overlay__eyebrow">Fall Alert</p>
        <h2>检测到疑似跌倒，请立即复核</h2>
        <p class="fall-overlay__lead">
          主系统已收到视觉跌倒告警，请社区值守人员立即确认 {{ elderName }} 的现场状态，并按流程处理。
        </p>

        <div class="fall-overlay__grid">
          <article class="fall-card">
            <span>camera_id</span>
            <strong>{{ cameraId }}</strong>
          </article>
          <article class="fall-card">
            <span>事件状态</span>
            <strong>{{ fallState }}</strong>
          </article>
          <article class="fall-card">
            <span>风险等级</span>
            <strong>{{ riskLevel }}</strong>
          </article>
          <article class="fall-card">
            <span>跌倒分数</span>
            <strong>{{ fallScore }}</strong>
          </article>
          <article class="fall-card">
            <span>incident_id</span>
            <strong>{{ incidentId }}</strong>
          </article>
          <article class="fall-card">
            <span>触发时间</span>
            <strong>{{ triggeredAt }}</strong>
          </article>
        </div>

        <div class="fall-overlay__actions">
          <div class="fall-overlay__queue-wrap">
            <p v-if="additionalCount > 0" class="fall-overlay__queue">
              当前还有 {{ additionalCount }} 条跌倒告警待确认。
            </p>
            <p v-else-if="!emergencyExtension" class="fall-overlay__queue">
              应急任务尚未建立，请先按普通告警流程人工复核。
            </p>
          </div>
          <div class="fall-overlay__buttons">
            <button
              v-if="emergencyExtension"
              type="button"
              class="fall-overlay__button fall-overlay__button--primary"
              :disabled="acknowledging"
              @click="emit('openEmergency', emergencyExtension.incident_id)"
            >
              进入应急处置
            </button>
            <button
              type="button"
              class="fall-overlay__button"
              :disabled="acknowledging"
              @click="emit('acknowledge')"
            >
              {{ acknowledging ? "处理中..." : "我已知晓" }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </transition>
</template>

<style scoped>
.fall-overlay {
  position: fixed;
  inset: 0;
  z-index: 1190;
  display: grid;
  place-items: center;
  padding: 28px;
  background:
    radial-gradient(circle at 50% 20%, rgba(255, 231, 201, 0.28), transparent 36%),
    rgba(78, 34, 2, 0.72);
  backdrop-filter: blur(10px);
}

.fall-overlay__pulse {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at center, rgba(255, 161, 77, 0.22), transparent 45%),
    linear-gradient(135deg, rgba(255, 176, 89, 0.18), rgba(131, 62, 11, 0.12));
  animation: fall-pulse 1.4s ease-in-out infinite;
}

.fall-overlay__panel {
  position: relative;
  width: min(900px, 100%);
  max-height: calc(100dvh - 56px);
  overflow-y: auto;
  overscroll-behavior: contain;
  display: grid;
  gap: 22px;
  padding: 28px;
  border-radius: 30px;
  border: 1px solid rgba(255, 232, 208, 0.24);
  background:
    linear-gradient(180deg, rgba(99, 47, 10, 0.95), rgba(61, 27, 5, 0.92));
  box-shadow: 0 28px 90px rgba(34, 10, 0, 0.36);
  color: #fff8ef;
}

.fall-overlay__eyebrow {
  margin: 0;
  color: rgba(255, 234, 214, 0.82);
  letter-spacing: 0.18em;
  text-transform: uppercase;
  font-size: 0.76rem;
  font-weight: 700;
}

.fall-overlay__panel h2 {
  margin: 0;
  font-family: var(--font-display);
  font-size: clamp(2rem, 5vw, 3.2rem);
  line-height: 1.02;
}

.fall-overlay__lead,
.fall-overlay__queue,
.fall-card span {
  color: rgba(255, 235, 214, 0.84);
}

.fall-overlay__lead,
.fall-overlay__queue {
  margin: 0;
  line-height: 1.7;
}

.fall-overlay__grid {
  display: grid;
  gap: 14px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.fall-card {
  display: grid;
  gap: 8px;
  padding: 16px 18px;
  border-radius: 22px;
  background: rgba(255, 249, 241, 0.08);
  border: 1px solid rgba(255, 225, 188, 0.12);
}

.fall-card strong {
  font-size: 1.06rem;
  line-height: 1.5;
  word-break: break-word;
}

.fall-overlay__actions {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  min-height: 48px;
}

.fall-overlay__queue-wrap { flex: 1; }
.fall-overlay__buttons { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 10px; }

.fall-overlay__button {
  min-height: 46px;
  border: none;
  border-radius: 999px;
  padding: 14px 22px;
  background: linear-gradient(135deg, #fff1de, #ffd3a3);
  color: #6b3400;
  font-weight: 800;
  cursor: pointer;
  flex-shrink: 0;
  box-shadow: 0 14px 28px rgba(0, 0, 0, 0.18);
}

.fall-overlay__button--primary {
  background: #fff;
  color: #7b3900;
}

.fall-overlay__button:disabled {
  cursor: wait;
  opacity: 0.72;
}

.fall-overlay-enter-active,
.fall-overlay-leave-active {
  transition: opacity 180ms ease;
}

.fall-overlay-enter-from,
.fall-overlay-leave-to {
  opacity: 0;
}

@keyframes fall-pulse {
  0%,
  100% {
    opacity: 0.56;
    transform: scale(1);
  }

  50% {
    opacity: 0.92;
    transform: scale(1.02);
  }
}

@media (max-width: 760px) {
  .fall-overlay {
    padding: 18px;
  }

  .fall-overlay__panel {
    gap: 16px;
    padding: 22px;
    border-radius: 24px;
  }

  .fall-overlay__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .fall-overlay__actions {
    flex-direction: column;
    align-items: stretch;
  }

  .fall-overlay__buttons {
    justify-content: stretch;
  }

  .fall-overlay__button {
    flex: 1;
  }
}

@media (max-width: 460px) {
  .fall-overlay {
    padding: 10px;
  }

  .fall-overlay__panel {
    max-height: calc(100dvh - 20px);
    gap: 12px;
    padding: 16px;
    border-radius: 20px;
  }

  .fall-overlay__panel h2 {
    font-size: 1.55rem;
    line-height: 1.12;
  }

  .fall-overlay__lead,
  .fall-overlay__queue {
    font-size: 0.82rem;
    line-height: 1.5;
  }

  .fall-overlay__grid {
    gap: 8px;
  }

  .fall-card {
    gap: 4px;
    padding: 10px;
    border-radius: 14px;
  }

  .fall-card span {
    font-size: 0.68rem;
  }

  .fall-card strong {
    font-size: 0.78rem;
  }

  .fall-overlay__buttons {
    display: grid;
    grid-template-columns: 1fr;
  }
}

@media (prefers-reduced-motion: reduce) {
  .fall-overlay__pulse {
    animation: none;
  }

  .fall-overlay-enter-active,
  .fall-overlay-leave-active {
    transition: none;
  }
}
</style>
