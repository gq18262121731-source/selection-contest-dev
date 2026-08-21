import type { HealthSample } from "../api/client";

export type RiskLevel = "high" | "medium" | "low" | "unknown";

export function evaluateRisk(sample: HealthSample | null | undefined, status?: string): RiskLevel {
  if (status === "offline") return "high";
  if (!sample) return "unknown";

  if (
    sample.sos_flag ||
    sample.heart_rate > 180 ||
    sample.heart_rate < 45 ||
    sample.blood_oxygen < 90 ||
    sample.temperature >= 38.5
  ) {
    return "high";
  }

  if (
    sample.heart_rate > 120 ||
    sample.heart_rate < 55 ||
    sample.blood_oxygen < 93 ||
    sample.temperature >= 37.6
  ) {
    return "medium";
  }

  return "low";
}

export function riskLabel(level: RiskLevel): string {
  if (level === "high") return "高风险";
  if (level === "medium") return "需关注";
  if (level === "low") return "稳定";
  return "待同步";
}

export function riskWeight(level: RiskLevel): number {
  if (level === "high") return 4;
  if (level === "medium") return 3;
  if (level === "low") return 2;
  return 1;
}
