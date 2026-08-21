from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from typing import Any, Protocol

from agent.robot_companion.action_planner import RobotCompanionActionPlanner
from agent.robot_companion.context_manager import RobotCompanionContextManager
from agent.robot_companion.prompt import SYSTEM_PROMPT, build_intent_user_prompt
from agent.robot_companion.safety_guard import RobotCompanionSafetyGuard
from backend.config import Settings
from backend.schemas.robot_companion_schema import (
    RobotCompanionActionType,
    RobotCompanionContext,
    RobotCompanionDecision,
    RobotCompanionDialogueRequest,
    RobotCompanionDialogueResponse,
    RobotCompanionIntent,
    RobotCompanionSafetyDecision,
)


logger = logging.getLogger(__name__)


class IntentClassifier(Protocol):
    def classify(self, text: str, *, use_llm: bool = True) -> RobotCompanionDecision: ...


class RobotCompanionIntentClassifier:
    """Qwen intent classifier with deterministic, safety-first fallback."""

    _EMERGENCY_TERMS = (
        "救命",
        "帮帮我",
        "摔倒",
        "跌倒",
        "起不来",
        "胸痛",
        "喘不过气",
        "呼吸困难",
        "sos",
        "紧急",
    )
    _WALK_TERMS = ("散步", "走走", "出去", "出门", "公园", "遛弯", "活动一下")
    _WEATHER_TERMS = ("天气", "下雨", "气温", "温度", "刮风", "风大", "太阳", "冷不冷", "热不热")
    _HEALTH_TERMS = ("身体", "健康", "状态", "血压", "心率", "血氧", "健康分", "监测")
    _COMPANION_TERMS = ("陪陪", "陪我", "孤独", "寂寞", "聊聊天", "说说话")

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def classify(self, text: str, *, use_llm: bool = True) -> RobotCompanionDecision:
        fallback = self._rule_decision(text)
        if fallback.intent == RobotCompanionIntent.EMERGENCY:
            return fallback
        if use_llm and self._settings.qwen_llm_configured:
            llm_decision = self._call_qwen(text)
            if llm_decision is not None:
                return llm_decision
        return fallback

    def _call_qwen(self, text: str) -> RobotCompanionDecision | None:
        base = (
            self._settings.qwen_api_base.strip()
            or "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        url = base.rstrip("/")
        if not url.endswith("/chat/completions"):
            url = f"{url}/chat/completions"
        body = {
            "model": self._settings.tongyi_chat_model,
            "temperature": 0.0,
            "stream": False,
            "response_format": {"type": "json_object"},
            "max_tokens": 120,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_intent_user_prompt(text)},
            ],
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._settings.dashscope_api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=max(3, int(self._settings.llm_timeout_seconds)),
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
            content = payload["choices"][0]["message"]["content"]
            parsed = json.loads(self._strip_code_fence(str(content)))
            intent = RobotCompanionIntent(str(parsed.get("intent", "")).strip())
            confidence = max(0.0, min(1.0, float(parsed.get("confidence", 0.0))))
            return RobotCompanionDecision(
                intent=intent,
                confidence=confidence,
                source="qwen",
                model=self._settings.tongyi_chat_model,
            )
        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            logger.info("Robot companion intent classification degraded to rules: %s", exc)
            return None

    def _rule_decision(self, text: str) -> RobotCompanionDecision:
        normalized = text.strip().lower()
        if self._contains(normalized, self._EMERGENCY_TERMS):
            intent, confidence = RobotCompanionIntent.EMERGENCY, 0.99
        elif self._contains(normalized, self._WALK_TERMS):
            intent, confidence = RobotCompanionIntent.WALK_REQUEST, 0.94
        elif self._contains(normalized, self._WEATHER_TERMS):
            intent, confidence = RobotCompanionIntent.WEATHER_QUERY, 0.93
        elif self._contains(normalized, self._HEALTH_TERMS):
            intent, confidence = RobotCompanionIntent.HEALTH_CHECK, 0.9
        elif self._contains(normalized, self._COMPANION_TERMS):
            intent, confidence = RobotCompanionIntent.COMPANIONSHIP, 0.9
        else:
            intent, confidence = RobotCompanionIntent.CHAT, 0.72
        return RobotCompanionDecision(
            intent=intent,
            confidence=confidence,
            source="rule",
        )

    @staticmethod
    def _contains(text: str, terms: tuple[str, ...]) -> bool:
        return any(term in text for term in terms)

    @staticmethod
    def _strip_code_fence(value: str) -> str:
        match = re.search(r"\{.*\}", value.strip(), flags=re.DOTALL)
        return match.group(0) if match else value.strip()


