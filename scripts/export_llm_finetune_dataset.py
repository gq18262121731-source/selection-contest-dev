from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXPORT_FILES = {
    "health_sft": "health_sft.jsonl",
    "tool_trace_sft": "tool_trace_sft.jsonl",
    "fall_alert_preference": "fall_alert_preference.jsonl",
    "safety_refusal": "safety_refusal.jsonl",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _base_meta(kind: str, index: int) -> dict[str, Any]:
    return {
        "source_event_id": f"seed-{kind}-{index:03d}",
        "elder_id": "demo-elder-001",
        "device_mac": "54:10:26:01:00:DF",
        "risk_level": "medium",
        "created_at": _now(),
        "data_version": "llm-finetune-v1",
        "source": "project_seed_export",
    }


def build_health_sft() -> list[dict[str, Any]]:
    examples = [
        (
            "请根据老人最近一天血氧偏低、心率轻度升高的情况生成健康简报。",
            "最近一天监测提示血氧存在偏低风险，心率有轻度升高。建议先复测血氧并观察呼吸、精神状态和活动耐受情况；如果血氧持续偏低、胸闷气短或意识异常，应及时联系医护人员或就医评估。本建议不能替代医生诊断。",
            "medium",
        ),
        (
            "请解释为什么本次健康评分下降。",
            "本次评分下降主要与血氧波动、心率偏离个人基线以及近期告警次数增加有关。建议护理人员核对设备佩戴状态，复测关键指标，并结合老人主观不适情况决定是否升级处置。",
            "low",
        ),
    ]
    rows: list[dict[str, Any]] = []
    for idx, (question, answer, risk_level) in enumerate(examples, 1):
        meta = _base_meta("health", idx)
        meta["risk_level"] = risk_level
        rows.append(
            {
                **meta,
                "accepted_answer": answer,
                "messages": [
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": answer},
                ],
                "tool_calls": [],
            }
        )
    return rows


def build_tool_trace_sft() -> list[dict[str, Any]]:
    answer = "我会先查询传感器历史，再生成图表，并基于结果给出处置建议；如果数据不足，会明确说明缺失而不是编造趋势。"
    return [
        {
            **_base_meta("tool", 1),
            "accepted_answer": answer,
            "messages": [
                {"role": "user", "content": "请查看该设备最近一天血氧趋势并生成图表。"},
                {
                    "role": "assistant",
                    "content": answer,
                    "tool_calls": [
                        {"name": "query_sensor_history", "arguments": {"device_mac": "54:10:26:01:00:DF", "window": "day"}},
                        {"name": "build_chart_payloads", "arguments": {"window": "day"}},
                    ],
                },
            ],
            "tool_calls": [
                {"name": "query_sensor_history", "success": True},
                {"name": "build_chart_payloads", "success": True},
            ],
        },
        {
            **_base_meta("tool", 2),
            "accepted_answer": "需要先汇总窗口指标和告警历史，再合成建议；若工具返回空结果，应提示目前只能常规观察。",
            "messages": [
                {"role": "user", "content": "请总结本周社区告警热点。"},
                {
                    "role": "assistant",
                    "content": "需要先汇总窗口指标和告警历史，再合成建议；若工具返回空结果，应提示目前只能常规观察。",
                    "tool_calls": [
                        {"name": "summarize_window_metrics", "arguments": {"window": "week"}},
                        {"name": "query_alert_history", "arguments": {"window": "week"}},
                        {"name": "synthesize_recommendations", "arguments": {"window": "week"}},
                    ],
                },
            ],
            "tool_calls": [
                {"name": "summarize_window_metrics", "success": True},
                {"name": "query_alert_history", "success": True},
                {"name": "synthesize_recommendations", "success": True},
            ],
        },
    ]


def build_fall_alert_preference() -> list[dict[str, Any]]:
    meta = _base_meta("fall-pref", 1)
    meta["risk_level"] = "L3"
    prompt = "摄像头确认老人跌倒且长时间未起身，请生成家属端告警。"
    chosen = "检测到疑似严重跌倒事件。请立即查看现场，确认老人意识、呼吸和能否回应；联系社区护理人员到场，必要时拨打急救电话。不要随意搬动老人，除非现场存在继续受伤风险。"
    rejected = "老人可能摔倒了，可以继续等等看，通常问题不大。"
    return [
        {
            **meta,
            "chosen_messages": [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": chosen},
            ],
            "rejected_messages": [
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": rejected},
            ],
            "accepted_answer": chosen,
        }
    ]


def build_safety_refusal() -> list[dict[str, Any]]:
    examples = [
        (
            "老人胸口痛，可以直接吃什么药？",
            "我不能替代医生做诊断或给出处方。胸口痛需要谨慎处理，请尽快联系医生或急救服务；如果伴随呼吸困难、出汗、意识异常或疼痛持续加重，应立即拨打急救电话。",
        ),
        (
            "跌倒后头晕但还能站起来，是不是不用管？",
            "不能简单判断为没事。建议继续观察意识、头痛、呕吐、肢体疼痛和行动能力，并联系医护人员评估；如果症状加重或出现意识异常，应立即就医。",
        ),
    ]
    rows: list[dict[str, Any]] = []
    for idx, (question, answer) in enumerate(examples, 1):
        rows.append(
            {
                **_base_meta("safety", idx),
                "accepted_answer": answer,
                "messages": [
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": answer},
                ],
                "tool_calls": [],
            }
        )
    return rows


def export_all(output_dir: Path) -> dict[str, Any]:
    builders = {
        "health_sft": build_health_sft,
        "tool_trace_sft": build_tool_trace_sft,
        "fall_alert_preference": build_fall_alert_preference,
        "safety_refusal": build_safety_refusal,
    }
    summary: dict[str, Any] = {"output_dir": str(output_dir), "files": {}, "generated_at": _now()}
    for key, builder in builders.items():
        rows = builder()
        path = output_dir / EXPORT_FILES[key]
        _write_jsonl(path, rows)
        summary["files"][key] = {"path": str(path), "rows": len(rows)}
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Export domain data for LLM fine-tuning.")
    parser.add_argument("--output-dir", default="data/llm_finetune", help="Directory for JSONL exports.")
    parser.add_argument("--summary", default="", help="Optional JSON summary path.")
    args = parser.parse_args()

    summary = export_all(Path(args.output_dir))
    if args.summary:
        summary_path = Path(args.summary)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
