<script setup lang="ts">
import { computed } from "vue";
import { BellRing, CircleCheckBig, Clock3 } from "lucide-vue-next";
import type { RobotDialogueIntent, RobotEmergencyCaseStatus } from "../../types/robot";

const props = defineProps<{
  intent: RobotDialogueIntent | null;
  status: RobotEmergencyCaseStatus | null;
}>();

const content = computed(() => {
  if (props.intent === "safe_response") {
    return { tone: "safe", title: "老人已明确回应", message: "机器人保持原地，等待管理员确认后再评估返航。", icon: CircleCheckBig };
  }
  if (props.intent === "need_help") {
    return { tone: "critical", title: "老人请求帮助", message: "高优先级告警已升级，等待人工处置，禁止返航。", icon: BellRing };
  }
  if (props.intent === "no_response") {
    return { tone: "critical", title: "15 秒内无有效回应", message: "高优先级告警已升级，机器人保持原地，禁止返航。", icon: BellRing };
  }
  if (props.intent === "uncertain") {
    return { tone: "critical", title: "无法可靠判断老人状态", message: "按需要帮助分支升级，等待人工处置，禁止返航。", icon: BellRing };
  }
  return { tone: "pending", title: props.status === "blocked" ? "等待人工处置" : "等待现场回应", message: "尚未形成 Mock 对话结论，告警保持有效。", icon: Clock3 };
});
</script>

<template>
  <article class="escalation-card" :class="`is-${content.tone}`">
    <component :is="content.icon" :size="20" />
    <div>
      <p>ALARM DISPOSITION</p>
      <h2>{{ content.title }}</h2>
      <span>{{ content.message }}</span>
    </div>
  </article>
</template>

<style scoped>
.escalation-card { display: grid; grid-template-columns: auto 1fr; gap: 10px; padding: 16px; border: 1px solid #edca8f; border-radius: 16px; background: #fff8e8; color: #8b5a0a; }
.escalation-card.is-safe { border-color: #a9ddca; background: #edf9f4; color: #087653; }
.escalation-card.is-critical { border-color: #efb6b0; border-left: 4px solid #c43d32; background: #fff2f0; color: #a53630; }
p { margin: 0; font-size: .6rem; font-weight: 850; letter-spacing: .09em; }
h2 { margin: 4px 0; font-size: .9rem; }
span { font-size: .67rem; line-height: 1.5; }
</style>