class RobotCompanionAgentService:
    def __init__(
        self,
        *,
        context_manager: RobotCompanionContextManager,
        intent_classifier: IntentClassifier,
        action_planner: RobotCompanionActionPlanner,
        safety_guard: RobotCompanionSafetyGuard,
    ) -> None:
        self._context = context_manager
        self._intent = intent_classifier
        self._planner = action_planner
        self._safety = safety_guard

    def dialogue(self, request: RobotCompanionDialogueRequest) -> RobotCompanionDialogueResponse:
        context = self._context.build(
            elder_id=request.elder_id,
            device_mac=request.device_mac,
            location_hint=request.location_hint,
            weather_scenario=request.demo_weather,
        )
        decision = self._intent.classify(request.text, use_llm=request.use_llm)
        action_plan = self._planner.plan(
            decision=decision,
            text=request.text,
            context=context,
        )
        safety = self._safety.evaluate(context=context, plan=action_plan)
        reply = self._build_reply(
            decision=decision,
            context=context,
            action_type=action_plan.type,
            safety=safety,
        )
        return RobotCompanionDialogueResponse(
            decision=decision,
            reply=reply,
            context=context,
            action_plan=action_plan,
            safety=safety,
        )

    def _build_reply(
        self,
        *,
        decision: RobotCompanionDecision,
        context: RobotCompanionContext,
        action_type: RobotCompanionActionType,
        safety: RobotCompanionSafetyDecision,
    ) -> str:
        del action_type
        if decision.intent == RobotCompanionIntent.EMERGENCY:
            return (
                "我听到您可能需要帮助，请先待在安全的位置。"
                "我已经生成求助建议，但当前不会自动联系家属或控制机器人，请立即呼叫家属或社区工作人员。"
            )
        if decision.intent == RobotCompanionIntent.WALK_REQUEST:
            return self._walk_reply(context, safety)
        if decision.intent == RobotCompanionIntent.WEATHER_QUERY:
            temperature_text = (
                f"大约 {context.environment.temperature:g}℃"
                if context.environment.temperature is not None
                else "暂时没有可靠温度数据"
            )
            return (
                f"我帮您看了一下，当前是{self._weather_label(context.environment.weather)}，"
                f"{temperature_text}。"
                f"{context.environment.suggestion}"
            )
        if decision.intent == RobotCompanionIntent.HEALTH_CHECK:
            return self._health_reply(context)
        if decision.intent == RobotCompanionIntent.COMPANIONSHIP:
            return "我在这里陪您。您可以慢慢说说今天想做什么，我会认真听。"
        return "我听到了。您可以告诉我想聊天、看看天气，还是想了解今天是否适合活动。"

    def _walk_reply(
        self,
        context: RobotCompanionContext,
        safety: RobotCompanionSafetyDecision,
    ) -> str:
        if safety.code in {"SOS_ACTIVE", "RECENT_FALL", "HEALTH_RISK_HIGH"}:
            return (
                "最近的健康状态需要多留意，今天先不要走太远。"
                "可以先在安全位置休息或短距离活动，如有不舒服请马上联系家属或社区工作人员。"
            )
        if safety.code in {"HEALTH_DATA_MISSING", "HEALTH_DATA_STALE"}:
            return (
                "目前还没有足够新鲜的健康数据。"
                "建议先确认手环佩戴并复测，状态确认后再考虑外出。"
            )
        if safety.code == "WEATHER_RAIN":
            return "外面现在有雨，路面可能有些滑。建议今天先在室内活动，或者等天气好一些再出去。"
        if safety.code == "WEATHER_STRONG_WIND":
            return "今天风有点大，外出时需要格外注意。建议先在室内或住宅附近短距离活动。"
        if safety.code == "WEATHER_HIGH_TEMPERATURE":
            return "今天比较热，不建议长时间在户外活动。可以先在室内走一走，并注意补充水分。"
        if safety.code == "WEATHER_LOW_TEMPERATURE":
            return "今天气温较低，外出需要增加衣物。建议缩短活动时间，或者先在室内活动。"
        if safety.code == "MOTION_DISABLED":
            return (
                "今天天气和当前状态适合适量活动，我已经准备好陪伴计划。"
                "不过真实运动模式还没有开启，目前只展示计划，建议您慢慢走、不要太累。"
            )
        return f"当前陪伴计划暂未执行。{safety.reason}"

    @staticmethod
    def _health_reply(context: RobotCompanionContext) -> str:
        health = context.health
        if health.data_freshness == "missing":
            return "目前没有可用的最新健康数据。请先确认手环佩戴和连接状态，再重新查看。"
        if health.data_freshness == "stale":
            return "当前健康数据已经有些过时。建议先重新测量，再根据新结果安排活动。"
        if health.risk_level == "high":
            return "当前监测结果需要重点留意。请先休息并联系家属或社区工作人员协助确认。"
        score_text = f"，健康分约为 {health.health_score} 分" if health.health_score is not None else ""
        return f"当前监测状态整体为{RobotCompanionAgentService._risk_label(health.risk_level)}{score_text}。建议继续适量活动并留意身体感受。"

    @staticmethod
    def _risk_label(risk_level: str) -> str:
        return {
            "low": "低风险",
            "medium": "需要留意",
            "high": "高风险",
            "unknown": "暂不明确",
        }.get(risk_level, "暂不明确")

    @staticmethod
    def _weather_label(weather: str) -> str:
        return {
            "sunny": "晴天",
            "rain": "有雨",
            "windy": "风力较大",
            "hot": "高温天气",
            "cold": "低温天气",
            "unknown": "天气信息未知",
        }.get(weather, "天气信息未知")
