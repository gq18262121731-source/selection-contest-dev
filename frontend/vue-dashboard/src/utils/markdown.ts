import MarkdownIt from "markdown-it";

const markdown = new MarkdownIt({
  html: true,
  breaks: true,
  linkify: true,
  typographer: false,
});

type RenderMarkdownOptions = {
  /**
   * For streaming scenarios: the content may end mid-block (e.g. an unclosed code fence).
   * We try to "balance" common fences so the preview stays stable.
   */
  streaming?: boolean;
};

/**
 * Strips outer ```markdown / ```md wrapper fences that many LLMs emit
 * around their entire response. Handles leading/trailing whitespace,
 * partial fences during streaming, and multiple wrapper layers.
 *
 * Also handles cases where the fence might not be at position 0
 * (e.g. the LLM starts with a brief line before the fence).
 */
export function unwrapOuterMarkdownFence(input: string): string {
  let text = String(input ?? "").trim();
  let maxIterations = 3;
  while (maxIterations-- > 0) {
    const openingRegex = /\s*(```|~~~)(?:markdown|md)\s*\r?\n/i;
    const match = text.match(openingRegex);
    
    if (match) {
      const fenceStart = match.index;
      // If the fence is found VERY late in the text, it's probably NOT an outer wrapper.
      if (fenceStart !== undefined && fenceStart > 200) {
        break;
      }
      
      const fence = match[1];
      const preamble = text.slice(0, fenceStart).trim();
      const contentAfterOpening = text.slice(fenceStart + match[0].length);
      
      const closingPattern = new RegExp(`(?:\\r?\\n)${fence}\\s*(?:\\r?\\n|$)`, 'g');
      let lastMatch = null;
      let m;
      while ((m = closingPattern.exec(contentAfterOpening)) !== null) {
        lastMatch = m;
      }
      
      if (lastMatch) {
         const beforeClose = contentAfterOpening.slice(0, lastMatch.index);
         const afterClose = contentAfterOpening.slice(lastMatch.index + lastMatch[0].length);
         const body = `${beforeClose}\n${afterClose}`.trim();
         text = preamble ? `${preamble}\n\n${body}` : body;
      } else {
         const body = contentAfterOpening.trim();
         text = preamble ? `${preamble}\n\n${body}` : body;
      }
      continue;
    }
    break;
  }
  return text;
}

/**
 * Balances unclosed code fences so markdown-it doesn't treat
 * everything after an opening fence as a code block.
 */
function balanceCodeFences(input: string): string {
  let text = String(input ?? "");

  // Balance triple-backtick fenced code blocks.
  // Only count fences that appear at the start of a line.
  const backtickFences = text.match(/^```/gm) ?? [];
  if (backtickFences.length % 2 === 1) {
    text = text + "\n```\n";
  }

  // Balance triple-tilde fenced code blocks.
  const tildeFences = text.match(/^~~~/gm) ?? [];
  if (tildeFences.length % 2 === 1) {
    text = `${text}\n~~~\n`;
  }

  return text;
}

/**
 * When streaming, the text may end mid-inline-element.
 * This function patches common broken structures so the visible
 * preview stays readable rather than showing raw markdown tokens.
 */
function patchStreamingArtifacts(input: string): string {
  let text = input;

  // Close unclosed bold markers: odd count of **
  const boldCount = (text.match(/\*\*/g) ?? []).length;
  if (boldCount % 2 === 1) {
    text += "**";
  }

  // Close unclosed italic markers: odd count of single * (that aren't part of **)
  // We use a simple heuristic: check the last line for a trailing single *
  const lastLine = text.split("\n").pop() ?? "";
  const singleStarCount = (lastLine.replace(/\*\*/g, "").match(/\*/g) ?? []).length;
  if (singleStarCount % 2 === 1) {
    text += "*";
  }

  // Close unclosed inline code: odd count of single `
  const inlineCodeCount = (text.replace(/```/g, "").match(/`/g) ?? []).length;
  if (inlineCodeCount % 2 === 1) {
    text += "`";
  }

  return text;
}

/**
 * Normalizes common LLM markdown quirks so that markdown-it can parse
 * tables, headings, and lists correctly.
 */
function normalizeMarkdown(input: string): string {
  let text = String(input ?? "");

  // 1. Remove emulated "horizontal lines" or extra dashes that often break table detection
  //    if they are directly glued to the table pipe.
  //    e.g. "-------------------|| 1 |" -> "\n\n| 1 |"
  text = text.replace(/^-{3,}(\|{1,2})/gm, "\n\n|");

  // 2. Fix double pipes at start of line which confuse standard parsers
  text = text.replace(/^\|\|/gm, "|");

  // 3. Ensure a blank line BEFORE a table header row.
  //    Markdown-it is strict: a table must be preceded by a blank line.
  //    Pattern: non-blank line → table header (| ... |) → separator (| --- | ... |)
  text = text.replace(
    /([^\n])\n(\|[^\n]+\|\s*\n\s*\|[\s:]*-{2,}[\s:]*\|)/g,
    "$1\n\n$2",
  );

  // 4. Ensure a blank line AFTER a table (before non-table content)
  //    This prevents the next paragraph from being swallowed into the table.
  text = text.replace(
    /(\|[^\n]+\|\s*\n)([^\s|])/g,
    "$1\n$2",
  );

  // 5. Ensure blank lines before headings (# ... ##)
  //    LLMs frequently glue headings directly to paragraphs.
  text = text.replace(/([^\n])\n(#{1,6}\s)/g, "$1\n\n$2");

  // 6. Ensure blank lines before list items that come after a paragraph
  text = text.replace(/([^\n])\n(\s*[-*+]\s)/g, "$1\n\n$2");
  text = text.replace(/([^\n])\n(\s*\d+\.\s)/g, "$1\n\n$2");

  // 7. Ensure blank line before blockquotes
  text = text.replace(/([^\n>])\n(>\s)/g, "$1\n\n$2");

  // 8. Normalize bold markers that LLMs sometimes emit with extra spaces
  //    e.g. "** 标题 **" → "**标题**"
  text = text.replace(/\*\*\s+/g, "**");
  text = text.replace(/\s+\*\*/g, "**");

  // 9. Collapse 3+ consecutive blank lines into 2 (keeps structure clean)
  text = text.replace(/\n{4,}/g, "\n\n\n");

  return text;
}

export function renderMarkdown(content: string, options: RenderMarkdownOptions = {}): string {
  const text = String(content ?? "");
  const trimmed = text.trim();
  if (!trimmed) return "";

  // Strip outer ```markdown wrapper fences — always, not just streaming
  let processed = unwrapOuterMarkdownFence(trimmed);
  // Normalize before balancing fences
  processed = normalizeMarkdown(processed);
  // Always balance code fences — LLMs can produce unbalanced fences even
  // in completed responses, causing the entire tail of the answer to render
  // as a giant <code> block instead of formatted markdown.
  processed = balanceCodeFences(processed);
  if (options.streaming) {
    processed = patchStreamingArtifacts(processed);
  }

  return markdown.render(processed);
}
