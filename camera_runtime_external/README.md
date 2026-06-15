# LLM fine-tune dataset bundle

This folder was prepared for the `D:/code/health` project on 2026-04-30.

## Included sources
- Single-turn: cMedQA2, Huatuo26M-Lite
- Multi-turn: CMtMedQA

## Output files
- `processed/single_turn_public_zh_medical.jsonl`: merged single-turn QA pairs
- `processed/single_turn_monitoring_focus_zh_medical.jsonl`: single-turn subset filtered by monitoring / elder-care keywords
- `processed/multi_turn_public_zh_medical.jsonl`: merged multi-turn consultations
- `processed/multi_turn_monitoring_focus_zh_medical.jsonl`: multi-turn subset filtered by monitoring / elder-care keywords
- `manifest.json`: source-level counts and metadata

## Record format
- Each row is JSON with `messages` in chat format and source metadata preserved.
- Original split names are retained in `source_split`.

## Project fit
- The public corpora are medical-consultation data, not elder-care monitoring data.
- For this repo, the most useful entry point is the `monitoring_focus` subset.
- For production-facing tuning, add a second-stage project-specific SFT set from your own prompts, device alerts, family/community roles, and report outputs.

## License notes
- Apache-2.0: 1 source(s)
- GPL-3.0 and non-commercial research note: 1 source(s)
- MIT: 1 source(s)
- Review each upstream source before commercial or production deployment.

## Keyword filter
- Focus keywords: 老人, 老年, 家属, 社区, 监测, 随访, 复测, 告警, 预警, 心率, 脉搏, 血压, 高血压, 低血压, 血氧, 低氧, 缺氧, 呼吸, 呼吸困难, 胸闷, 胸痛, 晕厥, 跌倒, 意识

## Counts
- Single-turn total: 285478
- Single-turn focus subset: 28138
- Multi-turn total: 66242
- Multi-turn focus subset: 2498
