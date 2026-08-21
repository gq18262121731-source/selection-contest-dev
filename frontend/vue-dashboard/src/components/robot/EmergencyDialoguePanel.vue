<script setup lang="ts">
import { computed } from "vue";
import { Bot, MessageCircleMore, MicOff, UserRound } from "lucide-vue-next";
import type {
  RobotDialogueIntent,
  RobotDialogueTurn,
  RobotNavigationExecutionState,
} from "../../types/robot";
import { robotExecutionStateLabel } from "../../utils/robotPresentation";

const props = defineProps<{
  turns: RobotDialogueTurn[];
  state: RobotNavigationExecutionState | null;
  prompt: Record<string, unknown> | null;
  disabled: boolean;
  submitting: boolean;
}>();

const emit = defineEmits<{
  result: [intent: RobotDialogueIntent];
}>();

const fixtures: Array<{ intent: RobotDialogueIntent; label: string }> = [
  { intent: "safe_response", label: "模拟“我没事”" },
  { intent: "need_help", label: "模拟“需要帮助”" },
  { intent: "no_response", label: "模拟“无回应”" },
  { intent: "uncertain", label: "模拟“无法判断”" },
];

const canRespond = computed(() => props.state === "waiting_response" && !props.disabled);

function display(value: string | number | null | undefined) {
  return value === null || value === undefined || value === "" ? "—" : String(value);
}

function formatTime(value: string) {
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}
</script>

<template>
  <article class="dialogue-card">
    <header>
      <span><MessageCircleMore :size="19" /></span>
      <div>
        <p>MOCK DIALOGUE</p>
        <h2>现场语音处置记录</h2>
      </div>
      <em><MicOff :size="13" /> 当前语音识别、对话理解和语音合成为模拟结果。</em>
    </header>

    <div v-if="prompt" class="prompt">
      <Bot :size="17" />
      <div>
        <strong>机器人模拟询问</strong>
        <p>{{ display(prompt.text as string | undefined) }}</p>
        <span>ASR {{ display(prompt.asr_status as string | undefined) }} · TTS {{ display(prompt.tts_status as string | undefined) }}</span>
      </div>
    </div>

    <div v-if="turns.length" class="turns">
      <article v-for="turn in turns" :key="turn.turn_id">
        <span><UserRound :size="16" /></span>
        <div>
          <div class="turn-head">
            <strong>{{ turn.role === "user" ? "模拟老人回应" : "机器人" }}</strong>
            <time>{{ formatTime(turn.occurred_at) }}</time>
          </div>
          <p>{{ turn.input_text || turn.text || "无有效文本" }}</p>
          <dl>
            <div><dt>intent</dt><dd>{{ display(turn.intent) }}</dd></div>
            <div><dt>confidence</dt><dd>{{ turn.confidence === null ? "—" : turn.confidence.toFixed(2) }}</dd></div>
            <div><dt>recommended</dt><dd>{{ display(turn.recommended_action) }}</dd></div>
            <div><dt>reply_text</dt><dd>{{ display(turn.reply_text) }}</dd></div>
            <div><dt>ASR</dt><dd>{{ display(turn.asr_status) }}</dd></div>
            <div><dt>TTS</dt><dd>{{ display(turn.tts_status) }}</dd></div>
          </dl>
        </div>
      </article>
    </div>
    <div v-else class="empty">暂无对话记录。机器人进入等待回应后，才可提交 Mock 结果。</div>

    <div class="mock-actions">
      <button
        v-for="fixture in fixtures"
        :key="fixture.intent"
        type="button"
        :class="`is-${fixture.intent}`"
        :disabled="!canRespond || submitting"
        @click="emit('result', fixture.intent)"
      >
        {{ submitting ? "提交中…" : fixture.label }}
      </button>
    </div>
    <p v-if="state !== 'waiting_response'" class="hint">
      当前状态为“{{ robotExecutionStateLabel(state) }}”，模拟结果按钮保持禁用。
    </p>
  </article>
</template>

<style scoped>
.dialogue-card { padding: 20px; border: 1px solid #dce6f0; border-radius: 18px; background: #fff; box-shadow: 0 8px 24px rgba(35, 78, 112, .055); }
header { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 10px; }
header > span { display: grid; width: 38px; height: 38px; place-items: center; border-radius: 11px; background: #eaf3fb; color: #326e9a; }
header p { margin: 0; color: #47779c; font-size: .63rem; font-weight: 850; letter-spacing: .09em; }
h2 { margin: 3px 0 0; color: #102a43; font-size: 1rem; }
header em { display: inline-flex; align-items: center; gap: 5px; padding: 6px 8px; border-radius: 8px; background: #fff8e8; color: #8b5a0a; font-size: .62rem; font-style: normal; font-weight: 750; }
.prompt { display: grid; grid-template-columns: auto 1fr; gap: 9px; margin-top: 15px; padding: 12px; border: 1px solid #c9dff0; border-radius: 11px; background: #f0f7fc; color: #2b648f; }
.prompt strong { font-size: .7rem; }
.prompt p { margin: 4px 0; color: #244e6d; font-size: .76rem; }
.prompt span { font-family: var(--font-mono); font-size: .6rem; }
.turns { display: grid; gap: 9px; margin-top: 12px; }
.turns > article { display: grid; grid-template-columns: auto 1fr; gap: 9px; padding: 12px; border: 1px solid #e0e8ee; border-radius: 11px; background: #fbfcfd; }
.turns > article > span { display: grid; width: 30px; height: 30px; place-items: center; border-radius: 9px; background: #edf2f6; color: #56738a; }
.turn-head { display: flex; justify-content: space-between; gap: 12px; }
.turn-head strong { color: #294b65; font-size: .7rem; }
.turn-head time { color: #8495a3; font-size: .59rem; }
.turns p { margin: 5px 0 8px; color: #3e6078; font-size: .72rem; line-height: 1.5; }
.turns dl { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px; margin: 0; }
.turns dl div { min-width: 0; padding: 6px; border-radius: 7px; background: #f1f5f8; }
dt { color: #8596a3; font-size: .55rem; }
dd { margin: 2px 0 0; overflow: hidden; color: #526e82; font-family: var(--font-mono); font-size: .59rem; text-overflow: ellipsis; white-space: nowrap; }
.empty { margin-top: 14px; padding: 22px; border: 1px dashed #cbd9e4; border-radius: 11px; color: #758b9d; font-size: .7rem; text-align: center; }
.mock-actions { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin-top: 14px; }
.mock-actions button { min-height: 38px; padding: 8px; border: 1px solid #bfd2e1; border-radius: 9px; background: #f5f9fc; color: #35617f; font: inherit; font-size: .66rem; font-weight: 780; cursor: pointer; }
.mock-actions button.is-safe_response { border-color: #a9ddca; background: #edf9f4; color: #087653; }
.mock-actions button.is-need_help, .mock-actions button.is-no_response, .mock-actions button.is-uncertain { border-color: #efc1bc; background: #fff5f3; color: #a53630; }
.mock-actions button:disabled { cursor: not-allowed; filter: grayscale(.45); opacity: .48; }
.hint { margin: 8px 0 0; color: #7d8f9c; font-size: .63rem; }
@media (max-width: 760px) { header { grid-template-columns: auto 1fr; } header em { grid-column: 1 / -1; justify-self: start; } .mock-actions { grid-template-columns: repeat(2, minmax(0, 1fr)); } .turns dl { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
