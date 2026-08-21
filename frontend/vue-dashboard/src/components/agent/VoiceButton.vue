<script setup lang="ts">
import { ref, onUnmounted } from "vue";
import { api } from "../../api/client";
import { Mic, MicOff, Volume2, Loader } from "lucide-vue-next";

const emit = defineEmits<{
  transcript: [text: string];
}>();

const props = withDefaults(defineProps<{
  voice?: string;
  disabled?: boolean;
}>(), {
  voice: "longyingtian",
  disabled: false,
});

type VoiceState = "idle" | "recording" | "processing" | "speaking" | "error";

const state = ref<VoiceState>("idle");
const errorMsg = ref("");
const isListening = ref(false);

let mediaRecorder: MediaRecorder | null = null;
let audioChunks: Blob[] = [];
let audioEl: HTMLAudioElement | null = null;
let stream: MediaStream | null = null;

async function speakText(text: string, voice = props.voice) {
  if (!text.trim()) return;
  try {
    state.value = "speaking";
    const result = await api.voiceTts(text, voice, "mp3");
    if (!result.ok || !result.audio_b64) {
      // fallback: browser TTS
      useBrowserTTS(text);
      return;
    }
    const bytes = Uint8Array.from(atob(result.audio_b64), (c) => c.charCodeAt(0));
    const blob = new Blob([bytes], { type: "audio/mpeg" });
    const url = URL.createObjectURL(blob);
    audioEl = new Audio(url);
    audioEl.onended = () => {
      URL.revokeObjectURL(url);
      state.value = "idle";
    };
    audioEl.onerror = () => {
      state.value = "idle";
    };
    await audioEl.play();
  } catch {
    useBrowserTTS(text);
  }
}

function useBrowserTTS(text: string) {
  if (!("speechSynthesis" in window)) { state.value = "idle"; return; }
  window.speechSynthesis.cancel();
  const utt = new SpeechSynthesisUtterance(text);
  utt.lang = "zh-CN";
  utt.rate = 0.95;
  utt.onend = () => { state.value = "idle"; };
  window.speechSynthesis.speak(utt);
}

function stopSpeaking() {
  audioEl?.pause();
  audioEl = null;
  window.speechSynthesis?.cancel();
  state.value = "idle";
}

// ── ASR: record and transcribe ────────────────────────────────────────
async function startRecording() {
  errorMsg.value = "";
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioChunks = [];
    const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : "audio/webm";
    mediaRecorder = new MediaRecorder(stream, { mimeType });
    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) audioChunks.push(e.data);
    };
    mediaRecorder.onstop = async () => {
      stream?.getTracks().forEach((t) => t.stop());
      stream = null;
      state.value = "processing";
      const blob = new Blob(audioChunks, { type: "audio/webm" });
      try {
        const result = await api.voiceAsr(blob);
        if (result.ok && result.text) {
          emit("transcript", result.text);
        } else if (result.text) {
          emit("transcript", result.text);
        } else {
          // fallback browser ASR
          useBrowserASR();
          return;
        }
        state.value = "idle";
      } catch {
        useBrowserASR();
      }
    };
    mediaRecorder.start(200);
    state.value = "recording";
    isListening.value = true;
  } catch {
    errorMsg.value = "麦克风权限被拒绝";
    state.value = "error";
  }
}

function stopRecording() {
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
  }
  isListening.value = false;
}

