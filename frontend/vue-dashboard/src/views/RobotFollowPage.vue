<script setup lang="ts">
import { computed, ref } from "vue";
import {
  Bot,
  Camera,
  CircleAlert,
  CircleCheckBig,
  LoaderCircle,
  Play,
  Power,
  Radio,
  RefreshCw,
  Square,
  Wifi,
  WifiOff,
} from "lucide-vue-next";
import PageHeader from "../components/layout/PageHeader.vue";
import { GO2_VIDEO_BRIDGE } from "../config/go2VideoBridge";
import { useGo2VideoBridge } from "../composables/useGo2VideoBridge";

type FollowState = "unconfirmed" | "idle" | "following";
const VIDEO_URL = GO2_VIDEO_BRIDGE.streamUrl;

const followState = ref<FollowState>("unconfirmed");
const actionLog = ref<Array<{ id: number; action: string; detail: string; time: Date }>>([]);

const {
  bridgeButtonDisabled,
  bridgeButtonLabel,
  bridgeServiceLabel,
  bridgeServiceMessage,
  bridgeServiceState,
  diagnostics,
  launchLocalBridge,
  markVideoError,
  markVideoOnline,
  retryVideo,
  videoErrorReason,
  videoSource,
  videoState,
  videoStatusLabel,
} = useGo2VideoBridge();

const isFollowing = computed(() => followState.value === "following");
const isStopped = computed(() => followState.value === "idle");
const pageMeta = computed(() => [
  "设备 Go2 EDU",
  "链路 STA-L / Wi-Fi",
  "画面 1280 × 720",
]);

function formatTime(value: Date | null) {
  if (!value) return "尚无操作";
  return value.toLocaleTimeString("zh-CN", { hour12: false });
}

function formatDiagnosticTime(value: Date | null) {
  return value ? value.toLocaleTimeString("zh-CN", { hour12: false }) : "-";
}

function appendAction(action: string, detail: string) {
  const time = new Date();
  actionLog.value.unshift({ id: time.getTime(), action, detail, time });
  actionLog.value = actionLog.value.slice(0, 4);
}

function startFollow() {
  if (isFollowing.value) return;
  followState.value = "following";
  appendAction("开始跟随", "仅更新网页标记，等待遥控器同步执行");
}

function stopFollow() {
  if (isStopped.value) return;
  followState.value = "idle";
  appendAction("停止跟随", "仅更新网页标记，等待遥控器同步执行");
}

</script>

