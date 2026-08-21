<script setup lang="ts">
import { computed, ref } from "vue";

import { getMainSystemBaseUrl, getVisionHealthEndpoint } from "../api/client";

type VisionHealthPayload = Record<string, unknown>;

const loading = ref(false);
const errorMessage = ref("");
const payload = ref<VisionHealthPayload | null>(null);
const rawResponse = ref("");

const mainSystemUrl = computed(() => getMainSystemBaseUrl());

const visionServiceUrl = computed(() => {
  const data = payload.value;
  if (!data) return "unknown";

  const topLevelBaseUrl = data.base_url;
  if (typeof topLevelBaseUrl === "string" && topLevelBaseUrl.trim()) {
    return topLevelBaseUrl;
  }

  const visionService = asRecord(data.vision_service);
  const nestedBaseUrl = visionService?.base_url;
  if (typeof nestedBaseUrl === "string" && nestedBaseUrl.trim()) {
    return nestedBaseUrl;
  }

  const nestedUrl = visionService?.url;
  if (typeof nestedUrl === "string" && nestedUrl.trim()) {
    try {
      const parsed = new URL(nestedUrl, window.location.origin);
      return parsed.origin;
    } catch {
      return nestedUrl;
    }
  }

  return "unknown";
});

const cameraId = computed(() => {
  const data = payload.value;
  if (!data) return "unknown";

  const directCameraId = data.camera_id;
  if (typeof directCameraId === "string" && directCameraId.trim()) {
    return directCameraId;
  }

  const defaultCameraId = data.default_camera_id;
  if (typeof defaultCameraId === "string" && defaultCameraId.trim()) {
    return defaultCameraId;
  }

  const visionService = asRecord(data.vision_service);
  const nestedCameraId = visionService?.camera_id;
  if (typeof nestedCameraId === "string" && nestedCameraId.trim()) {
    return nestedCameraId;
  }

  return "camera_01";
});

const connectionStatus = computed(() => {
  if (errorMessage.value) {
    return errorMessage.value;
  }

  const data = payload.value;
  if (!data) return "unknown";

  const directStatus = data.status;
  if (typeof directStatus === "string" && directStatus.trim()) {
    return directStatus;
  }

  const visionService = asRecord(data.vision_service);
  const nestedStatus = visionService?.status;
  if (typeof nestedStatus === "string" && nestedStatus.trim()) {
    return nestedStatus;
  }

  const nestedReason = visionService?.reason;
  if (typeof nestedReason === "string" && nestedReason.trim()) {
    return nestedReason;
  }

  return "unknown";
});

const formattedRawResponse = computed(() => rawResponse.value.trim() || "暂无响应");

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function normalizeRawResponse(data: unknown): string {
  if (typeof data === "string") {
    return data;
  }
  if (data == null) {
    return "";
  }
  try {
    return JSON.stringify(data, null, 2);
  } catch {
    return String(data);
  }
}

function statusTone(status: string) {
  if (status === "ok" || status === "online") return "success";
  if (status === "degraded") return "warning";
  if (
    status === "unavailable" ||
    status === "timeout" ||
    status === "connection_error" ||
    status === "主系统不可达" ||
    status === "请求超时" ||
    status === "响应格式异常"
  ) {
    return "error";
  }
  return "neutral";
}

async function testConnection() {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), 3000);

  loading.value = true;
  errorMessage.value = "";
  payload.value = null;
  rawResponse.value = "";

  try {
    const response = await fetch(getVisionHealthEndpoint(), {
      method: "GET",
      signal: controller.signal,
      headers: { "Cache-Control": "no-store" },
    });
    const rawText = await response.text();
    rawResponse.value = rawText;

    if (!response.ok) {
      errorMessage.value = "主系统不可达";
      return;
    }

    if (!rawText.trim()) {
      errorMessage.value = "响应格式异常";
      return;
    }

    try {
      const parsed = JSON.parse(rawText) as unknown;
      const record = asRecord(parsed);
      if (!record) {
        errorMessage.value = "响应格式异常";
        return;
      }
      payload.value = record;
      rawResponse.value = JSON.stringify(record, null, 2);
    } catch {
      errorMessage.value = "响应格式异常";
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      errorMessage.value = "请求超时";
    } else {
      errorMessage.value = "主系统不可达";
    }
    rawResponse.value = normalizeRawResponse(error);
  } finally {
    window.clearTimeout(timeoutId);
    loading.value = false;
  }
}

