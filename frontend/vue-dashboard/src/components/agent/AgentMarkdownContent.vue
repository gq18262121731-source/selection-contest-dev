<script setup lang="ts">
import { ref, watch, nextTick } from "vue";
import { renderMarkdown } from "../../utils/markdown";

const props = withDefaults(
  defineProps<{
    content: string;
    variant?: "bubble" | "report";
    streaming?: boolean;
  }>(),
  {
    variant: "report",
    streaming: false,
  },
);

const renderedHtml = ref("");

let timer: ReturnType<typeof setTimeout> | null = null;
const DEBOUNCE_MS = 32;

function updateRenderedHtml(forceNonStreaming = false) {
  const streaming = forceNonStreaming
    ? false
    : props.streaming || props.variant === "report";
  renderedHtml.value = renderMarkdown(props.content, { streaming });
}

// streaming 结束 (true->false) 或 variant 切换时，立即做完整渲染，
// 确保最终内容是正确的 HTML 而非残留的原始 markdown。
watch(
  () => [props.variant, props.streaming],
  (_next, prev) => {
    if (timer) clearTimeout(timer);
    updateRenderedHtml();
    // streaming 刚结束时，连续两帧兜底渲染（非流式模式），
    // 防止 content 尾部 delta 未合入或 watcher 执行顺序不确定。
    if (prev && prev[1] === true && !props.streaming) {
      nextTick(() => {
        updateRenderedHtml(true);
        nextTick(() => updateRenderedHtml(true));
      });
    }
  },
);

watch(
  () => props.content,
  (value) => {
    const text = String(value ?? "");
    if (!text.trim()) {
      renderedHtml.value = "";
      return;
    }

    // 流式结束后，任何 content 变化都立即渲染（最终答案设置）
    if (!props.streaming) {
      if (timer) clearTimeout(timer);
      updateRenderedHtml(true);
      return;
    }

    // 流式输出中：每次 delta 都立即渲染，保证用户永远看到 HTML 而非原始 markdown
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => updateRenderedHtml(), DEBOUNCE_MS);
    // 首次或短文本立即渲染，无需等待 debounce
    if (renderedHtml.value === "" || text.length < 300) {
      updateRenderedHtml();
    }
  },
  { immediate: true },
);
</script>

<template>
  <div
    class="agent-markdown"
    :class="`agent-markdown--${variant}`"
    v-html="renderedHtml"
  />
</template>

<style scoped>
.agent-markdown {
  color: var(--text-main);
  line-height: 1.85;
  overflow-x: auto;
  overflow-wrap: anywhere;
}

.agent-markdown--bubble {
  font-size: 1.22rem;
}

.agent-markdown--report {
  font-size: 1.28rem;
  line-height: 1.9;
}

.agent-markdown :deep(*:first-child) {
  margin-top: 0;
}

.agent-markdown :deep(*:last-child) {
  margin-bottom: 0;
}

.agent-markdown :deep(h1),
.agent-markdown :deep(h2),
.agent-markdown :deep(h3),
.agent-markdown :deep(h4),
.agent-markdown :deep(h5),
.agent-markdown :deep(h6) {
  margin: 1.5em 0 0.6em;
  color: #1e293b;
  line-height: 1.35;
  letter-spacing: -0.01em;
  font-weight: 700;
}

.agent-markdown :deep(h1) {
  font-size: 1.9rem;
  padding-bottom: 0.4em;
  border-bottom: 1px solid #e2e8f0;
}

.agent-markdown :deep(h2) {
  font-size: 1.62rem;
}

.agent-markdown :deep(h3) {
  font-size: 1.42rem;
}

.agent-markdown :deep(h4) {
  font-size: 1.3rem;
}

.agent-markdown :deep(p),
.agent-markdown :deep(ul),
.agent-markdown :deep(ol),
.agent-markdown :deep(blockquote),
.agent-markdown :deep(pre),
.agent-markdown :deep(table),
.agent-markdown :deep(hr) {
  margin: 1em 0;
}

.agent-markdown :deep(ul),
.agent-markdown :deep(ol) {
  padding-left: 1.5rem;
}

.agent-markdown :deep(li + li) {
  margin-top: 0.45rem;
}

.agent-markdown :deep(li) {
  font-size: 1.18rem;
}

.agent-markdown :deep(li::marker) {
  color: #64748b;
}

.agent-markdown :deep(strong) {
  color: #0f172a;
  font-weight: 700;
}

.agent-markdown :deep(blockquote) {
  margin-left: 0;
  padding: 0.85rem 1.1rem;
  border-left: 4px solid var(--brand, #3b82f6);
  border-radius: 4px 12px 12px 4px;
  background: #f8fafc;
  color: #475569;
  font-style: normal;
  font-size: 1.15rem;
}

.agent-markdown :deep(code) {
  padding: 0.2rem 0.45rem;
  border-radius: 0.375rem;
  background: #f1f5f9;
  color: #0f172a;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 0.88em;
}

.agent-markdown :deep(pre) {
  padding: 1.1rem;
  border-radius: 0.75rem;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  color: #334155;
  overflow-x: auto;
  font-size: 1.05rem;
}

.agent-markdown :deep(pre code) {
  padding: 0;
  background: transparent;
  color: inherit;
  border: none;
  font-size: 0.9em;
}

.agent-markdown :deep(table) {
  width: 100%;
  margin: 1.5rem 0;
  border-collapse: separate;
  border-spacing: 0;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  overflow: hidden;
  font-size: 1.15rem;
  table-layout: auto;
}

.agent-markdown :deep(thead) {
  background: #f8fafc;
}

.agent-markdown :deep(thead th) {
  color: #334155;
  font-weight: 600;
  text-align: left;
  padding: 0.9rem 1.1rem;
  border-bottom: 1px solid #e2e8f0;
  white-space: nowrap;
  font-size: 1.1rem;
}

.agent-markdown :deep(td) {
  padding: 0.9rem 1.1rem;
  border-bottom: 1px solid #e2e8f0;
  color: #475569;
  vertical-align: top;
  line-height: 1.65;
  font-size: 1.1rem;
}

.agent-markdown :deep(tr:nth-child(even) td) {
  background: #fcfcfc;
}

.agent-markdown :deep(tr:hover td) {
  background: #f1f5f9;
}

.agent-markdown :deep(tr:last-child td) {
  border-bottom: 0;
}

.agent-markdown :deep(hr) {
  border: 0;
  border-top: 1px solid #e2e8f0;
  margin: 2rem 0;
}

.agent-markdown :deep(a) {
  color: #0f766e;
  text-decoration: none;
  font-weight: 500;
}

.agent-markdown :deep(a:hover) {
  text-decoration: underline;
}
</style>
