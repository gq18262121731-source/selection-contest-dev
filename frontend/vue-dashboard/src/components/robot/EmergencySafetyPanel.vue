<script setup lang="ts">
import { ShieldCheck, ShieldX } from "lucide-vue-next";
import type { RobotControlOwner, RobotSafetyInterlock } from "../../types/robot";
import { robotBlockedReason, robotControlOwnerLabel } from "../../utils/robotPresentation";

defineProps<{
  interlock: RobotSafetyInterlock | null;
  controlOwner: RobotControlOwner | null;
}>();

const labels: Record<string, string> = {
  robot_online: "机器人在线",
  emergency_stop_clear: "急停已解除",
  localization_valid: "定位有效",
  map_loaded: "地图已加载",
  path_plannable: "路径可规划",
  robot_stationary: "机器人静止",
  control_available: "控制权可用",
};
</script>

<template>
  <article class="safety-card">
    <header>
      <span :class="{ 'is-passed': interlock?.passed }">
        <ShieldCheck v-if="interlock?.passed" :size="18" />
        <ShieldX v-else :size="18" />
      </span>
      <div><p>SAFETY INTERLOCK</p><h2>安全联锁与控制权</h2></div>
    </header>
    <div v-if="interlock" class="check-list">
      <div v-for="(passed, key) in interlock.checks" :key="key">
        <span :class="{ 'is-ok': passed }">{{ passed ? "通过" : "阻断" }}</span>
        <strong>{{ labels[key] ?? key }}</strong>
      </div>
    </div>
    <p v-else class="empty">安全联锁状态暂不可用，返航操作保持禁用。</p>
    <div class="control-owner">
      <span>当前控制权</span>
      <strong :class="{ 'is-manual': controlOwner === 'MANUAL' }">
        {{ robotControlOwnerLabel(controlOwner) }}
        <code>{{ controlOwner ?? "NONE" }}</code>
      </strong>
    </div>
    <div v-if="interlock?.blocked_by.length" class="blocked">
      <strong>返航阻断原因</strong>
      <p v-for="code in interlock.blocked_by" :key="code">
        {{ robotBlockedReason(code) }} <code>{{ code }}</code>
      </p>
    </div>
  </article>
</template>

<style scoped>
.safety-card { padding: 18px; border: 1px solid #dce6f0; border-radius: 18px; background: #fff; box-shadow: 0 8px 24px rgba(35, 78, 112, .055); }
header { display: flex; align-items: center; gap: 10px; }
header > span { display: grid; width: 36px; height: 36px; place-items: center; border-radius: 10px; background: #fff0ee; color: #a53630; }
header > span.is-passed { background: #e8f7f1; color: #087653; }
header p { margin: 0; color: #47779c; font-size: .62rem; font-weight: 850; letter-spacing: .09em; }
h2 { margin: 3px 0 0; color: #102a43; font-size: .96rem; }
.check-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 7px; margin-top: 14px; }
.check-list div { display: flex; align-items: center; gap: 7px; min-width: 0; padding: 8px; border: 1px solid #e3eaf0; border-radius: 9px; background: #f7fafc; }
.check-list span { padding: 3px 5px; border-radius: 5px; background: #fff0ee; color: #a53630; font-size: .56rem; font-weight: 850; }
.check-list span.is-ok { background: #e5f6ef; color: #087653; }
.check-list strong { color: #526e83; font-size: .64rem; }
.control-owner { display: flex; justify-content: space-between; gap: 10px; margin-top: 12px; padding: 10px 11px; border-radius: 9px; background: #edf4f9; color: #5b7286; font-size: .68rem; }
.control-owner strong { color: #245d87; font-family: var(--font-mono); }
.control-owner strong code { margin-left: 5px; color: #718698; font-size: .56rem; }
.control-owner strong.is-manual { color: #a16207; }
.empty, .blocked { margin: 12px 0 0; padding: 10px; border-radius: 9px; background: #fff8e8; color: #8b5a0a; font-size: .65rem; line-height: 1.45; }
.blocked { background: #fff3f1; color: #a53630; }
.blocked > strong { display: block; margin-bottom: 4px; }
.blocked p { margin: 3px 0; }
.blocked code { font-family: var(--font-mono); font-size: .58rem; }
@media (max-width: 420px) { .check-list { grid-template-columns: 1fr; } }
</style>