<template>
  <section class="page-stack robot-follow-page">
    <PageHeader
      eyebrow="Go2 / Companion Follow"
      title="机器狗自动跟随"
      description="通过 Go2 第一视角监看随行过程。自动跟随由工作人员使用随行遥控器实际启停，网页仅记录操作状态，不会直接控制机器狗运动。"
      :meta="pageMeta"
    >
      <template #actions>
        <button type="button" class="robot-follow-btn robot-follow-btn--secondary" @click="retryVideo">
          <RefreshCw :size="16" />
          重连视频
        </button>
      </template>
    </PageHeader>

    <article class="robot-follow-procedure">
      <div class="robot-follow-section-head">
        <div>
          <p class="section-eyebrow">标准操作流程</p>
          <h2>开始前完成三步确认</h2>
        </div>
        <span>工作人员与机器狗保持可视</span>
      </div>
      <ol>
        <li>
          <span>01</span>
          <div><strong>确认视频</strong><small>第一视角连续、方向正常，画面没有明显卡顿。</small></div>
        </li>
        <li>
          <span>02</span>
          <div><strong>检查环境</strong><small>清理台阶、玻璃门、人群和狭窄通道等风险区域。</small></div>
        </li>
        <li>
          <span>03</span>
          <div><strong>同步遥控器</strong><small>点击网页标记后，立即在随行遥控器上执行同一操作。</small></div>
        </li>
      </ol>
    </article>

    <div class="robot-follow-layout">
      <article class="robot-video-panel">
        <div class="robot-video-panel__head">
          <div>
            <p class="section-eyebrow">Go2 第一视角</p>
            <h2>实时摄像头</h2>
          </div>
          <span
            class="robot-video-state"
            :class="`robot-video-state--${videoState}`"
            role="status"
            aria-live="polite"
          >
            <component :is="videoState === 'online' ? Wifi : videoState === 'error' ? WifiOff : Radio" :size="15" />
            {{ videoStatusLabel }}
          </span>
        </div>

        <div class="robot-bridge-launch" :class="`robot-bridge-launch--${bridgeServiceState}`">
          <span class="robot-bridge-launch__icon" aria-hidden="true">
            <CircleCheckBig v-if="bridgeServiceState === 'ready'" :size="21" />
            <LoaderCircle v-else-if="['checking', 'launching', 'connecting'].includes(bridgeServiceState)" :size="21" />
            <CircleAlert v-else :size="21" />
          </span>
          <div class="robot-bridge-launch__copy" role="status" aria-live="polite">
            <small>本机视频桥接</small>
            <strong>{{ bridgeServiceLabel }}</strong>
            <p>{{ bridgeServiceMessage }}</p>
          </div>
          <button
            type="button"
            class="robot-follow-btn robot-follow-btn--launch"
            :disabled="bridgeButtonDisabled"
            @click="launchLocalBridge"
          >
            <LoaderCircle v-if="['checking', 'launching', 'connecting'].includes(bridgeServiceState)" :size="16" />
            <Power v-else :size="16" />
            {{ bridgeButtonLabel }}
          </button>
        </div>

        <div class="robot-video-stage" :class="{ 'robot-video-stage--error': videoState === 'error' }">
          <img
            v-show="videoState !== 'error'"
            :src="videoSource"
            crossorigin="anonymous"
            alt="Go2 EDU 机器狗第一视角实时画面"
            class="robot-video-stage__stream"
            @load="markVideoOnline"
            @error="markVideoError"
          />

          <div v-if="videoState === 'connecting'" class="robot-video-stage__overlay">
            <span class="robot-video-stage__scanner" aria-hidden="true"></span>
            <Radio :size="30" />
            <strong>正在连接无线视频</strong>
            <small>等待桥接电脑返回首帧画面</small>
          </div>

          <div v-else-if="videoState === 'error'" class="robot-video-error" role="alert">
            <span class="robot-video-error__icon"><Camera :size="28" /></span>
            <div>
              <strong>摄像头画面加载失败</strong>
              <p>{{ videoErrorReason }}</p>
            </div>
            <button type="button" class="robot-follow-btn robot-follow-btn--primary" @click="retryVideo">
              <RefreshCw :size="16" />
              重新连接
            </button>
          </div>

          <div class="robot-video-stage__hud" aria-hidden="true">
            <span>GO2 EDU</span>
            <span>1280 × 720</span>
            <span>LIVE / MJPEG</span>
          </div>
          <span class="robot-video-stage__corner robot-video-stage__corner--tl" aria-hidden="true"></span>
          <span class="robot-video-stage__corner robot-video-stage__corner--tr" aria-hidden="true"></span>
          <span class="robot-video-stage__corner robot-video-stage__corner--bl" aria-hidden="true"></span>
          <span class="robot-video-stage__corner robot-video-stage__corner--br" aria-hidden="true"></span>
        </div>

        <div class="robot-video-panel__source">
          <Camera :size="16" />
          <span>视频源</span>
          <code>{{ VIDEO_URL }}</code>
        </div>

        <details class="robot-video-diagnostics">
          <summary>视频诊断信息</summary>
          <dl>
            <div><dt>连接模式</dt><dd>{{ diagnostics.connectionMode }}</dd></div>
            <div><dt>机器狗地址</dt><dd>{{ diagnostics.robotIp }}</dd></div>
            <div><dt>最近画面</dt><dd>{{ formatDiagnosticTime(diagnostics.lastFrameAt) }}</dd></div>
            <div><dt>帧龄</dt><dd>{{ diagnostics.frameAgeMs === null ? '-' : `${Math.round(diagnostics.frameAgeMs)} ms` }}</dd></div>
            <div><dt>帧率</dt><dd>{{ diagnostics.fps.toFixed(1) }} FPS</dd></div>
            <div><dt>分辨率</dt><dd>{{ diagnostics.resolution }}</dd></div>
            <div><dt>重连次数</dt><dd>{{ diagnostics.reconnectCount }}</dd></div>
            <div><dt>服务版本</dt><dd>{{ diagnostics.serviceVersion }}</dd></div>
          </dl>
          <p>状态更新时间：{{ formatDiagnosticTime(diagnostics.updatedAt) }}</p>
        </details>
      </article>

      <aside class="robot-control-panel">
        <div class="robot-control-panel__identity">
          <span class="robot-control-panel__bot"><Bot :size="30" /></span>
          <div>
            <p class="section-eyebrow">跟随控制台</p>
            <h2>Go2 EDU</h2>
          </div>
          <span class="robot-control-panel__mode">遥控器协同</span>
        </div>

        <div class="robot-control-actions" aria-label="自动跟随状态控制">
          <button
            type="button"
            class="robot-control-action robot-control-action--start"
            :disabled="isFollowing"
            @click="startFollow"
          >
            <Play :size="19" fill="currentColor" />
            <span><strong>开始跟随</strong><small>标记后操作随行遥控器</small></span>
          </button>
          <button
            type="button"
            class="robot-control-action robot-control-action--stop"
            :disabled="isStopped"
            @click="stopFollow"
          >
            <Square :size="18" fill="currentColor" />
            <span><strong>停止跟随</strong><small>标记后确认机器狗静止</small></span>
          </button>
        </div>

      </aside>
    </div>

    <section class="robot-follow-support">
      <article class="robot-follow-log">
        <div class="robot-follow-section-head">
          <div>
            <p class="section-eyebrow">本次页面会话</p>
            <h2>最近操作记录</h2>
          </div>
          <span>{{ actionLog.length }} 条</span>
        </div>
        <div v-if="actionLog.length" class="robot-follow-log__list">
          <div v-for="item in actionLog" :key="item.id" class="robot-follow-log__item">
            <span class="robot-follow-log__dot" aria-hidden="true"></span>
            <div><strong>{{ item.action }}</strong><small>{{ item.detail }}</small></div>
            <time>{{ formatTime(item.time) }}</time>
          </div>
        </div>
        <div v-else class="robot-follow-log__empty">
          <Radio :size="24" />
          <p>当前页面还没有跟随操作。页面重新加载后，状态和记录都会清空并恢复为“未确认”。</p>
        </div>
      </article>
    </section>
  </section>
