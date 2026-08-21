from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from backend.config import Settings
from backend.schemas.health_insight_schema import HealthScoreInsightRequest, HealthScoreInsightResponse
from backend.services.health_insight_context_service import HealthInsightContextService


logger = logging.getLogger(__name__)


SCORE_NOTICE_FALLBACK = "结构化健康评分模型未完整加载，当前使用规则评分与降级模型评分进行辅助分析。"
TECHNICAL_TEXT_FALLBACK = "结构化健康评分模型未完整加载，当前解释主要依据规则评分、实时体征和趋势结果生成。"
TECHNICAL_PATTERNS = (
    "Missing model artifacts",
    "static_health_model.pt",
    "feature_scaler.joblib",
    "feature_columns.json",
    "Traceback",
    "Exception",
)
PATH_PATTERN = re.compile(r"([A-Za-z]:\\|/(?:home|usr|var|tmp|opt|mnt|data|Users|workspace)/[^\s\]]+)")
RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
VALID_RISK_LEVELS = set(RISK_ORDER)
VALID_CONFIDENCE_LEVELS = {"low", "medium", "high"}
REQUIRED_LLM_FIELDS = {
    "risk_level",
    "summary",
    "score_explanation",
    "trend_analysis",
    "model_assessment",
    "suggested_actions",
    "watch_items",
    "confidence",
}

SYSTEM_PROMPT = """你是智慧康养社区的健康监护分析助手。
只能基于输入数据分析，不得编造不存在的体征、告警或模型结果。
不得做医学诊断，不得使用“确诊”“治疗方案”等表达。
可以使用“风险提示”“监护建议”“建议联系医护人员”等表达。
如果出现 SOS、跌倒、血氧严重偏低、心率极端、血压极端、体温明显异常，必须优先提示立即核查。
如果数据缺失或数据过期，要明确说明数据可信度受限。
不得重新计算健康分，不得替代规则模型、评分模型和时间序列模型。
输出必须是 JSON，不要输出 Markdown，不要输出额外解释。"""


