<script setup lang="ts">
import { computed } from "vue";
import { Camera, Radio, RefreshCw, Wifi, WifiOff } from "lucide-vue-next";
import { useGo2VideoBridge } from "../../composables/useGo2VideoBridge";

const {
  bridgeServiceMessage,
  diagnostics,
  markVideoError,
  markVideoOnline,
  retryVideo,
  serviceState,
  videoSource,
  videoStreamState,
} = useGo2VideoBridge();

type PanelState = "connected" | "connecting" | "stale" | "reconnecting" | "unavailable";

const panelState = computed<PanelState>(() => {
  if (videoStreamState.value === "ready") return "connected";
  if (videoStreamState.value === "stalled" || videoStreamState.value === "no-frame") return "stale";
  if (serviceState.value === "starting" || videoStreamState.value === "connecting") return "reconnecting";
  if (serviceState.value === "checking" || serviceState.value === "unknown") return "connecting";
  return "unavailable";
});

const stateLabel: Record<PanelState, string> = {
  connected: "已连接",
  connecting: "连接中",
  stale: "画面过期",
  reconnecting: "自动恢复中",
  unavailable: "不可用",
};

function formatTime(value: Date | null) {
  return value ? value.toLocaleTimeString("zh-CN", { hour12: false }) : "尚无画面";
}
</script>

<template>
  <article class="go2-video-panel">
    <header>
      <div><p>GO2 LIVE VIEW</p><h2>实时视频</h2></div>
      <span :class="`is-${panelState}`">
        <Wifi v-if="panelState === 'connected'" :size="14" />
        <WifiOff v-else-if="panelState === 'unavailable'" :size="14" />
        <Radio v-else :size="14" />
        {{ stateLabel[panelState] }}
      </span>
    </header>

    <div class="go2-video-panel__stage">
      <img
        v-show="panelState === 'connected'"
        :src="videoSource"
        alt="Go2 EDU 第一视角实时视频"
        crossorigin="anonymous"
        @load="markVideoOnline"
        @error="markVideoError"
      />
      <div v-if="panelState !== 'connected'" class="go2-video-panel__fallback">
        <Camera :size="25" />
        <strong>{{ stateLabel[panelState] }}</strong>
        <p>{{ bridgeServiceMessage }}</p>
      </div>
      <span class="go2-video-panel__hud">8093 / MJPEG</span>
    </div>

    <dl>
      <div><dt>最后画面</dt><dd>{{ formatTime(diagnostics.lastFrameAt) }}</dd></div>
      <div><dt>frame_age_ms</dt><dd>{{ diagnostics.frameAgeMs === null ? "-" : Math.round(diagnostics.frameAgeMs) }}</dd></div>
      <div><dt>自动恢复</dt><dd>{{ panelState === "connected" ? "监测中" : "有限退避" }}</dd></div>
    </dl>

    <button type="button" @click="retryVideo">
      <RefreshCw :size="14" />
      重试视频
    </button>
  </article>
</template>

<style scoped>
.go2-video-panel { min-width: 0; padding: 18px; border: 1px solid #dce6f0; border-radius: 18px; background: #fbfdff; box-shadow: 0 8px 24px rgba(35, 78, 112, 0.06); }
.go2-video-panel header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.go2-video-panel header p { margin: 0; color: #47779c; font-size: 0.65rem; font-weight: 800; letter-spacing: 0.08em; }
.go2-video-panel h2 { margin: 4px 0 0; color: #102a43; font-size: 1rem; }
.go2-video-panel header > span { display: inline-flex; align-items: center; gap: 5px; padding: 5px 8px; border-radius: 8px; background: #eef3f7; color: #5e768a; font-size: 0.68rem; font-weight: 750; }
.go2-video-panel header > span.is-connected { background: #e5f6ef; color: #087653; }
.go2-video-panel header > span.is-unavailable { background: #fff0ee; color: #a53630; }
.go2-video-panel header > span.is-stale { background: #fff3dc; color: #8b5a0a; }
.go2-video-panel__stage { position: relative; aspect-ratio: 16 / 9; margin-top: 14px; overflow: hidden; border: 1px solid #c7d5e0; border-radius: 11px; background: #eaf1f6; }
.go2-video-panel__stage img { width: 100%; height: 100%; display: block; object-fit: cover; }
.go2-video-panel__fallback { position: absolute; inset: 0; display: grid; place-content: center; justify-items: center; gap: 6px; padding: 18px; color: #58748a; text-align: center; }
.go2-video-panel__fallback strong { color: #294b65; font-size: 0.82rem; }
.go2-video-panel__fallback p { max-width: 320px; margin: 0; font-size: 0.68rem; line-height: 1.45; }
.go2-video-panel__hud { position: absolute; right: 8px; bottom: 8px; padding: 3px 6px; border-radius: 4px; background: rgba(17, 38, 54, 0.76); color: #eef7fd; font-family: var(--font-mono); font-size: 0.58rem; }
.go2-video-panel dl { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 7px; margin: 11px 0 0; }
.go2-video-panel dl div { min-width: 0; padding: 7px; border-radius: 8px; background: #f1f6f9; }
.go2-video-panel dt { color: #788d9e; font-size: 0.6rem; }
.go2-video-panel dd { margin: 3px 0 0; overflow: hidden; color: #3b5d76; font-family: var(--font-mono); font-size: 0.64rem; text-overflow: ellipsis; white-space: nowrap; }
.go2-video-panel button { width: 100%; display: inline-flex; align-items: center; justify-content: center; gap: 6px; margin-top: 10px; padding: 8px; border: 1px solid #c8d6e2; border-radius: 8px; background: #f8fbfd; color: #3e617b; font: inherit; font-size: 0.72rem; font-weight: 750; cursor: pointer; }
</style>