function useBrowserASR() {
  type SpeechRecognitionResultEventLike = Event & {
    results: ArrayLike<ArrayLike<{ transcript?: string }>>;
  };
  type SpeechRecognitionCtor = new () => {
    lang: string;
    interimResults: boolean;
    onresult: ((event: SpeechRecognitionResultEventLike) => void) | null;
    onerror: (() => void) | null;
    onend: (() => void) | null;
    start: () => void;
  };
  const speechWindow = window as Window & {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  const SR = speechWindow.SpeechRecognition || speechWindow.webkitSpeechRecognition;
  if (!SR) { state.value = "error"; errorMsg.value = "语音识别不可用"; return; }
  const recog = new SR();
  recog.lang = "zh-CN";
  recog.interimResults = false;
  recog.onresult = (e: SpeechRecognitionResultEventLike) => {
    const text = e.results[0]?.[0]?.transcript ?? "";
    if (text) emit("transcript", text);
    state.value = "idle";
  };
  recog.onerror = () => { state.value = "error"; errorMsg.value = "识别失败"; };
  recog.onend = () => { if (state.value !== "idle") state.value = "idle"; };
  recog.start();
  state.value = "recording";
}

function handleMicClick() {
  if (props.disabled) return;
  if (state.value === "speaking") { stopSpeaking(); return; }
  if (state.value === "recording") { stopRecording(); return; }
  if (state.value === "idle" || state.value === "error") { startRecording(); return; }
}

onUnmounted(() => {
  stream?.getTracks().forEach((t) => t.stop());
  audioEl?.pause();
  window.speechSynthesis?.cancel();
});

defineExpose({ speakText, stopSpeaking });
</script>

<template>
  <div class="voice-btn-wrap">
    <button
      type="button"
      class="voice-btn"
      :class="[`voice-btn--${state}`, { 'voice-btn--disabled': disabled }]"
      :aria-label="state === 'recording' ? '停止录音' : '开始语音输入'"
      @click="handleMicClick"
    >
      <span class="voice-btn__ring" v-if="state === 'recording'" />
      <Loader v-if="state === 'processing'" :size="18" class="voice-btn__spin" />
      <Volume2 v-else-if="state === 'speaking'" :size="18" />
      <MicOff v-else-if="state === 'error'" :size="18" />
      <Mic v-else :size="18" />
    </button>
    <span v-if="state === 'recording'" class="voice-label">录音中…</span>
    <span v-else-if="state === 'processing'" class="voice-label">识别中…</span>
    <span v-else-if="state === 'speaking'" class="voice-label voice-label--speaking">播放中 ·
      <button class="voice-stop" @click="stopSpeaking">停止</button>
    </span>
    <span v-else-if="errorMsg" class="voice-label voice-label--error">{{ errorMsg }}</span>
  </div>
</template>

<style scoped>
.voice-btn-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
}

.voice-btn {
  position: relative;
  width: 42px;
  height: 42px;
  border-radius: 999px;
  border: 1.5px solid rgba(34, 211, 238, 0.30);
  background: rgba(34, 211, 238, 0.08);
  color: #22d3ee;
  display: grid;
  place-items: center;
  cursor: pointer;
  transition: all 180ms ease;
  flex-shrink: 0;
}

.voice-btn:hover:not(.voice-btn--disabled) {
  background: rgba(34, 211, 238, 0.16);
  border-color: rgba(34, 211, 238, 0.50);
  transform: scale(1.06);
}

.voice-btn--recording {
  background: rgba(248, 113, 122, 0.14);
  border-color: rgba(248, 113, 122, 0.50);
  color: #f87171;
}

.voice-btn--speaking {
  background: rgba(52, 211, 153, 0.12);
  border-color: rgba(52, 211, 153, 0.40);
  color: #34d399;
}

.voice-btn--error {
  background: rgba(248, 113, 122, 0.08);
  border-color: rgba(248, 113, 122, 0.28);
  color: #f87171;
}

.voice-btn--disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.voice-btn__ring {
  position: absolute;
  inset: -6px;
  border-radius: 999px;
  border: 2px solid rgba(248, 113, 122, 0.50);
  animation: voice-pulse 1.2s ease-out infinite;
  pointer-events: none;
}

.voice-btn__spin {
  animation: spin 1s linear infinite;
}

@keyframes voice-pulse {
  0%   { transform: scale(1);    opacity: 0.8; }
  100% { transform: scale(1.5);  opacity: 0; }
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.voice-label {
  font-size: 0.84rem;
  color: #6ea8c8;
  white-space: nowrap;
}

.voice-label--speaking {
  color: #34d399;
  display: flex;
  align-items: center;
  gap: 8px;
}

.voice-label--error {
  color: #f87171;
}

.voice-stop {
  background: none;
  border: none;
  color: #f87171;
  cursor: pointer;
  font-size: 0.82rem;
  padding: 0;
  text-decoration: underline;
}
</style>