class HealthLlmInsightService:
    """Generates structured health score insight with LLM-first, rules-safe fallback."""

    def __init__(self, *, settings: Settings, context_service: HealthInsightContextService) -> None:
        self._settings = settings
        self._context_service = context_service

    def generate(self, request: HealthScoreInsightRequest) -> HealthScoreInsightResponse:
        context = self._sanitize_context(self._context_service.build_context(request))
        fallback = self._fallback_response(context)
        if not request.use_llm:
            return fallback

        llm_payload = self._call_llm(context)
        if not llm_payload:
            return fallback

        llm_risk = self._safe_risk_level(llm_payload.get("risk_level"), fallback.risk_level)
        merged = fallback.model_copy(
            update={
                "risk_level": llm_risk,
                "summary": self._safe_text(llm_payload.get("summary"), fallback.summary),
                "score_explanation": self._safe_text(llm_payload.get("score_explanation"), fallback.score_explanation),
                "trend_analysis": self._safe_text(llm_payload.get("trend_analysis"), fallback.trend_analysis),
                "model_assessment": self._safe_text(llm_payload.get("model_assessment"), fallback.model_assessment),
                "suggested_actions": self._safe_list(llm_payload.get("suggested_actions"), fallback.suggested_actions),
                "watch_items": self._safe_list(llm_payload.get("watch_items"), fallback.watch_items),
                "confidence": self._safe_confidence(llm_payload.get("confidence"), fallback.confidence),
                "llm_used": True,
                "fallback_used": False,
            }
        )
        return self._enforce_rule_priority(merged, context)

    def _call_llm(self, context: dict[str, Any]) -> dict[str, Any] | None:
        context = self._sanitize_context(context)
        api_key = self._settings.dashscope_api_key
        if not api_key or not self._settings.tongyi_chat_model:
            return None
        base = self._settings.qwen_api_base.strip() or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        url = base.rstrip("/")
        if not url.endswith("/chat/completions"):
            url = f"{url}/chat/completions"

        body = {
            "model": self._settings.tongyi_chat_model,
            "temperature": 0.1,
            "stream": False,
            "response_format": {"type": "json_object"},
            "messages": self._build_messages(context),
            "max_tokens": 700,
        }
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=max(3, int(self._settings.llm_timeout_seconds))) as response:
                raw = response.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            logger.info("Health score insight LLM call failed; fallback will be used: %s", exc)
            return None

        try:
            payload_json = json.loads(raw)
            content = payload_json["choices"][0]["message"]["content"]
            parsed = json.loads(self._strip_code_fence(str(content)))
            return self._validate_llm_payload(parsed)
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            logger.info("Health score insight LLM response parse failed; fallback will be used: %s", exc)
            return None

    def _build_messages(self, context: dict[str, Any]) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": self._build_user_prompt(context)},
        ]

    @staticmethod
    def _build_user_prompt(context: dict[str, Any]) -> str:
        safe_context = HealthLlmInsightService._sanitize_context(context)
        context_json = json.dumps(safe_context, ensure_ascii=False, default=str, indent=2)
        return (
            "请基于以下 health_context_json 生成健康评分智能解读。"
            "health_context_json 已包含老人姓名、房间号、设备 MAC、最新生命体征、健康评分结果、"
            "规则分、模型分、最终分、稳定化结果、近 window_minutes 分钟趋势摘要、"
            "时间序列模型结果、最近告警和数据新鲜度。"
            "只能解释已有字段，不要补造缺失数据，不要重新计算健康分。\n\n"
            "严格返回如下 JSON 结构：\n"
            '{\n'
            '  "risk_level": "low|medium|high|critical",\n'
            '  "summary": "一句话总结当前状态",\n'
            '  "score_explanation": "解释健康评分、规则分、模型分之间的关系",\n'
            '  "trend_analysis": "解释近一段时间趋势",\n'
            '  "model_assessment": "解释时间序列模型或异常检测模型结果",\n'
            '  "suggested_actions": ["建议动作1", "建议动作2"],\n'
            '  "watch_items": ["后续关注点1", "后续关注点2"],\n'
            '  "confidence": "low|medium|high"\n'
            '}\n\n'
            f"health_context_json:\n{context_json}"
        )

    @staticmethod
    def _validate_llm_payload(payload: Any) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None
        if REQUIRED_LLM_FIELDS - set(payload):
            return None
        if str(payload.get("risk_level") or "").lower() not in VALID_RISK_LEVELS:
            return None
        if str(payload.get("confidence") or "").lower() not in VALID_CONFIDENCE_LEVELS:
            return None
        text_fields = ("summary", "score_explanation", "trend_analysis", "model_assessment")
        if any(not str(payload.get(field) or "").strip() for field in text_fields):
            return None
        if not isinstance(payload.get("suggested_actions"), list) or not isinstance(payload.get("watch_items"), list):
            return None
        return payload

    @staticmethod
    def _has_technical_text(value: Any) -> bool:
        text = str(value or "")
        return any(pattern in text for pattern in TECHNICAL_PATTERNS) or bool(PATH_PATTERN.search(text))

    @classmethod
    def _sanitize_context(cls, value: Any) -> Any:
        if isinstance(value, dict):
            raw_has_technical_text = any(cls._has_technical_text(item) for item in value.values())
            sanitized = {key: cls._sanitize_context(item) for key, item in value.items()}
            if raw_has_technical_text or any(cls._has_technical_text(item) for item in sanitized.values()):
                sanitized["model_artifacts_available"] = False
                sanitized["score_mode"] = sanitized.get("score_mode") or "fallback"
                sanitized["score_notice"] = sanitized.get("score_notice") or SCORE_NOTICE_FALLBACK
            for key in ("message", "error", "score_adjustment_reason", "reason"):
                if key in sanitized and cls._has_technical_text(sanitized[key]):
                    if key in {"message", "error"}:
                        sanitized.pop(key, None)
                    else:
                        sanitized[key] = SCORE_NOTICE_FALLBACK
            return sanitized
        if isinstance(value, list):
            return [cls._sanitize_context(item) for item in value]
        if isinstance(value, str) and cls._has_technical_text(value):
            return TECHNICAL_TEXT_FALLBACK
        return value

    def _fallback_response(self, context: dict[str, Any]) -> HealthScoreInsightResponse:
        score = context.get("health_score") or {}
        trend = context.get("trend") or {}
        model = context.get("time_series_model") or {}
        high_priority = list(context.get("high_priority_reasons") or [])
        risk_level = self._derive_risk(context)
        score_text = self._score_text(score)
        trend_text = self._trend_text(trend)
        model_text = self._model_text(model)
        missing = list(context.get("missing_fields") or [])

        actions = self._actions_for_risk(risk_level)
        if high_priority:
            actions = high_priority + actions
        watch_items = [
            "关注心率是否持续超过阈值",
            "关注血氧、血压和体温是否连续更新",
        ]
        if context.get("data_freshness") in {"missing", "stale"}:
            watch_items.append("当前数据缺失或过期，分析可信度受限")
        if missing:
            watch_items.append(f"以下数据暂缺：{', '.join(missing)}")

        return HealthScoreInsightResponse(
            elder_name=(context.get("elder") or {}).get("elder_name"),
            room_no=(context.get("elder") or {}).get("room_no"),
            device_mac=str(context.get("device_mac") or ""),
            generated_at=datetime.now(timezone.utc),
            data_freshness=context.get("data_freshness") if context.get("data_freshness") in {"fresh", "stale", "missing"} else "missing",
            risk_level=risk_level,
            summary=self._summary_for_risk(risk_level, bool(high_priority), context),
            score_explanation=score_text,
            trend_analysis=trend_text,
            model_assessment=model_text,
            suggested_actions=list(dict.fromkeys(actions))[:6],
            watch_items=list(dict.fromkeys(watch_items))[:6],
            confidence="low" if context.get("data_freshness") == "missing" else "medium",
            llm_used=False,
            fallback_used=True,
        )

    def _derive_risk(self, context: dict[str, Any]) -> str:
        score = context.get("health_score") or {}
        raw = str(score.get("risk_level") or "").lower()
        mapped = {"normal": "low", "attention": "medium", "warning": "high", "critical": "critical"}.get(raw, "low")
        if context.get("data_freshness") == "missing":
            mapped = "medium"
        if context.get("high_priority_reasons"):
            mapped = "critical" if any("critical" in str(item).lower() or "SOS" in str(item) for item in context["high_priority_reasons"]) else "high"
        for alarm in context.get("recent_alarms") or []:
            if alarm.get("alarm_type") in {"sos", "fall_detected", "fall_injury_risk", "video_fall"} and not alarm.get("acknowledged"):
                mapped = "critical"
        return mapped

    def _enforce_rule_priority(self, response: HealthScoreInsightResponse, context: dict[str, Any]) -> HealthScoreInsightResponse:
        fallback = self._fallback_response(context)
        risk_level = response.risk_level
        if RISK_ORDER[fallback.risk_level] > RISK_ORDER[risk_level]:
            risk_level = fallback.risk_level
        actions = list(dict.fromkeys(fallback.suggested_actions + response.suggested_actions))[:6]
        return response.model_copy(update={"risk_level": risk_level, "suggested_actions": actions})

    @staticmethod
    def _score_text(score: dict[str, Any]) -> str:
        if not score:
            return "当前健康评分数据暂缺，分析可信度受限。"
        final = HealthLlmInsightService._first_number(
            score.get("health_score"),
            score.get("final_health_score"),
            (score.get("sub_scores") or {}).get("final_health_score") if isinstance(score.get("sub_scores"), dict) else None,
        )
        rule = HealthLlmInsightService._first_number(
            score.get("rule_health_score"),
            (score.get("sub_scores") or {}).get("rule_health_score") if isinstance(score.get("sub_scores"), dict) else None,
        )
        model = HealthLlmInsightService._first_number(
            score.get("model_health_score"),
            (score.get("sub_scores") or {}).get("model_health_score") if isinstance(score.get("sub_scores"), dict) else None,
        )
        if final is None and rule is None and model is None:
            return "当前健康评分数据暂缺，分析可信度受限。"
        risk = HealthLlmInsightService._risk_text(score.get("risk_level"))
        action = score.get("recommendation_code") or "暂无建议动作"
        pieces = []
        if final is not None:
            pieces.append(f"当前健康评分为 {final:.1f} 分")
        if rule is not None:
            pieces.append(f"规则分为 {rule:.1f}")
        if model is not None:
            pieces.append(f"模型分为 {model:.1f}")
        text = "，".join(pieces)
        text = f"{text}，整体处于 {risk} 风险状态，建议动作 {action}。"
        if score.get("model_artifacts_available") is False or score.get("score_mode") == "fallback" or score.get("score_notice"):
            text += "由于结构化模型文件未完整加载，模型评分处于降级模式，模型解释可信度受限，当前解释主要依据规则评分、实时体征和趋势结果生成。"
        return text

    @staticmethod
    def _risk_text(value: Any) -> str:
        raw = str(value or "").lower()
        return {
            "normal": "低",
            "low": "低",
            "attention": "中等",
            "medium": "中等",
            "warning": "高",
            "high": "高",
            "critical": "紧急",
        }.get(raw, str(value or "未知"))

    @staticmethod
    def _first_number(*values: Any) -> float | None:
        for value in values:
            try:
                if value is None:
                    continue
                number = float(value)
            except (TypeError, ValueError):
                continue
            if number == number:
                return number
        return None

    @staticmethod
    def _trend_text(trend: dict[str, Any]) -> str:
        if not trend or not trend.get("sample_count"):
            return "近段时间趋势数据暂缺。"
        metrics = trend.get("metrics") or {}
        pieces = []
        labels = {"heart_rate": "心率", "spo2": "血氧", "sbp": "收缩压", "dbp": "舒张压", "body_temp": "体温"}
        for key, label in labels.items():
            item = metrics.get(key) or {}
            if not item:
                continue
            direction = {"up": "上升", "down": "下降", "stable": "平稳"}.get(item.get("direction"), "平稳")
            abnormal = "，存在持续异常" if item.get("sustained_abnormal") else ""
            pieces.append(f"{label}{direction}，范围 {item.get('min')}-{item.get('max')}{abnormal}")
        return "；".join(pieces) if pieces else "近段时间趋势摘要暂缺。"

    @staticmethod
    def _model_text(model: dict[str, Any]) -> str:
        if not model.get("ready"):
            message = str(model.get("message") or "时间序列模型结果暂缺。")
            return TECHNICAL_TEXT_FALLBACK if HealthLlmInsightService._has_technical_text(message) else message
        reason = model.get("reason") or "未发现持续性异常漂移"
        if HealthLlmInsightService._has_technical_text(reason):
            reason = "模型解释可信度受限，当前主要依据规则评分和实时趋势分析"
        return (
            f"时间序列模型概率 {model.get('probability')}，异常分 {model.get('score')}，"
            f"漂移分 {model.get('drift_score')}，重构分 {model.get('reconstruction_score')}；{reason}。"
        )

    @staticmethod
    def _summary_for_risk(risk_level: str, has_high_priority: bool, context: dict[str, Any]) -> str:
        if has_high_priority or risk_level == "critical":
            return "当前存在高优先级风险提示，请立即联系现场值守人员复核。"
        if context.get("data_freshness") == "missing":
            return "当前设备实时数据暂缺，分析可信度受限，建议先确认设备在线和数据上传状态。"
        if context.get("data_freshness") == "stale":
            return "当前设备实时数据已过期，分析可信度受限，建议先确认设备在线和数据上传状态。"
        if risk_level == "high":
            return "当前生命体征或告警提示风险偏高，建议缩短观察间隔并联系医护人员。"
        if risk_level == "medium":
            return "当前存在需要关注的波动，建议继续观察并复核关键指标。"
        return "当前生命体征整体稳定，建议保持常规监护。"

    @staticmethod
    def _actions_for_risk(risk_level: str) -> list[str]:
        if risk_level == "critical":
            return ["立即联系现场值守人员核查", "同步通知家属和医护人员", "复测关键生命体征"]
        if risk_level == "high":
            return ["缩短观察间隔", "联系医护人员复核", "确认设备佩戴和数据连续性"]
        if risk_level == "medium":
            return ["保持重点观察", "复核异常指标是否持续", "确认设备数据连续更新"]
        return ["保持常规监护", "若指标持续升高或降低，缩短观察间隔"]

    @staticmethod
    def _safe_text(value: Any, fallback: str) -> str:
        text = str(value or "").strip()
        if not text:
            return fallback
        if HealthLlmInsightService._has_technical_text(text):
            return TECHNICAL_TEXT_FALLBACK
        for blocked in ("诊断", "确诊", "治疗方案"):
            text = text.replace(blocked, "监护建议")
        return text[:600]

    @staticmethod
    def _safe_list(value: Any, fallback: list[str]) -> list[str]:
        if not isinstance(value, list):
            return fallback
        items = [HealthLlmInsightService._safe_text(item, "") for item in value]
        return [item for item in items if item][:6] or fallback

    @staticmethod
    def _safe_confidence(value: Any, fallback: str) -> str:
        text = str(value or "").lower()
        return text if text in {"low", "medium", "high"} else fallback

    @staticmethod
    def _safe_risk_level(value: Any, fallback: str) -> str:
        text = str(value or "").lower()
        return text if text in VALID_RISK_LEVELS else fallback

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            if stripped.lower().startswith("json"):
                stripped = stripped[4:]
        return stripped.strip()
