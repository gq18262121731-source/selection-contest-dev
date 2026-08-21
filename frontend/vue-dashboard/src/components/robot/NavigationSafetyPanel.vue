<script setup lang="ts">
import { computed } from "vue";
import { Check, ShieldCheck, X } from "lucide-vue-next";
import type { RobotNavigationState } from "../../types/robot";
import { robotBlockedReason } from "../../utils/robotPresentation";

const props = defineProps<{ state: RobotNavigationState | null }>();

const checks = computed(() => {
  const explicit = props.state?.safety_interlock?.checks;
  return [
    ["robot_online", "机器人在线", explicit?.robot_online ?? props.state?.robot_online ?? false],
    ["emergency_stop_clear", "急停已解除", explicit?.emergency_stop_clear ?? props.state?.emergency_stop_clear ?? false],
    ["localization_valid", "定位有效", explicit?.localization_valid ?? props.state?.localization_valid ?? false],
    ["map_loaded", "地图已加载", explicit?.map_loaded ?? props.state?.map_loaded ?? false],
    ["path_plannable", "路径可规划", explicit?.path_plannable ?? props.state?.path_plannable ?? false],
    ["robot_stationary", "机器人静止", explicit?.robot_stationary ?? props.state?.robot_stationary ?? false],
    ["control_available", "控制权可用", explicit?.control_available ?? props.state?.control_available ?? false],
  ] as const;
});

const passed = computed(() => checks.value.every(([, , value]) => value));
const blockedBy = computed(() => (
  props.state?.safety_interlock?.blocked_by?.length
    ? props.state.safety_interlock.blocked_by
    : checks.value.filter(([, , value]) => !value).map(([key]) => key.toUpperCase())
));
</script>

<template>
  <section class="safety-card">
    <header>
      <span class="icon" :class="{ 'icon--passed': passed }"><ShieldCheck :size="18" /></span>
      <div>
        <h3>安全联锁</h3>
        <p>启动、继续和返航必须由后端再次校验。</p>
      </div>
      <span class="result" :class="{ 'result--passed': passed }">{{ passed ? "通过" : "阻断" }}</span>
    </header>
    <ul>
      <li v-for="[key, label, value] in checks" :key="key" :class="{ failed: !value }">
        <span class="check-icon"><Check v-if="value" :size="13" /><X v-else :size="13" /></span>
        <span>{{ label }}</span>
        <code>{{ key }}</code>
      </li>
    </ul>
    <div v-if="blockedBy.length" class="blocked">
      <strong>安全阻断原因</strong>
      <span v-for="code in blockedBy" :key="code">
        {{ robotBlockedReason(code) }}
        <code>{{ code }}</code>
      </span>
    </div>
  </section>
</template>

<style scoped>
.safety-card { display: grid; gap: 14px; padding: 20px; border: 1px solid #dbe4ee; border-radius: 18px; background: #fff; }
header { display: grid; grid-template-columns: auto 1fr auto; gap: 11px; align-items: start; }
.icon { display: grid; width: 36px; height: 36px; place-items: center; border-radius: 10px; background: #fef2f2; color: #dc2626; }
.icon--passed { background: #f0fdf4; color: #15803d; }
h3 { margin: 0 0 3px; color: #0f172a; font-size: .98rem; }
p { margin: 0; color: #64748b; font-size: .74rem; }
.result { padding: 5px 9px; border-radius: 999px; background: #fef2f2; color: #b91c1c; font-size: .68rem; font-weight: 850; }
.result--passed { background: #dcfce7; color: #166534; }
ul { display: grid; gap: 5px; padding: 0; margin: 0; list-style: none; }
li { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 7px; padding: 7px 8px; border-radius: 8px; color: #166534; background: #f7fdf9; font-size: .74rem; }
li.failed { color: #991b1b; background: #fff8f8; }
.check-icon { display: grid; width: 20px; height: 20px; place-items: center; border-radius: 50%; background: #dcfce7; }
.failed .check-icon { background: #fee2e2; }
code { color: #94a3b8; font-size: .61rem; }
.blocked { display: flex; flex-wrap: wrap; gap: 5px; padding-top: 10px; border-top: 1px solid #fee2e2; }
.blocked strong { width: 100%; color: #991b1b; font-size: .67rem; }
.blocked span { display: inline-flex; align-items: center; gap: 5px; padding: 4px 6px; border-radius: 5px; background: #fef2f2; color: #b91c1c; font-size: .65rem; }
.blocked span code { color: #a53630; font-family: ui-monospace, monospace; font-size: .56rem; }
</style>