</template>

<style scoped>
.robot-follow-page {
  --robot-ink: #102a43;
  --robot-blue: #1f6feb;
  --robot-blue-deep: #174ea6;
  --robot-mist: #eef6ff;
  --robot-danger: #c2413a;
}

.robot-follow-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.7fr) minmax(320px, 0.72fr);
  gap: 18px;
  align-items: stretch;
}

.robot-video-panel,
.robot-control-panel,
.robot-follow-procedure,
.robot-follow-log {
  border: 1px solid #dce6f0;
  background: #fbfdff;
  box-shadow: 0 10px 32px rgba(35, 78, 112, 0.07);
}

.robot-video-panel {
  min-width: 0;
  padding: clamp(18px, 2.2vw, 26px);
  border-radius: 22px;
}

.robot-video-panel__head,
.robot-follow-section-head,
.robot-control-panel__identity {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.robot-video-panel h2,
.robot-control-panel h2,
.robot-follow-procedure h2,
.robot-follow-log h2 {
  margin: 3px 0 0;
  color: var(--robot-ink);
  font-size: 1.18rem;
  letter-spacing: -0.02em;
}

.robot-video-state {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 8px 11px;
  border: 1px solid #cad7e5;
  border-radius: 9px;
  background: #f4f8fc;
  color: #526b82;
  font-size: 0.78rem;
  font-weight: 750;
}

.robot-video-state--online {
  border-color: #a9ddca;
  background: #edf9f4;
  color: #087653;
}

.robot-video-state--error {
  border-color: #efc1bc;
  background: #fff3f1;
  color: #a53630;
}

.robot-bridge-launch {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
  padding: 13px 14px;
  border: 1px solid #cedce8;
  border-radius: 12px;
  background: #f3f8fc;
}

.robot-bridge-launch--ready {
  border-color: #a9ddca;
  background: #edf9f4;
}

.robot-bridge-launch--failed {
  border-color: #efc1bc;
  background: #fff4f2;
}

.robot-bridge-launch__icon {
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  background: #e3eef7;
  color: #376b91;
}

.robot-bridge-launch--ready .robot-bridge-launch__icon {
  background: #d8f1e7;
  color: #087653;
}

.robot-bridge-launch--failed .robot-bridge-launch__icon {
  background: #fbe1de;
  color: #a53630;
}

.robot-bridge-launch__copy {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.robot-bridge-launch__copy small {
  color: #6b8092;
  font-size: 0.7rem;
  font-weight: 700;
}

.robot-bridge-launch__copy strong {
  color: var(--robot-ink);
  font-size: 0.86rem;
}

.robot-bridge-launch__copy p {
  margin: 1px 0 0;
  color: #587187;
  font-size: 0.74rem;
  line-height: 1.45;
}

.robot-bridge-launch .lucide-loader-circle {
  animation: robot-spin 1s linear infinite;
}

.robot-video-stage {
  position: relative;
  aspect-ratio: 16 / 9;
  min-height: 320px;
  margin-top: 18px;
  overflow: hidden;
  border: 1px solid #b9cadb;
  border-radius: 14px;
  background:
    linear-gradient(rgba(98, 132, 161, 0.08) 1px, transparent 1px),
    linear-gradient(90deg, rgba(98, 132, 161, 0.08) 1px, transparent 1px),
    #eaf2f8;
  background-size: 32px 32px;
}

.robot-video-stage--error {
  background: #f3f7fa;
}

.robot-video-stage__stream {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: cover;
  background: #dfe9f2;
}

.robot-video-stage__overlay,
.robot-video-error {
  position: absolute;
  inset: 0;
  z-index: 2;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 8px;
  padding: 28px;
  text-align: center;
  color: #365e7d;
  background: rgba(235, 244, 251, 0.92);
}

.robot-video-stage__overlay strong,
.robot-video-error strong {
  color: var(--robot-ink);
  font-size: 1rem;
}

.robot-video-stage__overlay small {
  color: #607b91;
}

.robot-video-stage__scanner {
  position: absolute;
  left: 8%;
  right: 8%;
  top: 32%;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(31, 111, 235, 0.55), transparent);
  animation: robot-scan 2.4s cubic-bezier(0.22, 1, 0.36, 1) infinite;
}

.robot-video-error {
  max-width: none;
}

.robot-video-error__icon {
  width: 50px;
  height: 50px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: #fff;
  color: var(--robot-danger);
  box-shadow: 0 6px 18px rgba(118, 62, 53, 0.1);
}

.robot-video-error p {
  max-width: 560px;
  margin: 7px auto 0;
  color: #5d7183;
  font-size: 0.86rem;
  line-height: 1.65;
}

.robot-video-stage__hud {
  position: absolute;
  z-index: 3;
  left: 18px;
  right: 18px;
  bottom: 14px;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  pointer-events: none;
}

.robot-video-stage__hud span {
  padding: 5px 8px;
  border-radius: 5px;
  background: rgba(13, 35, 53, 0.72);
  color: #edf7ff;
  font-family: var(--font-mono);
  font-size: 0.68rem;
  letter-spacing: 0.04em;
}

.robot-video-stage__corner {
  position: absolute;
  z-index: 3;
  width: 24px;
  height: 24px;
  pointer-events: none;
}

.robot-video-stage__corner--tl { left: 14px; top: 14px; border-left: 2px solid #70b7f3; border-top: 2px solid #70b7f3; }
.robot-video-stage__corner--tr { right: 14px; top: 14px; border-right: 2px solid #70b7f3; border-top: 2px solid #70b7f3; }
.robot-video-stage__corner--bl { left: 14px; bottom: 50px; border-left: 2px solid #70b7f3; border-bottom: 2px solid #70b7f3; }
.robot-video-stage__corner--br { right: 14px; bottom: 50px; border-right: 2px solid #70b7f3; border-bottom: 2px solid #70b7f3; }

.robot-video-panel__source {
  min-width: 0;
  margin-top: 13px;
  display: grid;
  grid-template-columns: auto auto minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  color: #61798e;
  font-size: 0.77rem;
}

.robot-video-panel__source code {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #34556f;
  white-space: nowrap;
}

.robot-video-diagnostics {
  margin-top: 12px;
  border-top: 1px solid #dce6f0;
  color: #526b82;
}

.robot-video-diagnostics summary {
  width: fit-content;
  padding-top: 12px;
  color: #345a77;
  font-size: 0.76rem;
  font-weight: 750;
  cursor: pointer;
}

.robot-video-diagnostics dl {
  margin: 13px 0 0;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.robot-video-diagnostics dl > div {
  min-width: 0;
  display: grid;
  gap: 3px;
  padding: 9px 10px;
  border-radius: 8px;
  background: #f2f7fb;
}

.robot-video-diagnostics dt {
  color: #70869a;
  font-size: 0.66rem;
}

.robot-video-diagnostics dd {
  margin: 0;
  overflow: hidden;
  color: #274a65;
  font-size: 0.74rem;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.robot-video-diagnostics > p {
  margin: 10px 0 0;
  color: #71869a;
  font-size: 0.68rem;
}

.robot-control-panel {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: clamp(18px, 2.2vw, 24px);
  border-radius: 22px;
}

.robot-control-panel__identity {
  justify-content: flex-start;
  padding-bottom: 17px;
  border-bottom: 1px solid #dce6f0;
}

.robot-control-panel__bot {
  width: 52px;
  height: 52px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  border-radius: 14px;
  background: #eaf4ff;
  color: var(--robot-blue);
}

.robot-control-panel__mode {
  margin-left: auto;
  padding: 6px 9px;
  border-radius: 7px;
  background: #edf3f8;
  color: #516b80;
  font-size: 0.72rem;
  font-weight: 750;
}

.robot-control-actions {
  display: grid;
  gap: 10px;
}

.robot-control-action {
  width: 100%;
  display: grid;
  grid-template-columns: auto 1fr;
  align-items: center;
  gap: 12px;
  padding: 14px 15px;
  border: 1px solid;
  border-radius: 11px;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: transform 180ms ease, box-shadow 180ms ease, opacity 180ms ease;
}

.robot-control-action span {
  display: grid;
  gap: 2px;
}

.robot-control-action small {
  font-size: 0.73rem;
  font-weight: 550;
}

.robot-control-action--start {
  border-color: #1765c2;
  background: var(--robot-blue-deep);
  color: #f5faff;
  box-shadow: 0 8px 18px rgba(23, 78, 166, 0.16);
}

.robot-control-action--stop {
  border-color: #e3b5b0;
  background: #fff5f3;
  color: #a43a34;
}

.robot-control-action:hover:not(:disabled) {
  transform: translateY(-1px);
}

.robot-control-action:disabled {
  cursor: not-allowed;
  opacity: 0.42;
  box-shadow: none;
}

.robot-follow-support {
  display: block;
}

.robot-follow-procedure,
.robot-follow-log {
  padding: clamp(18px, 2.2vw, 24px);
  border-radius: 20px;
}

.robot-follow-section-head > span {
  color: #71869a;
  font-size: 0.75rem;
}

.robot-follow-procedure ol {
  margin: 18px 0 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  list-style: none;
}

.robot-follow-procedure li {
  min-width: 0;
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 11px;
  padding: 6px 18px;
  border-right: 1px solid #dce6f0;
}

.robot-follow-procedure li:first-child { padding-left: 0; }
.robot-follow-procedure li:last-child { padding-right: 0; border-right: 0; }

.robot-follow-procedure li > span {
  color: #2d78c8;
  font-family: var(--font-mono);
  font-size: 0.75rem;
  font-weight: 800;
}

.robot-follow-procedure li div,
.robot-follow-log__item div {
  display: grid;
  gap: 4px;
}

.robot-follow-procedure strong,
.robot-follow-log__item strong {
  color: var(--robot-ink);
  font-size: 0.86rem;
}

.robot-follow-procedure small,
.robot-follow-log__item small {
  color: #6b8092;
  font-size: 0.75rem;
  line-height: 1.55;
}

.robot-follow-log__list {
  margin-top: 16px;
  display: grid;
  gap: 10px;
}

.robot-follow-log__item {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 10px;
}

.robot-follow-log__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #4187c7;
}

.robot-follow-log__item time {
  color: #71869a;
  font-family: var(--font-mono);
  font-size: 0.7rem;
}

.robot-follow-log__empty {
  min-height: 112px;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 8px;
  text-align: center;
  color: #7890a3;
}

.robot-follow-log__empty p {
  max-width: 320px;
  margin: 0;
  font-size: 0.78rem;
  line-height: 1.55;
}

.robot-follow-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 9px 12px;
  border-radius: 9px;
  font: inherit;
  font-size: 0.8rem;
  font-weight: 750;
  cursor: pointer;
}

.robot-follow-btn--secondary {
  border: 1px solid #cbd8e4;
  background: #f8fbfd;
  color: #345a77;
}

.robot-follow-btn--primary {
  margin-top: 8px;
  border: 1px solid #1765c2;
  background: var(--robot-blue-deep);
  color: #f5faff;
}

.robot-follow-btn--launch {
  border: 1px solid #1765c2;
  background: var(--robot-blue-deep);
  color: #f5faff;
  white-space: nowrap;
}

.robot-follow-btn--launch:disabled {
  border-color: #c5d2dd;
  background: #e3eaf0;
  color: #72879a;
  cursor: not-allowed;
}

@keyframes robot-scan {
  0% { transform: translateY(-55px); opacity: 0; }
  20%, 75% { opacity: 1; }
  100% { transform: translateY(100px); opacity: 0; }
}

@keyframes robot-spin {
  to { transform: rotate(360deg); }
}

@media (prefers-reduced-motion: reduce) {
  .robot-video-stage__scanner { animation: none; }
  .robot-bridge-launch .lucide-loader-circle { animation: none; }
  .robot-control-action { transition: none; }
}

@media (max-width: 1180px) {
  .robot-follow-layout {
    grid-template-columns: 1fr;
  }

  .robot-control-panel {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .robot-control-panel__identity {
    grid-column: 1 / -1;
  }
}

@media (max-width: 720px) {
  .robot-video-stage { min-height: 240px; }
  .robot-bridge-launch { grid-template-columns: auto minmax(0, 1fr); }
  .robot-bridge-launch .robot-follow-btn--launch { grid-column: 1 / -1; width: 100%; }
  .robot-control-panel { display: flex; }
  .robot-follow-procedure ol { grid-template-columns: 1fr; gap: 12px; }
  .robot-follow-procedure li { padding: 0 0 12px; border-right: 0; border-bottom: 1px solid #dce6f0; }
  .robot-follow-procedure li:last-child { padding-bottom: 0; border-bottom: 0; }
  .robot-video-stage__hud span:nth-child(2) { display: none; }
  .robot-video-diagnostics dl { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 520px) {
  .robot-video-panel__head,
  .robot-follow-section-head { align-items: flex-start; flex-direction: column; }
  .robot-video-stage { min-height: 210px; }
  .robot-video-error { padding: 20px; }
  .robot-video-stage__hud { left: 10px; right: 10px; bottom: 10px; }
}
</style>
