from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from backend.config import get_settings
from backend.schemas.health_insight_schema import HealthScoreInsightRequest
from backend.services.health_llm_insight_service import HealthLlmInsightService


PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
STATIC_HEALTH_ARTIFACT_DIR = str(Path(PROJECT_ROOT) / "data" / "artifacts" / "static_health")
STATIC_HEALTH_MODEL_PATH = str(Path(STATIC_HEALTH_ARTIFACT_DIR) / "static_health_model.pt")
STATIC_HEALTH_SCALER_PATH = str(Path(STATIC_HEALTH_ARTIFACT_DIR) / "feature_scaler.joblib")
STATIC_HEALTH_COLUMNS_PATH = str(Path(STATIC_HEALTH_ARTIFACT_DIR) / "feature_columns.json")


FORBIDDEN_TECHNICAL_SNIPPETS = (
    "Missing model artifacts",
    PROJECT_ROOT,
    "static_health_model.pt",
    "feature_scaler.joblib",
    "feature_columns.json",
    "Traceback",
    "Exception",
)


def _base_context() -> dict[str, object]:
    return {
        "device_mac": "54:10:26:01:00:DF",
        "elder": {"elder_id": "elder01", "elder_name": "李四", "room_no": "1-102"},
        "latest_vitals": {
            "heart_rate": 79,
            "spo2": 97,
            "blood_pressure": "113/70",
            "body_temp": 36.5,
            "steps": 1200,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
        "data_freshness": "fresh",
        "health_score": {
            "health_score": 89.0,
            "rule_health_score": 90.8,
            "model_health_score": 87.2,
            "risk_level": "normal",
            "recommendation_code": "HEALTH_OK",
            "active_events": [],
            "stabilized_vitals": {},
            "score_adjustment_reason": None,
        },
        "trend": {
            "sample_count": 4,
            "metrics": {
                "heart_rate": {"min": 76, "max": 82, "direction": "stable", "sustained_abnormal": False},
                "spo2": {"min": 96, "max": 98, "direction": "stable", "sustained_abnormal": False},
            },
        },
        "time_series_model": {"ready": True, "probability": 0.12, "score": 0.3, "drift_score": 0.1, "reconstruction_score": 0.2, "reason": "未检测到持续性异常漂移"},
        "recent_alarms": [],
        "high_priority_reasons": [],
        "missing_fields": [],
        "window_minutes": 5,
    }


class FakeContextService:
    def __init__(self, context: dict[str, object]) -> None:
        self.context = context

    def build_context(self, request: HealthScoreInsightRequest) -> dict[str, object]:
        return self.context


def _service(context: dict[str, object]) -> HealthLlmInsightService:
    settings = get_settings().model_copy(update={"qwen_api_key": "test-key", "qwen_model": "qwen-plus"})
    return HealthLlmInsightService(settings=settings, context_service=FakeContextService(context))  # type: ignore[arg-type]


def test_health_score_insight_uses_llm_when_available(monkeypatch) -> None:
    service = _service(_base_context())
    monkeypatch.setattr(
        service,
        "_call_llm",
        lambda context: {
            "summary": "当前生命体征整体稳定，建议保持常规监护。",
            "score_explanation": "规则分和模型分接近，风险提示一致。",
            "trend_analysis": "近5分钟关键指标平稳。",
            "model_assessment": "时间序列模型未检测到持续性异常漂移。",
            "suggested_actions": ["保持常规监护"],
            "watch_items": ["关注设备数据是否连续更新"],
            "confidence": "high",
            "risk_level": "low",
        },
    )

    result = service.generate(HealthScoreInsightRequest(device_mac="54:10:26:01:00:DF"))

    assert result.llm_used is True
    assert result.fallback_used is False
    assert result.risk_level == "low"
    assert result.summary.startswith("当前生命体征")


def test_health_score_insight_llm_http_uses_system_and_user_prompts(monkeypatch) -> None:
    service = _service(_base_context())
    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            content = {
                "risk_level": "low",
                "summary": "当前生命体征整体稳定，建议保持常规监护。",
                "score_explanation": "健康评分、规则分和模型分均提示风险较低。",
                "trend_analysis": "近5分钟心率和血氧整体平稳。",
                "model_assessment": "时间序列模型未检测到持续性异常漂移。",
                "suggested_actions": ["保持常规监护"],
                "watch_items": ["关注设备数据是否连续更新"],
                "confidence": "high",
            }
            return json.dumps({"choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}]}).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("backend.services.health_llm_insight_service.urllib.request.urlopen", fake_urlopen)

    result = service.generate(HealthScoreInsightRequest(device_mac="54:10:26:01:00:DF"))

    assert result.llm_used is True
    body = captured["body"]
    messages = body["messages"]
    assert messages[0]["role"] == "system"
    assert "智慧康养社区的健康监护分析助手" in messages[0]["content"]
    assert "不得编造不存在的体征、告警或模型结果" in messages[0]["content"]
    assert "输出必须是 JSON" in messages[0]["content"]
    assert messages[1]["role"] == "user"
    assert "health_context_json" in messages[1]["content"]
    assert '"latest_vitals"' in messages[1]["content"]
    assert '"health_score"' in messages[1]["content"]
    assert '"time_series_model"' in messages[1]["content"]
    assert '"data_freshness"' in messages[1]["content"]


def test_health_score_insight_fallback_when_llm_unavailable(monkeypatch) -> None:
    service = _service(_base_context())
    monkeypatch.setattr(service, "_call_llm", lambda context: None)

    result = service.generate(HealthScoreInsightRequest(device_mac="54:10:26:01:00:DF"))

    assert result.llm_used is False
    assert result.fallback_used is True
    assert result.score_explanation
    assert result.suggested_actions


def test_health_score_insight_fallback_when_llm_returns_non_json(monkeypatch) -> None:
    service = _service(_base_context())

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return json.dumps({"choices": [{"message": {"content": "这不是 JSON"}}]}).encode("utf-8")

    monkeypatch.setattr("backend.services.health_llm_insight_service.urllib.request.urlopen", lambda request, timeout: FakeResponse())

    result = service.generate(HealthScoreInsightRequest(device_mac="54:10:26:01:00:DF"))

    assert result.llm_used is False
    assert result.fallback_used is True


def test_health_score_insight_fallback_when_llm_json_schema_invalid(monkeypatch) -> None:
    service = _service(_base_context())

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            content = {
                "risk_level": "safe",
                "summary": "当前生命体征整体稳定。",
                "suggested_actions": ["保持常规监护"],
            }
            return json.dumps({"choices": [{"message": {"content": json.dumps(content, ensure_ascii=False)}}]}).encode("utf-8")

    monkeypatch.setattr("backend.services.health_llm_insight_service.urllib.request.urlopen", lambda request, timeout: FakeResponse())

    result = service.generate(HealthScoreInsightRequest(device_mac="54:10:26:01:00:DF"))

    assert result.llm_used is False
    assert result.fallback_used is True


def test_health_score_insight_fallback_when_llm_times_out(monkeypatch) -> None:
    service = _service(_base_context())

    def fake_timeout(request, timeout):
        raise TimeoutError("timed out")

    monkeypatch.setattr("backend.services.health_llm_insight_service.urllib.request.urlopen", fake_timeout)

    result = service.generate(HealthScoreInsightRequest(device_mac="54:10:26:01:00:DF"))

    assert result.llm_used is False
    assert result.fallback_used is True


def test_health_score_insight_fallback_without_api_key(monkeypatch) -> None:
    settings = get_settings().model_copy(update={"qwen_api_key": "", "dashscope_api_key_env": "", "qwen_model": "qwen-plus"})
    service = HealthLlmInsightService(settings=settings, context_service=FakeContextService(_base_context()))  # type: ignore[arg-type]

    def fail_if_called(request, timeout):
        raise AssertionError("LLM HTTP call should not run without an API key")

    monkeypatch.setattr("backend.services.health_llm_insight_service.urllib.request.urlopen", fail_if_called)

    result = service.generate(HealthScoreInsightRequest(device_mac="54:10:26:01:00:DF"))

    assert result.llm_used is False
    assert result.fallback_used is True


def test_health_score_insight_missing_data_does_not_raise(monkeypatch) -> None:
    context = _base_context()
    context.update(
        {
            "data_freshness": "missing",
            "latest_vitals": {},
            "health_score": None,
            "trend": {"sample_count": 0, "metrics": {}},
            "time_series_model": {"ready": False, "message": "时间序列样本不足，模型结果暂缺。"},
            "missing_fields": ["heart_rate", "spo2", "blood_pressure", "body_temp"],
        }
    )
    service = _service(context)
    monkeypatch.setattr(service, "_call_llm", lambda context: None)

    result = service.generate(HealthScoreInsightRequest(device_mac="54:10:26:01:00:DF"))

    assert result.data_freshness == "missing"
    assert result.risk_level == "medium"
    assert "可信度受限" in result.summary
    assert "当前健康评分数据暂缺" in result.score_explanation
    assert any("暂缺" in item for item in result.watch_items)


def test_health_score_insight_high_risk_alarm_escalates() -> None:
    context = _base_context()
    context["recent_alarms"] = [
        {
            "alarm_id": "alarm-1",
            "alarm_type": "sos",
            "alarm_level": 1,
            "message": "检测到 SOS 求助",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "acknowledged": False,
        }
    ]
    context["high_priority_reasons"] = ["sos 告警未确认，请优先联系现场值守人员核查。"]
    service = _service(context)

    result = service.generate(HealthScoreInsightRequest(device_mac="54:10:26:01:00:DF", use_llm=False))

    assert result.risk_level in {"high", "critical"}
    assert result.suggested_actions[0].startswith("sos 告警未确认")


def test_health_score_insight_high_risk_alarm_overrides_low_llm(monkeypatch) -> None:
    context = _base_context()
    context["recent_alarms"] = [
        {
            "alarm_id": "alarm-1",
            "alarm_type": "sos",
            "alarm_level": 1,
            "message": "检测到 SOS 求助",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "acknowledged": False,
        }
    ]
    context["high_priority_reasons"] = ["sos 告警未确认，请优先联系现场值守人员核查。"]
    service = _service(context)
    monkeypatch.setattr(
        service,
        "_call_llm",
        lambda context: {
            "risk_level": "low",
            "summary": "当前整体平稳。",
            "score_explanation": "规则分和模型分较高。",
            "trend_analysis": "趋势平稳。",
            "model_assessment": "模型未提示持续异常。",
            "suggested_actions": ["保持常规监护"],
            "watch_items": ["关注设备数据是否连续更新"],
            "confidence": "high",
        },
    )

    result = service.generate(HealthScoreInsightRequest(device_mac="54:10:26:01:00:DF"))

    assert result.llm_used is True
    assert result.risk_level == "critical"
    assert result.suggested_actions[0].startswith("sos 告警未确认")


def test_health_score_insight_hides_model_artifact_errors_when_scores_exist() -> None:
    context = _base_context()
    context["health_score"] = {
        "health_score": 91.0,
        "rule_health_score": 92.8,
        "model_health_score": 89.2,
        "risk_level": "normal",
        "recommendation_code": "MONITOR",
        "error": "MODEL_ARTIFACT_MISSING",
        "message": (
            f"Missing model artifacts: ['{STATIC_HEALTH_MODEL_PATH}', "
            f"'{STATIC_HEALTH_SCALER_PATH}', "
            f"'{STATIC_HEALTH_COLUMNS_PATH}']"
        ),
        "score_adjustment_reason": f"{STATIC_HEALTH_MODEL_PATH} is missing",
    }
    service = _service(context)

    result = service.generate(HealthScoreInsightRequest(device_mac="54:10:26:01:00:DF", use_llm=False))
    rendered = " ".join(
        [
            result.summary,
            result.score_explanation,
            result.trend_analysis,
            result.model_assessment,
            " ".join(result.suggested_actions),
            " ".join(result.watch_items),
        ]
    )

    assert "当前健康评分为 91.0 分" in result.score_explanation
    assert "模型评分处于降级模式" in result.score_explanation
    assert "健康评分暂不可用" not in result.score_explanation
    assert all(snippet not in rendered for snippet in FORBIDDEN_TECHNICAL_SNIPPETS)


def test_health_score_insight_only_says_score_missing_when_no_scores() -> None:
    context = _base_context()
    context["health_score"] = {
        "model_artifacts_available": False,
        "score_mode": "fallback",
        "score_notice": "结构化健康评分模型未完整加载，当前使用规则评分与降级模型评分进行辅助分析。",
    }
    service = _service(context)

    result = service.generate(HealthScoreInsightRequest(device_mac="54:10:26:01:00:DF", use_llm=False))

    assert result.score_explanation == "当前健康评分数据暂缺，分析可信度受限。"


def test_health_score_insight_user_prompt_sanitizes_technical_context() -> None:
    context = _base_context()
    context["health_score"] = {
        "health_score": 91.0,
        "rule_health_score": 92.8,
        "model_health_score": 89.2,
        "risk_level": "normal",
        "message": f"Missing model artifacts: ['{STATIC_HEALTH_MODEL_PATH}']",
    }

    prompt = HealthLlmInsightService._build_user_prompt(context)

    assert "model_artifacts_available" in prompt
    assert "score_mode" in prompt
    assert all(snippet not in prompt for snippet in FORBIDDEN_TECHNICAL_SNIPPETS)


def test_health_score_insight_sanitizes_llm_technical_text(monkeypatch) -> None:
    service = _service(_base_context())
    monkeypatch.setattr(
        service,
        "_call_llm",
        lambda context: {
            "risk_level": "low",
            "summary": "当前生命体征整体稳定，建议保持常规监护。",
            "score_explanation": f"Missing model artifacts: {STATIC_HEALTH_MODEL_PATH}",
            "trend_analysis": "近5分钟关键指标平稳。",
            "model_assessment": "Traceback Exception feature_scaler.joblib",
            "suggested_actions": ["保持常规监护"],
            "watch_items": ["feature_columns.json"],
            "confidence": "medium",
        },
    )

    result = service.generate(HealthScoreInsightRequest(device_mac="54:10:26:01:00:DF"))
    rendered = " ".join(
        [
            result.score_explanation,
            result.model_assessment,
            " ".join(result.watch_items),
        ]
    )

    assert "结构化健康评分模型未完整加载" in result.score_explanation
    assert all(snippet not in rendered for snippet in FORBIDDEN_TECHNICAL_SNIPPETS)