async function copySummary() {
  const summary = [
    "Main System:",
    mainSystemUrl.value,
    "",
    "Vision Service:",
    visionServiceUrl.value,
    "",
    "Camera ID:",
    cameraId.value,
    "",
    "Status:",
    connectionStatus.value,
    "",
    "Time:",
    new Date().toISOString(),
  ].join("\n");

  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(summary);
    return;
  }

  const textarea = document.createElement("textarea");
  textarea.value = summary;
  textarea.setAttribute("readonly", "true");
  textarea.style.position = "absolute";
  textarea.style.left = "-9999px";
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand("copy");
  document.body.removeChild(textarea);
}
</script>

<template>
  <article class="panel integration-debug-card">
    <div class="integration-debug-card__header">
      <div>
        <p class="section-eyebrow">Integration Debug</p>
        <h2>联调地址确认</h2>
        <p class="subtle-copy">
          只通过主系统的 <code>/api/v1/vision/health</code> 核对当前前端、主系统和 Vision Service 的链路状态。
        </p>
      </div>
      <div class="integration-debug-card__actions">
        <button type="button" class="ghost-btn" :disabled="loading" @click="testConnection">
          {{ loading ? "测试中..." : "测试连接" }}
        </button>
        <button type="button" class="ghost-btn" @click="copySummary">复制联调摘要</button>
      </div>
    </div>

    <div class="integration-debug-card__grid">
      <section class="integration-debug-card__field">
        <span>主系统地址</span>
        <strong>{{ mainSystemUrl }}</strong>
      </section>
      <section class="integration-debug-card__field">
        <span>Vision Service 地址</span>
        <strong>{{ visionServiceUrl }}</strong>
      </section>
      <section class="integration-debug-card__field">
        <span>camera_id</span>
        <strong>{{ cameraId }}</strong>
      </section>
      <section class="integration-debug-card__field">
        <span>连接状态</span>
        <strong :data-tone="statusTone(connectionStatus)">{{ connectionStatus }}</strong>
      </section>
    </div>

    <p v-if="errorMessage" class="integration-debug-card__feedback integration-debug-card__feedback--error">
      {{ errorMessage }}
    </p>

    <details class="integration-debug-card__details">
      <summary>原始响应</summary>
      <pre>{{ formattedRawResponse }}</pre>
    </details>
  </article>
</template>

<style scoped>
.integration-debug-card {
  display: grid;
  gap: 20px;
}

.integration-debug-card__header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.integration-debug-card__header h2 {
  margin: 6px 0 10px;
  color: #0f172a;
}

.integration-debug-card__header code {
  padding: 0.15rem 0.4rem;
  border-radius: 999px;
  background: #e0f2fe;
  color: #0f172a;
  font-size: 0.82rem;
}

.integration-debug-card__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.integration-debug-card__grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.integration-debug-card__field {
  display: grid;
  gap: 8px;
  padding: 16px;
  border-radius: 18px;
  border: 1px solid #dbe4f0;
  background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
}

.integration-debug-card__field span {
  color: #64748b;
  font-size: 0.84rem;
  font-weight: 700;
}

.integration-debug-card__field strong {
  color: #0f172a;
  font-size: 0.98rem;
  line-height: 1.5;
  word-break: break-word;
}

.integration-debug-card__field strong[data-tone="success"] {
  color: #15803d;
}

.integration-debug-card__field strong[data-tone="warning"] {
  color: #b45309;
}

.integration-debug-card__field strong[data-tone="error"] {
  color: #dc2626;
}

.integration-debug-card__feedback {
  margin: 0;
  padding: 12px 14px;
  border-radius: 14px;
  font-size: 0.92rem;
  font-weight: 600;
}

.integration-debug-card__feedback--error {
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.18);
  color: #dc2626;
}

.integration-debug-card__details {
  border-top: 1px solid #e2e8f0;
  padding-top: 14px;
}

.integration-debug-card__details summary {
  cursor: pointer;
  color: #1e3a8a;
  font-weight: 700;
}

.integration-debug-card__details pre {
  margin: 12px 0 0;
  padding: 14px;
  border-radius: 16px;
  background: #0f172a;
  color: #e2e8f0;
  font-size: 0.8rem;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-x: auto;
}

@media (max-width: 1080px) {
  .integration-debug-card__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 760px) {
  .integration-debug-card__header {
    flex-direction: column;
  }

  .integration-debug-card__actions {
    width: 100%;
  }

  .integration-debug-card__grid {
    grid-template-columns: 1fr;
  }
}
</style>
