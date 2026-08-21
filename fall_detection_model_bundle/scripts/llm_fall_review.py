from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from config_utils import load_yaml


ROOT = Path(__file__).resolve().parents[1]


def image_to_data_url(image_path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(image_path))
    if mime is None:
        mime = "image/jpeg"
    data = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{data}"


def compact_detection_context(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"raw_text": path.read_text(encoding="utf-8")[:4000]}
    detections = data.get("detections", data)
    if isinstance(detections, list):
        return {
            "detections": [
                {
                    "person_id": item.get("person_id"),
                    "bbox": item.get("bbox"),
                    "posture_label": item.get("posture_label"),
                    "posture_score": item.get("posture_score"),
                    "detector_label": item.get("detector_label"),
                    "detector_score": item.get("detector_score"),
                    "fall_score": item.get("fall_score"),
                    "risk_level": item.get("risk_level"),
                }
                for item in detections[:5]
                if isinstance(item, dict)
            ]
        }
    return data if isinstance(data, dict) else {"data": data}


def build_payload(args: argparse.Namespace, config: dict[str, Any], model: str, json_mode: bool) -> dict[str, Any]:
    detection_context = compact_detection_context(Path(args.detection_json) if args.detection_json else None)
    prompt = {
        "task": "请作为跌倒检测系统的视觉复核模型，判断图片中是否存在真实摔倒或倒地风险。",
        "requirements": [
            "结合图片视觉内容和检测模型给出的结构化结果判断。",
            "重点区分真实摔倒、躺下休息、坐下、弯腰、运动、遮挡导致的误报。",
            "只输出 JSON，不要输出 Markdown。",
        ],
        "expected_json_schema": {
            "judgement": "real_fall | suspected_fall | no_fall | unclear",
            "confidence": "high | medium | low",
            "severity": "L0 | L1 | L2 | L3 | L4",
            "reason": "简短中文原因",
            "suggestion": "无需处理 | 继续观察 | 通知管理员 | 立即处理 | 呼叫紧急联系人",
            "visible_person_count": 0,
            "likely_false_alarm_type": "none | sitting | lying_rest | bending | exercise | occlusion | camera_angle | other",
        },
        "model_detection_context": detection_context,
    }
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "你是跌倒检测系统的多模态复核助手，必须谨慎、保守、输出合法 JSON。",
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": json.dumps(prompt, ensure_ascii=False)},
                    {"type": "image_url", "image_url": {"url": image_to_data_url(Path(args.image))}},
                ],
            },
        ],
        "temperature": float(args.temperature if args.temperature is not None else config.get("temperature", 0.1)),
        "max_tokens": int(args.max_tokens or config.get("max_tokens", 512)),
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    return payload


def call_siliconflow(payload: dict[str, Any], config: dict[str, Any], api_key: str) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        config.get("base_url", "https://api.siliconflow.cn/v1/chat/completions"),
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    timeout = int(config.get("timeout_seconds", 60))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"SiliconFlow API error {exc.code}: {detail}") from exc


def parse_review(response: dict[str, Any]) -> dict[str, Any]:
    content = response["choices"][0]["message"]["content"]
    if isinstance(content, str):
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            start = content.find("{")
            end = content.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(content[start : end + 1])
                except json.JSONDecodeError:
                    pass
            return {"raw_response": content}
    return {"raw_response": content}


def normalize_review(review: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "judgement",
        "confidence",
        "severity",
        "reason",
        "suggestion",
        "visible_person_count",
        "likely_false_alarm_type",
    ]
    if all(key in review for key in ["judgement", "confidence", "severity"]):
        return {key: review.get(key) for key in keys if key in review}
    return review


def review_with_fallback(args: argparse.Namespace, config: dict[str, Any], api_key: str) -> tuple[dict[str, Any], dict[str, Any], str | None]:
    primary_model = args.model or config.get("model", "Qwen/Qwen3-VL-8B-Instruct")
    free_model = config.get("free_fallback_model")
    primary_json_mode = not (primary_model == free_model and not bool(config.get("free_fallback_supports_json_mode", False)))
    attempts = [(primary_model, primary_json_mode)]
    if args.enable_free_fallback:
        if free_model and free_model != primary_model:
            attempts.append((free_model, bool(config.get("free_fallback_supports_json_mode", False))))
    elif config.get("fallback_model") and config.get("fallback_model") != primary_model:
        attempts.append((config["fallback_model"], True))

    last_error = None
    for model, json_mode in attempts:
        payload = build_payload(args, config, model, json_mode)
        try:
            response = call_siliconflow(payload, config, api_key)
            return response, payload, last_error
        except Exception as exc:
            last_error = f"{model}: {exc}"
            continue
    raise RuntimeError(f"All SiliconFlow review models failed. Last error: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Use a SiliconFlow vision-language model to review a fall alert image.")
    parser.add_argument("--image", required=True)
    parser.add_argument("--detection-json", default=None)
    parser.add_argument("--config", default=str(ROOT / "configs" / "llm_review.yaml"))
    parser.add_argument("--model", default=None)
    parser.add_argument("--enable-free-fallback", action="store_true", default=True)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--output", default=str(ROOT / "outputs" / "llm_fall_review.json"))
    args = parser.parse_args()

    api_key = os.environ.get("SILICONFLOW_API_KEY")
    if not api_key:
        raise RuntimeError("Missing SILICONFLOW_API_KEY environment variable.")

    config = load_yaml(args.config)
    response, payload, fallback_error = review_with_fallback(args, config, api_key)
    review = normalize_review(parse_review(response))
    result = {
        "model": payload["model"],
        "fallback_from_error": fallback_error,
        "image": str(args.image),
        "review": review,
        "usage": response.get("usage", {}),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
