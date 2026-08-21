export function riskLevelToChinese(level?: string | null): string {
  const raw = String(level ?? "").trim();
  if (!raw) return "待评估";

  const s = raw.toLowerCase();

  if (s === "unknown" || s === "待评估" || s === "none") return "待评估";
  if (s === "待分析".toLowerCase() || raw.includes("待分析")) return "待分析";
  if (s === "待同步".toLowerCase() || raw.includes("待同步")) return "待同步";

  // critical/high => 高风险
  if (s === "critical" || s === "high" || s === "danger") return "高风险";

  // warning/attention/medium => 中风险
  if (s === "warning" || s === "attention" || s === "medium") return "中风险";

  // low => 低风险；stable/normal => 稳定
  if (s === "low") return "低风险";
  if (s === "stable" || s === "normal") return "稳定";

  // Already chinese or other variants.
  if (raw.includes("风险") || raw.includes("关注") || raw.includes("平稳") || raw.includes("稳定")) return raw;

  return "待评估";
}

