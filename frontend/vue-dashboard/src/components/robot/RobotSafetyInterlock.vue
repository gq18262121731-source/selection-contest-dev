<script setup lang="ts">
import { computed } from "vue";
import { Check, ShieldAlert, X } from "lucide-vue-next";
import type { RobotSafetyInterlock } from "../../types/robot";
import { robotBlockedReason } from "../../utils/robotPresentation";

const props = defineProps<{ interlock: RobotSafetyInterlock | null | undefined }>();

const checkLabels: Record<string, string> = {
  robot_online: "机器人在线",
  emergency_stop_clear: "急停已解除",
  localization_valid: "定位有效",
  map_loaded: "地图已加载",
  path_plannable: "路径可规划",
  robot_stationary: "机器人静止",
  control_available: "控制权可用",
};

const checks = computed(() => Object.entries(props.interlock?.checks ?? {}).map(([key, passed]) => ({
  key,
  label: checkLabels[key] ?? key,
  passed,
})));
</script>

<template>
  <article class="robot-status-card robot-interlock">
    <header class="robot-interlock__head">
      <div class="robot-interlock__title">
        <span><ShieldAlert :size="19" /></span>
        <div><p>SAFETY INTERLOCK</p><h2>安全联锁</h2></div>
      </div>
      <strong v-if="interlock" :class="interlock.passed ? 'is-passed' : 'is-blocked'">
        {{ interlock.passed ? "Mock 检查通过" : "已阻塞" }}
      </strong>
      <strong v-else class="is-unknown">未验证</strong>
    </header>

    <div v-if="checks.length" class="robot-interlock__checks">
      <div v-for="check in checks" :key="check.key">
        <span :class="check.passed ? 'is-passed' : 'is-blocked'">
          <Check v-if="check.passed" :size="14" />
          <X v-else :size="14" />
        </span>
        <p>{{ check.label }}</p>
      </div>
    </div>
    <p v-else class="robot-interlock__empty">后端尚未返回七项联锁检查，当前不能视为已通过。</p>

    <div v-if="interlock?.blocked_by.length" class="robot-interlock__blocked">
      <span>阻断原因</span>
      <div v-for="code in interlock.blocked_by" :key="code">
        <strong>{{ robotBlockedReason(code) }}</strong>
        <code>{{ code }}</code>
      </div>
    </div>
    <p class="robot-interlock__note">本页面仅展示联锁结果，不提供绕过、启动或继续按钮。</p>
  </article>
</template>

<style scoped>
.robot-status-card { border: 1px solid #dce6f0; border-radius: 18px; background: #fbfdff; box-shadow: 0 8px 24px rgba(35, 78, 112, 0.06); }
.robot-interlock { padding: 20px; }
.robot-interlock__head, .robot-interlock__title { display: flex; align-items: center; gap: 11px; }
.robot-interlock__head { justify-content: space-between; }
.robot-interlock__title > span { width: 38px; height: 38px; display: grid; place-items: center; border-radius: 10px; background: #fff3df; color: #946213; }
.robot-interlock__title p { margin: 0; color: #7a6b50; font-size: 0.65rem; font-weight: 800; letter-spacing: 0.08em; }
.robot-interlock__title h2 { margin: 3px 0 0; color: #102a43; font-size: 1rem; }
.robot-interlock__head > strong { padding: 5px 9px; border-radius: 8px; font-size: 0.7rem; }
.is-passed { color: #087653; background: #e5f6ef; }
.is-blocked { color: #a53630; background: #fff0ee; }
.is-unknown { color: #64798c; background: #edf2f6; }
.robot-interlock__checks { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin-top: 16px; }
.robot-interlock__checks > div { display: flex; align-items: center; gap: 7px; min-width: 0; padding: 9px; border: 1px solid #e0e8ef; border-radius: 9px; background: #f7f9fb; }
.robot-interlock__checks span { width: 23px; height: 23px; display: grid; place-items: center; flex: 0 0 auto; border-radius: 7px; }
.robot-interlock__checks p { margin: 0; color: #506b80; font-size: 0.69rem; }
.robot-interlock__blocked { display: flex; flex-wrap: wrap; align-items: center; gap: 7px; margin-top: 13px; padding: 10px; border-radius: 9px; background: #fff7e8; color: #806226; font-size: 0.68rem; }
.robot-interlock__blocked > div { display: inline-flex; align-items: center; gap: 5px; padding: 4px 6px; border-radius: 6px; background: #fff; }
.robot-interlock__blocked strong { color: #806226; font-size: 0.65rem; }
.robot-interlock__blocked code { font-family: var(--font-mono); font-size: 0.58rem; }
.robot-interlock__empty, .robot-interlock__note { margin: 14px 0 0; color: #6b8092; font-size: 0.7rem; line-height: 1.5; }
@media (max-width: 720px) { .robot-interlock__checks { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
