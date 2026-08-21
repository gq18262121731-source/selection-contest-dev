from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from typing import Any, Iterator, TypedDict
from urllib import error, request
from uuid import uuid4

from agent.analysis_service import HealthDataAnalysisService
from agent.context_assembler import AgentContextAssembler
from agent.langchain_rag_service import LangChainRAGService
from agent.mcp_adapter import ToolAdapter, ToolInvocation
from agent.model_interfaces import AgentModelInput, AgentModelSuite
from agent.prompting import build_prompt_package
from agent.response_normalizer import sanitize_agent_response, sanitize_device_health_report
from backend.config import Settings
from backend.models.health_model import HealthSample
from backend.models.user_model import UserRole

try:
    from langchain_core.prompts import ChatPromptTemplate
except Exception:
    ChatPromptTemplate = None

try:
    from langchain_community.chat_models import ChatTongyi
except Exception:
    ChatTongyi = None

try:
    from langchain_ollama import ChatOllama
except Exception:
    ChatOllama = None


def _alarm_from_payload(payload: dict[str, Any]):
    class _AlarmStub:
        def __init__(self, row: dict[str, Any]) -> None:
            self.id = row.get("id", "")
            self.device_mac = str(row.get("device_mac", ""))
            self.alarm_type = row.get("alarm_type", "")
            self.alarm_level = int(row.get("alarm_level", 0) or 0)
            self.message = str(row.get("message", ""))
            self.acknowledged = bool(row.get("acknowledged", False))

    return _AlarmStub(payload)


class AgentState(TypedDict, total=False):
    scope: str
    role: UserRole
    question: str
    workflow: str
    window: str
    conversation_history: list[dict[str, str]]
    history_minutes: int
    per_device_limit: int
    focus_device_mac: str
    target_device_mac: str
    target_device_macs: list[str]
    subject_elder_id: str | None
    samples: list[HealthSample]
    community_samples: dict[str, list[HealthSample]]
    route_mode: str
    include_report: bool
    network_online: bool
    selected_mode: str
    selected_provider: str
    selected_model: str
    context_bundle: dict[str, Any]
    tool_results: list[dict[str, Any]]
    model_results: dict[str, dict[str, Any]]
    degraded_notes: list[str]
    analysis_payload: dict[str, Any]
    analysis_context: str
    dialogue_events: list[dict[str, Any]]
    dialogue_action_labels: list[str]
    dialogue_expression: dict[str, Any]
    retrieval_query: str
    knowledge_hits: list[str]
    system_prompt: str
    user_prompt: str
    prompt_text: str
    messages: list[Any]
    answer: str
    final_payload: dict[str, object]


class HealthAgentService:
    """Health agent with provider auto-routing for Qwen API and local fallbacks."""

    def __init__(
        self,
        settings: Settings,
        rag_service: LangChainRAGService,
        analysis_service: HealthDataAnalysisService | None = None,
        *,
        context_assembler: AgentContextAssembler | None = None,
        tool_adapter: ToolAdapter | None = None,
        model_suite: AgentModelSuite | None = None,
    ) -> None:
        self._settings = settings
        self._rag = rag_service
        self._analysis = analysis_service or HealthDataAnalysisService()
        self._context_assembler = context_assembler
        self._tool_adapter = tool_adapter
        self._model_suite = model_suite
        self._local_llms: dict[str, Any] = {}

    def analyze(
        self,
        *,
        role: UserRole,
        question: str,
        samples: list[HealthSample],
        mode: str = "local",
    ) -> dict[str, object]:
        return self.analyze_device(role=role, question=question, samples=samples, mode=mode)

    def analyze_device(
        self,
        *,
        role: UserRole,
        question: str,
        samples: list[HealthSample],
        mode: str = "local",
    ) -> dict[str, object]:
        state = self._execute(
            {
                "scope": "device",
                "role": role,
                "question": question,
                "target_device_mac": samples[-1].device_mac if samples else "",
                "samples": samples,
                "route_mode": mode,
            }
        )
        return self._format_result(state)

    def analyze_community(
        self,
        *,
        role: UserRole,
        question: str,
        device_samples: dict[str, list[HealthSample]],
        mode: str = "local",
        history_minutes: int = 1440,
        workflow: str = "free_chat",
        focus_device_mac: str | None = None,
        history: list[dict[str, str]] | None = None,
        scope: str = "community",
        subject_elder_id: str | None = None,
        window: str = "day",
        provider: str = "qwen",
        include_report: bool = False,
        per_device_limit: int = 240,
        device_macs: list[str] | None = None,
    ) -> dict[str, object]:
        target_device_macs = self._resolve_target_device_macs(
            scope=scope,
            device_macs=device_macs,
            subject_elder_id=subject_elder_id,
            focus_device_mac=focus_device_mac,
        )
        samples_by_device = self._hydrate_community_samples(
            device_samples,
            target_device_macs=target_device_macs,
            history_minutes=history_minutes,
            per_device_limit=per_device_limit,
        )
        primary_device_mac = target_device_macs[0] if target_device_macs else ""
        state = self._execute(
            {
                "scope": scope,
                "role": role,
                "question": question,
                "workflow": workflow,
                "window": window,
                "conversation_history": self._normalize_conversation_history(history),
                "history_minutes": history_minutes,
                "per_device_limit": per_device_limit,
                "focus_device_mac": str(focus_device_mac or "").strip().upper(),
                "target_device_mac": primary_device_mac,
                "target_device_macs": target_device_macs or sorted(samples_by_device.keys()),
                "subject_elder_id": subject_elder_id,
                "samples": list(samples_by_device.get(primary_device_mac, [])) if primary_device_mac else [],
                "community_samples": samples_by_device,
                "route_mode": provider or mode,
                "include_report": bool(include_report),
            }
        )
        return self._format_result(state)

    def stream_analyze_device(
        self,
        *,
        role: UserRole,
        question: str,
        samples: list[HealthSample],
        mode: str = "local",
    ) -> Iterator[dict[str, object]]:
        session_id = str(uuid4())
        initial_state: AgentState = {
            "scope": "device",
            "role": role,
            "question": question,
            "target_device_mac": samples[-1].device_mac if samples else "",
            "samples": samples,
            "route_mode": mode,
        }
        yield {
            "type": "session.started",
            "session_id": session_id,
            "scope": "device",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        yield from self._stream_execute(initial_state, session_id=session_id)

    def stream_analyze_community(
        self,
        *,
        role: UserRole,
        question: str,
        device_samples: dict[str, list[HealthSample]] | None = None,
        mode: str = "local",
        history_minutes: int = 1440,
        workflow: str = "free_chat",
        focus_device_mac: str | None = None,
        history: list[dict[str, str]] | None = None,
        scope: str = "community",
        subject_elder_id: str | None = None,
        window: str = "day",
        provider: str = "qwen",
        include_report: bool = False,
        per_device_limit: int = 240,
        device_macs: list[str] | None = None,
    ) -> Iterator[dict[str, object]]:
        target_device_macs = self._resolve_target_device_macs(
            scope=scope,
            device_macs=device_macs,
            subject_elder_id=subject_elder_id,
            focus_device_mac=focus_device_mac,
        )
        samples_by_device = self._hydrate_community_samples(
            device_samples,
            target_device_macs=target_device_macs,
            history_minutes=history_minutes,
            per_device_limit=per_device_limit,
        )
        session_id = str(uuid4())
        primary_device_mac = target_device_macs[0] if target_device_macs else ""
        initial_state: AgentState = {
          "scope": scope,
          "role": role,
          "question": question,
          "workflow": workflow,
          "window": window,
          "conversation_history": self._normalize_conversation_history(history),
          "history_minutes": history_minutes,
          "per_device_limit": per_device_limit,
          "focus_device_mac": str(focus_device_mac or "").strip().upper(),
          "target_device_mac": primary_device_mac,
          "target_device_macs": target_device_macs or sorted(samples_by_device.keys()),
          "subject_elder_id": subject_elder_id,
          "samples": list(samples_by_device.get(primary_device_mac, [])) if primary_device_mac else [],
          "community_samples": samples_by_device,
          "route_mode": provider or mode,
          "include_report": bool(include_report),
        }
        yield {
            "type": "session.started",
            "session_id": session_id,
            "scope": "community",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        yield from self._stream_execute(initial_state, session_id=session_id)

    def generate_device_health_report(
        self,
        *,
        role: UserRole,
        device_mac: str,
        start_at: datetime,
        end_at: datetime,
        samples: list[HealthSample],
        mode: str = "local",
    ) -> dict[str, object]:
        ordered = sorted(samples, key=lambda item: item.timestamp)
        analysis_payload = self._analysis.summarize_device(ordered)

        context_bundle: dict[str, Any] = {}
        if self._context_assembler is not None:
            try:
                context_bundle = self._context_assembler.build_device_context(
                    device_mac=device_mac,
                    samples=ordered,
                ).summary
            except Exception:
                context_bundle = {}

        model_signals = self._build_report_model_signals(
            role=role,
            device_mac=device_mac,
            samples=ordered,
            context_bundle=context_bundle,
        )
        health_model_evidence = self._build_report_health_model_evidence(
            device_mac=device_mac,
            samples=ordered,
            analysis_payload=analysis_payload,
            model_signals=model_signals,
        )
        knowledge_hits = self._rag.search(
            self._build_report_retrieval_query(
                role=role,
                device_mac=device_mac,
                start_at=start_at,
                end_at=end_at,
                analysis_payload=analysis_payload,
                model_signals=model_signals,
                health_model_evidence=health_model_evidence,
            ),
            top_k=self._settings.rag_top_k,
            network_online=False,
            allow_rerank=self._settings.qwen_enable_rerank,
        )

        prompt = self._build_report_prompt(
            role=role,
            device_mac=device_mac,
            start_at=start_at,
            end_at=end_at,
            analysis_payload=analysis_payload,
            knowledge_hits=knowledge_hits,
            context_bundle=context_bundle,
            model_signals=model_signals,
            health_model_evidence=health_model_evidence,
        )
        selected_provider = self._select_generation_provider(requested_mode=mode)
        selected_model = self._select_report_generation_model(
            role=role,
            requested_mode=mode,
            provider=selected_provider,
        )
        summary = self._invoke_local(
            prompt["prompt_text"],
            prompt["messages"],
            selected_model=selected_model,
            selected_provider=selected_provider,
            system_prompt=prompt["system_prompt"],
            user_prompt=prompt["user_prompt"],
            max_predict_tokens=None,
            max_output_chars=None,
        )
        if not summary:
            summary = self._fallback_report_summary_with_model_signals(
                analysis_payload,
                model_signals=model_signals,
                health_model_evidence=health_model_evidence,
            )

        latest = analysis_payload.get("latest", {}) if isinstance(analysis_payload, dict) else {}
        averages = analysis_payload.get("averages", {}) if isinstance(analysis_payload, dict) else {}
        ranges = analysis_payload.get("ranges", {}) if isinstance(analysis_payload, dict) else {}
        trend = analysis_payload.get("trend", {}) if isinstance(analysis_payload, dict) else {}
        elder_profile = context_bundle.get("elder_profile", {}) if isinstance(context_bundle, dict) else {}
        device_row = context_bundle.get("device", {}) if isinstance(context_bundle, dict) else {}
        key_findings = self._build_report_key_findings(
            analysis_payload,
            model_signals=model_signals,
            health_model_evidence=health_model_evidence,
        )
        recommendations = self._build_report_recommendations(
            analysis_payload,
            model_signals=model_signals,
            health_model_evidence=health_model_evidence,
        )

        metrics = self._build_report_metrics(
            latest=latest if isinstance(latest, dict) else {},
            averages=averages if isinstance(averages, dict) else {},
            ranges=ranges if isinstance(ranges, dict) else {},
            trend=trend if isinstance(trend, dict) else {},
        )

        raw_report = {
            "report_type": "device_health_report",
            "device_mac": device_mac.upper(),
            "subject_name": elder_profile.get("name") if isinstance(elder_profile, dict) else None,
            "device_name": device_row.get("device_name") if isinstance(device_row, dict) else None,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "period": {
                "start_at": start_at.astimezone(timezone.utc).isoformat(),
                "end_at": end_at.astimezone(timezone.utc).isoformat(),
                "duration_minutes": max(int((end_at - start_at).total_seconds() // 60), 0),
                "sample_count": int(analysis_payload.get("sample_count", len(ordered))) if isinstance(analysis_payload, dict) else len(ordered),
            },
            "summary": summary,
            "risk_level": health_model_evidence.get("risk_level", "unknown"),
            "risk_flags": list(health_model_evidence.get("risk_flags", [])),
            "key_findings": key_findings,
            "recommendations": recommendations,
            "metrics": metrics,
            "references": knowledge_hits,
        }
        return sanitize_device_health_report(raw_report)

    def capability_report(self) -> dict[str, object]:
        return {
            "framework": {
                "langchain_prompt_available": ChatPromptTemplate is not None,
            },
            "llm_adapters": {
                "langchain_tongyi": ChatTongyi is not None,
                "langchain_ollama": ChatOllama is not None,
            },
            "configured_models": {
                "preferred_provider": self._settings.preferred_llm_provider,
                "llm_provider": self._settings.llm_provider,
                "qwen_model": self._settings.qwen_model,
                "qwen_api_base": self._settings.qwen_api_base,
                "qwen_configured": self._settings.qwen_llm_configured,
                "ollama_base_url": self._settings.ollama_base_url,
                "ollama_model": self._settings.ollama_model,
                "default_local_model": self._settings.local_default_model,
                "reasoning_local_model": self._settings.local_reasoning_model,
                "report_local_model": self._settings.local_report_model,
                "approved_local_models": list(self._settings.supported_local_models),
                "local_model_routing": self._settings.local_model_routing,
                "local_report_routing": self._settings.local_report_routing,
                "execution_mode": "provider_auto_routing",
            },
            "retrieval": self._rag.stats(),
            "extensions": {
                "context_assembler": self._context_assembler is not None,
                "tool_adapter": self._tool_adapter is not None,
                "model_suite": self._model_suite is not None,
                "mcp_connected": False,
                "cloud_mode_enabled": self._settings.qwen_llm_configured,
                "offline_only_runtime": self._settings.offline_only_runtime,
            },
            "tool_specs": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "source": tool.source,
                }
                for tool in (self._tool_adapter.list_tools() if self._tool_adapter is not None else [])
            ],
        }

    def _execute(self, initial_state: AgentState) -> AgentState:
        state: AgentState = dict(initial_state)
        state.update(self._route_node(state))
        state.update(self._context_node(state))
        state.update(self._tool_node(state))
        state.update(self._analysis_node(state))
        state.update(self._model_node(state))
        state.update(self._dialogue_event_node(state))
        state.update(self._retrieve_node(state))
        state.update(self._prompt_node(state))
        state.update(self._generate_node(state))
        state.update(self._aggregate_node(state))
        return state

    @staticmethod
    def _normalize_conversation_history(history: list[dict[str, str]] | None) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        for item in history or []:
            role = str(item.get("role", "")).strip().lower()
            content = str(item.get("content", "")).strip()
            if role not in {"user", "assistant"} or not content:
                continue
            normalized.append({"role": role, "content": content})
        return normalized[-8:]

    @staticmethod
    def _normalize_mac_list(device_macs: list[str] | None) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for mac in device_macs or []:
            value = str(mac or "").strip().upper()
            if not value or value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        return normalized

    def _resolve_target_device_macs(
        self,
        *,
        scope: str,
        device_macs: list[str] | None,
        subject_elder_id: str | None,
        focus_device_mac: str | None,
    ) -> list[str]:
        explicit = self._normalize_mac_list(device_macs)
        if explicit:
            return explicit

        focus = str(focus_device_mac or "").strip().upper()
        if scope != "elder":
            return [focus] if focus else []

        if self._context_assembler is not None and subject_elder_id:
            try:
                directory = self._context_assembler._care.get_directory()
                elder = next(
                    (
                        item
                        for item in directory.elders
                        if str(getattr(item, "id", "")).strip() == str(subject_elder_id).strip()
                    ),
                    None,
                )
                if elder is not None:
                    elder_device_macs = list(getattr(elder, "device_macs", [])) or (
                        [getattr(elder, "device_mac", "")]
                        if getattr(elder, "device_mac", "")
                        else []
                    )
                    resolved = self._normalize_mac_list(elder_device_macs)
                    if resolved:
                        return resolved
            except Exception:
                pass

        return [focus] if focus else []

    def _hydrate_community_samples(
        self,
        device_samples: dict[str, list[HealthSample]] | None,
        *,
        target_device_macs: list[str],
        history_minutes: int,
        per_device_limit: int,
    ) -> dict[str, list[HealthSample]]:
        if device_samples:
            return {mac.upper(): list(samples) for mac, samples in device_samples.items()}
        if self._context_assembler is None:
            return {}
        try:
            return self._context_assembler._stream.recent_by_devices(
                target_device_macs or None,
                minutes=max(30, int(history_minutes or 1440)),
                per_device_limit=max(24, int(per_device_limit or 240)),
            )
        except Exception:
            return {}

    def _stream_execute(self, initial_state: AgentState, *, session_id: str) -> Iterator[dict[str, object]]:
        state: AgentState = dict(initial_state)
        stages = [
            ("route", "路由模型", self._route_node),
            ("context", "上下文整理", self._context_node),
            ("tools", "工具调用", None),
            ("analysis", "结构分析", self._analysis_node),
            ("models", "模型信号", self._model_node),
            ("dialogue", "过程归纳", self._dialogue_event_node),
            ("retrieve", "知识检索", self._retrieve_node),
            ("prompt", "提示构建", self._prompt_node),
            ("generate", "回答生成", None),
            ("aggregate", "结果汇总", self._aggregate_node),
        ]

        try:
            for stage_key, stage_label, handler in stages:
                yield self._make_stage_event(stage_key, stage_label, "running")

                if stage_key == "tools":
                    update = yield from self._stream_tool_node(state, stage=stage_key)
                elif stage_key == "generate":
                    full_answer = []
                    for chunk in self._stream_build_answer(state):
                        if not chunk:
                            continue
                        for fragment in self._iter_stream_fragments(chunk):
                            if not fragment:
                                continue
                            full_answer.append(fragment)
                            yield {
                                "type": "answer.delta",
                                "session_id": session_id,
                                "delta": fragment,
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                            }
                    update = {
                        "answer": "".join(full_answer),
                        "selected_mode": str(state.get("selected_mode", "local")),
                    }
                else:
                    assert handler is not None
                    update = handler(state)

                state.update(update)

                for note in self._build_stage_notes(stage_key, state):
                    yield {
                        "type": "trace.note",
                        "stage": stage_key,
                        "note": note,
                        "level": "info",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }

                yield self._make_stage_event(stage_key, stage_label, "completed")

            formatted = self._format_result(state)
            yield {
                "type": "answer.completed",
                "session_id": session_id,
                "answer": str(formatted.get("answer", "")).strip(),
                "references": list(formatted.get("references", [])),
                "analysis": dict(formatted.get("analysis", {})),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            yield {
                "type": "session.completed",
                "session_id": session_id,
                "selected_model": str(state.get("selected_model", self._settings.local_default_model)),
                "degraded_notes": list(state.get("degraded_notes", [])),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as exc:
            yield self._make_stage_event("aggregate", "结果汇总", "error", detail=exc.__class__.__name__)
            yield {
                "type": "session.error",
                "session_id": session_id,
                "error": f"{exc.__class__.__name__}: {exc}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    def _make_stage_event(
        self,
        stage: str,
        label: str,
        status: str,
        *,
        detail: str = "",
    ) -> dict[str, object]:
        summary = detail or f"{label}{'进行中' if status == 'running' else '已完成'}"
        payload: dict[str, object] = {
            "type": "stage.changed",
            "stage": stage,
            "label": label,
            "status": status,
            "group": "trace",
            "summary": summary,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if detail:
            payload["detail"] = detail
        return payload

    def _route_node(self, state: AgentState) -> AgentState:
        requested_mode = str(state.get("route_mode", "local"))
        selected_provider = self._select_generation_provider(requested_mode=requested_mode)
        selected_model = self._select_generation_model(
            scope=str(state.get("scope", "device")),
            question=str(state.get("question", "")),
            requested_mode=requested_mode,
            provider=selected_provider,
        )
        degraded_notes: list[str] = []
        if selected_provider == "ollama" and self._settings.qwen_llm_configured:
            degraded_notes.append("qwen_provider_fallback_to_local")
        return {
            "network_online": selected_provider == "qwen",
            "selected_mode": "cloud" if selected_provider == "qwen" else "local",
            "selected_provider": selected_provider,
            "selected_model": selected_model,
            "degraded_notes": degraded_notes,
        }

    def _select_generation_provider(self, *, requested_mode: str) -> str:
        normalized = requested_mode.strip().lower()
        if normalized in {"qwen", "tongyi", "cloud", "api"} and self._settings.qwen_llm_configured:
            return "qwen"
        if normalized in {"ollama"}:
            return "ollama"
        return self._settings.preferred_llm_provider

    def _normalize_qwen_model(self, model_name: str) -> str:
        normalized = (model_name or "").strip()
        if not normalized:
            return "qwen-plus"
        lower = normalized.lower()
        if lower in {"qwen3.5-flash", "qwen3.5", "qwen3.5-flash-mini", "qwen3.5-lite"}:
            return "qwen-plus"
        return normalized

    def _select_generation_model(self, *, scope: str, question: str, requested_mode: str, provider: str) -> str:
        if provider == "qwen":
            return self._normalize_qwen_model(self._settings.qwen_model)
        return self._select_local_model(scope=scope, question=question, requested_mode=requested_mode)

    def _select_local_model(self, *, scope: str, question: str, requested_mode: str) -> str:
        del requested_mode

        approved = self._settings.supported_local_models
        default_model = self._settings.local_default_model
        reasoning_model = self._settings.local_reasoning_model

        if self._settings.local_model_routing == "single":
            return default_model

        question_text = question.lower()
        reasoning_keywords = (
            "community",
            "社区",
            "summary",
            "summarize",
            "汇总",
            "排序",
            "priorit",
            "trend",
            "原因",
            "归因",
            "explain",
        )
        if scope == "community" or any(keyword in question_text for keyword in reasoning_keywords):
            if reasoning_model in approved:
                return reasoning_model
        return default_model

    def _select_report_model(
        self,
        *,
        role: UserRole,
        requested_mode: str,
    ) -> str:
        del requested_mode

        approved = self._settings.supported_local_models
        report_model = self._settings.local_report_model
        reasoning_model = self._settings.local_reasoning_model

        if self._settings.local_report_routing == "role_router":
            if role in {UserRole.COMMUNITY, UserRole.ADMIN} and reasoning_model in approved:
                return reasoning_model

        if report_model in approved:
            return report_model
        return self._settings.local_default_model

    def _select_report_generation_model(
        self,
        *,
        role: UserRole,
        requested_mode: str,
        provider: str,
    ) -> str:
        if provider == "qwen":
            return self._normalize_qwen_model(self._settings.qwen_model)
        return self._select_report_model(role=role, requested_mode=requested_mode)

    def _context_node(self, state: AgentState) -> AgentState:
        if self._context_assembler is None:
            return {"context_bundle": {}, "degraded_notes": ["context_assembler_not_configured"]}

        scope = str(state.get("scope", "device"))
        try:
            if scope == "community":
                bundle = self._context_assembler.build_community_context(
                    device_macs=list(state.get("target_device_macs", [])),
                    device_samples=dict(state.get("community_samples", {})),
                )
            else:
                device_mac = str(state.get("target_device_mac", "")).strip()
                if not device_mac and state.get("samples"):
                    device_mac = list(state.get("samples", []))[-1].device_mac
                bundle = self._context_assembler.build_device_context(
                    device_mac=device_mac,
                    samples=list(state.get("samples", [])),
                )
            return {
                "context_bundle": bundle.summary,
                "degraded_notes": list(bundle.degraded),
            }
        except Exception as exc:
            return {
                "context_bundle": {},
                "degraded_notes": [f"context_build_failed:{exc.__class__.__name__}"],
            }

    def _tool_node(self, state: AgentState) -> AgentState:
        if self._tool_adapter is None:
            return {"tool_results": []}
        calls = self._build_tool_calls(state)
        results = self._tool_adapter.invoke_many(calls)
        return {"tool_results": [self._serialize_tool_result(call, item) for call, item in zip(calls, results, strict=False)]}

    def _build_tool_calls(self, state: AgentState) -> list[ToolInvocation]:
        scope = str(state.get("scope", "device"))
        role = str(state.get("role", ""))
        workflow = str(state.get("workflow", "free_chat"))
        question = str(state.get("question", "")).strip()
        community_id = None
        context_bundle = state.get("context_bundle", {})
        if isinstance(context_bundle, dict):
            community_value = context_bundle.get("community")
            if isinstance(community_value, dict):
                community_id = str(community_value.get("id", "")) or None

        if scope == "community":
            device_macs = list(state.get("target_device_macs", []))
            focus_device_mac = str(state.get("focus_device_mac", "")).strip().upper()
            window = str(state.get("window") or self._window_value_from_history(int(state.get("history_minutes", 1440) or 1440)))
            calls = [
                ToolInvocation(name="get_community_overview", request_id=str(uuid4()), operator_role=role, community_id=community_id),
                ToolInvocation(name="get_active_alarms", request_id=str(uuid4()), operator_role=role, community_id=community_id, payload={"active_only": True}),
                ToolInvocation(name="get_care_directory", request_id=str(uuid4()), operator_role=role, community_id=community_id),
                ToolInvocation(
                    name="summarize_window_metrics",
                    request_id=str(uuid4()),
                    operator_role=role,
                    community_id=community_id,
                    payload={"window": window, "device_macs": device_macs},
                ),
            ]
            if workflow == "community_report" or bool(state.get("include_report", False)):
                calls.append(
                    ToolInvocation(
                        name="generate_analysis_report",
                        request_id=str(uuid4()),
                        operator_role=role,
                        community_id=community_id,
                        payload={"scope": "community", "window": window, "device_macs": device_macs},
                    )
                )
            if workflow in {"overview", "device_focus", "free_chat", "risk_ranking", "community_report", "report_generation"}:
                calls.append(
                    ToolInvocation(
                        name="build_chart_payloads",
                        request_id=str(uuid4()),
                        operator_role=role,
                        community_id=community_id,
                        payload={"window": window, "device_macs": device_macs},
                    )
                )
            if workflow in {"alert_digest", "free_chat", "community_report", "report_generation"}:
                calls.append(
                    ToolInvocation(
                        name="query_alert_history",
                        request_id=str(uuid4()),
                        operator_role=role,
                        community_id=community_id,
                        payload={"window": window, "device_macs": device_macs},
                    )
                )
            if workflow == "device_focus" and focus_device_mac:
                focus_payload = {"window": window, "device_mac": focus_device_mac, "mac_address": focus_device_mac}
                calls.extend(
                    [
                        ToolInvocation(name="query_sensor_history", request_id=str(uuid4()), operator_role=role, community_id=community_id, payload=focus_payload),
                        ToolInvocation(name="query_health_scores", request_id=str(uuid4()), operator_role=role, community_id=community_id, payload=focus_payload),
                        ToolInvocation(name="query_device_status_history", request_id=str(uuid4()), operator_role=role, community_id=community_id, payload=focus_payload),
                    ]
                )
            if self._should_search(question=question, workflow=workflow):
                calls.append(
                    ToolInvocation(
                        name="run_tavily_search",
                        request_id=str(uuid4()),
                        operator_role=role,
                        community_id=community_id,
                        payload={"query": question},
                    )
                )
            return calls

        device_mac = str(state.get("target_device_mac", "")).strip()
        calls = [
            ToolInvocation(name="get_device_realtime", request_id=str(uuid4()), operator_role=role, community_id=community_id, payload={"mac_address": device_mac}),
            ToolInvocation(name="get_device_status", request_id=str(uuid4()), operator_role=role, community_id=community_id, payload={"mac_address": device_mac}),
            ToolInvocation(name="get_active_alarms", request_id=str(uuid4()), operator_role=role, community_id=community_id, payload={"mac_address": device_mac, "active_only": True}),
            ToolInvocation(name="get_elder_profile", request_id=str(uuid4()), operator_role=role, community_id=community_id, payload={"mac_address": device_mac}),
        ]
        if self._should_search(question=question, workflow=workflow):
            calls.append(
                ToolInvocation(
                    name="run_tavily_search",
                    request_id=str(uuid4()),
                    operator_role=role,
                    community_id=community_id,
                    payload={"query": question},
                )
            )
        return calls

    @staticmethod
    def _window_value_from_history(history_minutes: int) -> str:
        return "week" if history_minutes >= 7 * 24 * 60 else "day"

    @staticmethod
    def _should_search(*, question: str, workflow: str) -> bool:
        if workflow in {"community_report", "report_generation", "elder_report", "overview", "risk_ranking", "alert_digest"}:
            return False
        normalized_question = question.lower()
        explicit_search_terms = ("搜索", "查找", "检索", "search", "政策", "指南", "天气", "空气", "周边", "假期", "网页", "新闻")
        return workflow in {"free_chat", "device_focus"} and any(term in normalized_question for term in explicit_search_terms)

    def _serialize_tool_result(self, call: ToolInvocation, item: Any) -> dict[str, Any]:
        attachments = self._tool_result_attachments(call.name, item.data if isinstance(item.data, dict) else {})
        return {
            "request_id": call.request_id,
            "name": item.name,
            "status": item.status,
            "success": item.success,
            "source": item.source,
            "data": item.data,
            "attachments": attachments,
            "error_code": item.error_code,
            "error_message": item.error_message,
        }

    def _stream_tool_node(self, state: AgentState, *, stage: str) -> Iterator[dict[str, object]]:
        if self._tool_adapter is None:
            return {"tool_results": []}

        calls = self._build_tool_calls(state)
        tool_results: list[dict[str, Any]] = []
        legacy_emitted: set[str] = set()
        last_summary = ""
        last_input_preview = ""
        last_output_preview = ""
        for index, call in enumerate(calls):
            yield {
                "type": "tool.started",
                "stage": stage,
                "tool_name": call.name,
                "request_id": call.request_id,
                "source": "local_service",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            result = self._tool_adapter.invoke_many([call])[0]
            serialized = self._serialize_tool_result(call, result)
            tool_results.append(serialized)
            attachments = list(serialized.get("attachments", []))
            summary = self._tool_result_summary(call.name, result.data, result.success)
            input_preview = json.dumps(call.payload or {}, ensure_ascii=False, default=str)[:240]
            output_preview = json.dumps(result.data if isinstance(result.data, dict) else {"value": result.data}, ensure_ascii=False, default=str)[:360]
            last_summary = summary
            last_input_preview = input_preview
            last_output_preview = output_preview
            yield {
                "type": "tool.finished",
                "stage": stage,
                "tool_name": call.name,
                "request_id": call.request_id,
                "source": result.source,
                "status": result.status,
                "success": result.success,
                "summary": summary,
                "attachments": attachments,
                "title": attachments[0].get("title") if attachments else None,
                "render_type": attachments[0].get("render_type") if attachments else None,
                "render_payload": attachments[0].get("render_payload") if attachments else None,
                "input_preview": input_preview,
                "output_preview": output_preview,
                "error_message": result.error_message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            legacy_name, tool_kind = self._legacy_tool_alias_for_stream(
                state=state,
                call_name=call.name,
                index=index,
            )
            if legacy_name and legacy_name not in legacy_emitted:
                legacy_emitted.add(legacy_name)
                yield {
                    "type": "tool.finished",
                    "stage": stage,
                    "tool_name": legacy_name,
                    "tool_kind": tool_kind,
                    "request_id": call.request_id,
                    "source": result.source,
                    "status": result.status,
                    "success": result.success,
                    "summary": summary,
                    "attachments": attachments,
                    "input_preview": input_preview,
                    "output_preview": output_preview,
                    "error_message": result.error_message,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

        if str(state.get("scope", "device")) == "community" and "synthesize_recommendations" not in legacy_emitted:
            yield {
                "type": "tool.finished",
                "stage": stage,
                "tool_name": "synthesize_recommendations",
                "tool_kind": "reasoning",
                "request_id": "synthetic-synthesize-recommendations",
                "source": "local_service",
                "status": "ok",
                "success": True,
                "summary": last_summary or "已生成处置建议",
                "attachments": [],
                "input_preview": last_input_preview,
                "output_preview": last_output_preview,
                "error_message": None,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        return {"tool_results": tool_results}

    def _legacy_tool_alias_for_stream(self, *, state: AgentState, call_name: str, index: int) -> tuple[str, str]:
        scope = str(state.get("scope", "device"))
        if scope != "community":
            return "", ""

        if call_name in {"get_community_overview", "summarize_window_metrics", "get_care_directory", "get_active_alarms"}:
            return "query_window_dataset", "data_query"
        if call_name in {"build_chart_payloads", "query_alert_history", "query_health_scores"}:
            return "analyze_health_window", "analysis"
        if call_name in {"generate_analysis_report", "run_tavily_search"}:
            return "synthesize_recommendations", "reasoning"

        if index == 0:
            return "query_window_dataset", "data_query"
        if index == 1:
            return "analyze_health_window", "analysis"
        if index == 2:
            return "synthesize_recommendations", "reasoning"
        return "", ""

    def _tool_result_summary(self, tool_name: str, data: dict[str, Any], success: bool) -> str:
        if not success:
            return "工具执行失败"
        if tool_name == "generate_analysis_report":
            if isinstance(data, dict):
                attachments = data.get("attachments", [])
                if isinstance(attachments, list) and attachments:
                    return "已生成结构化分析报告"
            return "报告生成完成"
        if tool_name == "get_active_alarms":
            return f"返回 {len(data.get('alarms', [])) if isinstance(data.get('alarms'), list) else 0} 条告警"
        if tool_name == "get_community_overview":
            return f"覆盖 {data.get('device_count', 0)} 台设备"
        if tool_name == "get_care_directory":
            families = data.get("families", []) if isinstance(data, dict) else []
            elders = data.get("elders", []) if isinstance(data, dict) else []
            return f"返回 {len(elders) if isinstance(elders, list) else 0} 位老人 / {len(families) if isinstance(families, list) else 0} 位家属"
        if tool_name == "get_device_realtime":
            return "已读取设备最新生命体征"
        if tool_name == "get_device_status":
            return f"设备状态 {data.get('status', 'unknown')}"
        if tool_name == "get_elder_profile":
            return f"已读取对象 {data.get('name', 'unknown')}"
        if tool_name == "summarize_window_metrics":
            metrics = data.get("key_metrics", {}) if isinstance(data, dict) else {}
            return f"已汇总窗口关键指标 {len(metrics) if isinstance(metrics, dict) else 0} 项"
        if tool_name == "build_chart_payloads":
            charts = data.get("charts", []) if isinstance(data, dict) else []
            return f"已生成 {len(charts) if isinstance(charts, list) else 0} 组图表"
        if tool_name == "query_alert_history":
            alerts = data.get("alerts", []) if isinstance(data, dict) else []
            return f"已检索 {len(alerts) if isinstance(alerts, list) else 0} 条告警记录"
        if tool_name == "query_health_scores":
            scores = data.get("scores", []) if isinstance(data, dict) else []
            return f"已返回 {len(scores) if isinstance(scores, list) else 0} 条健康评分记录"
        if tool_name == "run_tavily_search":
            results = data.get("results", []) if isinstance(data, dict) else []
            return f"已检索 {len(results) if isinstance(results, list) else 0} 条外部参考"
        return "已返回结构化结果"

    def _tool_result_attachments(self, tool_name: str, data: dict[str, Any]) -> list[dict[str, Any]]:
        if not isinstance(data, dict):
            return []
        if tool_name == "generate_analysis_report":
            attachments = data.get("attachments", [])
            if isinstance(attachments, list):
                normalized: list[dict[str, Any]] = []
                for item in attachments:
                    if not isinstance(item, dict):
                        continue
                    render_type = str(item.get("render_type", ""))
                    title = str(item.get("title", ""))
                    if not render_type or not title:
                        continue
                    normalized.append(
                        {
                            "id": str(item.get("id", "analysis-report")),
                            "title": title,
                            "summary": str(item.get("summary", "")),
                            "render_type": render_type,
                            "render_payload": dict(item.get("render_payload", {})),
                            "source_tool": "generate_analysis_report",
                        }
                    )
                return normalized
        label_map = {
            "device_count": "设备总数",
            "reported_device_count": "已上报设备",
            "active_alert_count": "活跃告警",
            "high_risk_device_count": "高风险对象",
            "average_health_score": "平均健康分",
            "average_blood_oxygen": "平均血氧",
            "elder_name": "老人",
            "device_mac": "设备 MAC",
            "risk_level": "风险等级",
            "latest_health_score": "最新健康分",
            "active_alert_count": "活跃告警数",
            "alarm_type": "告警类型",
            "alarm_level": "告警等级",
            "message": "告警说明",
            "created_at": "时间",
            "evaluated_at": "评估时间",
            "health_score": "健康分",
            "recommendation_code": "推荐动作",
            "title": "标题",
            "url": "链接",
            "snippet": "摘要",
        }
        if tool_name == "build_chart_payloads":
            attachments: list[dict[str, Any]] = []
            for index, chart in enumerate(data.get("charts", [])):
                if not isinstance(chart, dict):
                    continue
                option = chart.get("echarts_option")
                if not isinstance(option, dict):
                    continue
                attachments.append(
                    {
                        "id": str(chart.get("id") or f"chart-{index}"),
                        "title": str(chart.get("title") or "图表输出"),
                        "summary": str(chart.get("summary") or ""),
                        "render_type": "echarts",
                        "render_payload": {
                            "id": str(chart.get("id") or f"chart-{index}"),
                            "title": str(chart.get("title") or "图表输出"),
                            "summary": str(chart.get("summary") or ""),
                            "echarts_option": option,
                        },
                        "source_tool": tool_name,
                    }
                )
            return attachments
        if tool_name == "summarize_window_metrics":
            metric_cards = []
            key_metrics = data.get("key_metrics", {})
            if isinstance(key_metrics, dict):
                for key in (
                    "device_count",
                    "reported_device_count",
                    "active_alert_count",
                    "high_risk_device_count",
                    "average_health_score",
                    "average_blood_oxygen",
                ):
                    if key in key_metrics:
                        metric_cards.append({"label": label_map.get(key, key), "value": key_metrics[key]})
            high_risk_entities = data.get("high_risk_entities", [])
            attachments: list[dict[str, Any]] = []
            if metric_cards:
                attachments.append(
                    {
                        "id": "window-metrics",
                        "title": "社区关键指标",
                        "summary": "窗口内的核心监护指标摘要",
                        "render_type": "metric_cards",
                        "render_payload": {"items": metric_cards},
                        "source_tool": tool_name,
                    }
                )
            if isinstance(high_risk_entities, list) and high_risk_entities:
                attachments.append(
                    {
                        "id": "window-risk-ranking",
                        "title": "高风险对象排行",
                        "summary": "按当前窗口的风险等级与活跃告警排序",
                        "render_type": "table",
                        "render_payload": {
                            "columns": [
                                {"key": "elder_name", "label": label_map["elder_name"]},
                                {"key": "device_mac", "label": label_map["device_mac"]},
                                {"key": "risk_level", "label": label_map["risk_level"]},
                                {"key": "latest_health_score", "label": label_map["latest_health_score"]},
                                {"key": "active_alert_count", "label": label_map["active_alert_count"]},
                            ],
                            "rows": high_risk_entities[:8],
                        },
                        "source_tool": tool_name,
                    }
                )
            return attachments
        if tool_name == "query_alert_history":
            alerts = data.get("alerts", [])
            if isinstance(alerts, list) and alerts:
                return [
                    {
                        "id": "alert-history",
                        "title": "告警历史",
                        "summary": "窗口内命中的告警记录",
                        "render_type": "table",
                        "render_payload": {
                            "columns": [
                                {"key": "device_mac", "label": label_map["device_mac"]},
                                {"key": "alarm_type", "label": label_map["alarm_type"]},
                                {"key": "alarm_level", "label": label_map["alarm_level"]},
                                {"key": "message", "label": label_map["message"]},
                                {"key": "created_at", "label": label_map["created_at"]},
                            ],
                            "rows": alerts[:10],
                        },
                        "source_tool": tool_name,
                    }
                ]
        if tool_name == "query_health_scores":
            scores = data.get("scores", [])
            if isinstance(scores, list) and scores:
                return [
                    {
                        "id": "health-score-history",
                        "title": "健康评分记录",
                        "summary": "聚焦设备最近窗口内的评分轨迹",
                        "render_type": "table",
                        "render_payload": {
                            "columns": [
                                {"key": "evaluated_at", "label": label_map["evaluated_at"]},
                                {"key": "health_score", "label": label_map["health_score"]},
                                {"key": "risk_level", "label": label_map["risk_level"]},
                                {"key": "recommendation_code", "label": label_map["recommendation_code"]},
                            ],
                            "rows": scores[:10],
                        },
                        "source_tool": tool_name,
                    }
                ]
        if tool_name == "run_tavily_search":
            results = data.get("results", [])
            if isinstance(results, list) and results:
                return [
                    {
                        "id": "web-search-results",
                        "title": "外部检索结果",
                        "summary": "补充性的网络参考信息",
                        "render_type": "table",
                        "render_payload": {
                            "columns": [
                                {"key": "title", "label": label_map["title"]},
                                {"key": "url", "label": label_map["url"]},
                                {"key": "snippet", "label": label_map["snippet"]},
                            ],
                            "rows": results[:8],
                        },
                        "source_tool": tool_name,
                    }
                ]
        return []

    def _analysis_node(self, state: AgentState) -> AgentState:
        scope = str(state.get("scope", "device"))
        question = str(state.get("question", "")).strip()
        if scope == "community":
            raw_payload = self._analysis.summarize_community_history(dict(state.get("community_samples", {})))
        else:
            raw_payload = self._analysis.summarize_device(list(state.get("samples", [])))

        payload = self._sanitize_agent_content(raw_payload)

        context_bundle = self._sanitize_agent_content(dict(state.get("context_bundle", {})))
        context_bundle["analysis_recommendations"] = payload.get("recommendations", []) if isinstance(payload, dict) else []

        return {
            "context_bundle": context_bundle,
            "analysis_payload": payload,
            "analysis_context": json.dumps(payload, ensure_ascii=False, indent=2, default=str),
            "retrieval_query": self._build_retrieval_query(scope=scope, question=question, analysis_payload=payload),
        }

    def _sanitize_agent_content(self, value: Any) -> Any:
        if isinstance(value, dict):
            sanitized: dict[str, Any] = {}
            for key, item in value.items():
                key_text = str(key)
                if self._should_skip_agent_key(key_text):
                    continue
                cleaned = self._sanitize_agent_content(item)
                if self._is_agent_empty(cleaned):
                    continue
                sanitized[key_text] = cleaned
            return sanitized

        if isinstance(value, list):
            sanitized_items = [self._sanitize_agent_content(item) for item in value]
            return [item for item in sanitized_items if not self._is_agent_empty(item)]

        if isinstance(value, str):
            return "" if self._mentions_temperature_topic(value) else value

        return value

    @staticmethod
    def _should_skip_agent_key(key: str) -> bool:
        normalized = key.strip().lower()
        if not normalized:
            return False
        return normalized in {
            "temperature",
            "body_temp",
            "current_temperature",
            "temperature_delta",
            "temperature_celsius",
        } or "temperature" in normalized

    @staticmethod
    def _mentions_temperature_topic(text: str) -> bool:
        raw = text.strip()
        if not raw:
            return False
        lowered = raw.lower()
        cn_markers = ("体温", "发热", "低温", "高温")
        en_markers = ("temperature", "temp_warning", "temp_critical")
        return any(marker in raw for marker in cn_markers) or any(
            marker in lowered for marker in en_markers
        )

    @staticmethod
    def _is_agent_empty(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return not value.strip()
        if isinstance(value, (list, tuple, set, dict)):
            return len(value) == 0
        return False

    def _model_node(self, state: AgentState) -> AgentState:
        if self._model_suite is None:
            return {"model_results": {}}

        model_input = AgentModelInput(
            scope=str(state.get("scope", "device")),
            role=state.get("role", UserRole.FAMILY),
            question=str(state.get("question", "")),
            device_mac=str(state.get("target_device_mac", "")).strip() or None,
            device_macs=list(state.get("target_device_macs", [])),
            samples=list(state.get("samples", [])),
            community_samples=dict(state.get("community_samples", {})),
            alarms=[],
            context=dict(state.get("context_bundle", {})),
        )
        tool_alarm_payloads = [
            item.get("data", {}).get("alarms", [])
            for item in state.get("tool_results", [])
            if item.get("name") == "get_active_alarms"
        ]
        flat_alarm_payloads = [alarm for batch in tool_alarm_payloads if isinstance(batch, list) for alarm in batch]
        model_input.alarms = [_alarm_from_payload(payload) for payload in flat_alarm_payloads]
        results = self._model_suite.run_all(model_input)
        return {
            "model_results": {
                key: {
                    "model_name": value.model_name,
                    "status": value.status,
                    "source": value.source,
                    "summary": self._sanitize_agent_content(value.summary),
                    "payload": self._sanitize_agent_content(value.payload),
                    "confidence": value.confidence,
                    "degraded_reason": value.degraded_reason,
                }
                for key, value in results.items()
            }
        }

    def _dialogue_event_node(self, state: AgentState) -> AgentState:
        analysis_payload = dict(state.get("analysis_payload", {}))
        model_results = dict(state.get("model_results", {}))
        context_bundle = dict(state.get("context_bundle", {}))
        scope = str(state.get("scope", "device"))
        role = state.get("role", UserRole.FAMILY)
        question = str(state.get("question", "")).strip()

        event_layer = self._build_dialogue_event_layer(
            scope=scope,
            role=role,
            analysis_payload=analysis_payload,
            model_results=model_results,
            context_bundle=context_bundle,
        )
        expression = self._build_dialogue_expression(
            scope=scope,
            role=role,
            analysis_payload=analysis_payload,
            event_layer=event_layer,
        )
        retrieval_query = self._build_dialogue_retrieval_query(
            scope=scope,
            question=question,
            analysis_payload=analysis_payload,
            event_layer=event_layer,
        )
        return {
            "dialogue_events": list(event_layer.get("events", [])),
            "dialogue_action_labels": list(event_layer.get("action_labels", [])),
            "dialogue_expression": expression,
            "retrieval_query": retrieval_query or str(state.get("retrieval_query", "")),
        }

    def _build_dialogue_event_layer(
        self,
        *,
        scope: str,
        role: UserRole,
        analysis_payload: dict[str, Any],
        model_results: dict[str, dict[str, Any]],
        context_bundle: dict[str, Any],
    ) -> dict[str, Any]:
        del role
        if scope == "community":
            return self._build_community_dialogue_events(analysis_payload)
        return self._build_device_dialogue_events(
            analysis_payload=analysis_payload,
            model_results=model_results,
            context_bundle=context_bundle,
        )

    def _build_device_dialogue_events(
        self,
        *,
        analysis_payload: dict[str, Any],
        model_results: dict[str, dict[str, Any]],
        context_bundle: dict[str, Any],
    ) -> dict[str, Any]:
        latest = analysis_payload.get("latest", {})
        trend = analysis_payload.get("trend", {})
        data_quality = analysis_payload.get("data_quality", {})
        risk_flags = [str(item) for item in analysis_payload.get("risk_flags", [])]
        risk_level = str(analysis_payload.get("risk_level", "unknown"))

        anomaly_result = model_results.get("anomaly_explain", {})
        anomaly_payload = anomaly_result.get("payload", {}) if isinstance(anomaly_result, dict) else {}
        alarm_payloads = [
            item.get("data", {}).get("alarms", [])
            for item in context_bundle.get("tool_results", [])
        ] if False else []
        active_alarm_rows = context_bundle.get("active_alarms", []) if isinstance(context_bundle, dict) else []
        active_alarm_count = len(active_alarm_rows) if isinstance(active_alarm_rows, list) else 0

        events: list[dict[str, Any]] = []

        spo2 = latest.get("blood_oxygen") if isinstance(latest, dict) else None
        spo2_trend = trend.get("blood_oxygen", {}) if isinstance(trend, dict) else {}
        if (
            isinstance(spo2, (int, float)) and spo2 <= 94
            or "blood_oxygen_warning" in risk_flags
            or "blood_oxygen_critical" in risk_flags
            or (isinstance(spo2_trend, dict) and str(spo2_trend.get("label", "")) == "falling")
        ):
            severity = "low"
            urgency = "routine"
            if isinstance(spo2, (int, float)):
                if spo2 <= 88:
                    severity, urgency = "critical", "immediate"
                elif spo2 <= 90:
                    severity, urgency = "high", "soon"
                elif spo2 <= 92:
                    severity, urgency = "medium", "today"
            if str(spo2_trend.get("label", "")) == "falling" and severity == "low":
                severity, urgency = "medium", "today"
            events.append(
                {
                    "event_code": "low_oxygen_risk",
                    "event_name": "低氧风险",
                    "severity": severity,
                    "urgency": urgency,
                    "status": "active",
                    "summary": "当前血氧偏低并呈下降趋势" if str(spo2_trend.get("label", "")) == "falling" else "当前血氧偏低",
                    "evidence": {
                        "current_spo2": spo2,
                        "trend_label": str(spo2_trend.get("label", "")),
                        "trend_delta": spo2_trend.get("delta"),
                    },
                    "recommended_action_levels": [
                        "rest_in_sitting_position",
                        "remeasure_spo2_30min",
                        "watch_breathing_symptoms",
                        "seek_medical_help_if_persistent",
                    ],
                }
            )

        temp = latest.get("temperature") if isinstance(latest, dict) else None
        temp_trend = trend.get("temperature", {}) if isinstance(trend, dict) else {}
        if (
            isinstance(temp, (int, float)) and temp >= 37.5
            or "temperature_warning" in risk_flags
            or "temperature_critical" in risk_flags
            or (isinstance(temp_trend, dict) and str(temp_trend.get("label", "")) == "rising" and isinstance(temp, (int, float)) and temp >= 37.2)
        ):
            severity = "low"
            urgency = "routine"
            if isinstance(temp, (int, float)):
                if temp >= 39.0:
                    severity, urgency = "critical", "immediate"
                elif temp >= 38.5:
                    severity, urgency = "high", "soon"
                elif temp >= 38.0:
                    severity, urgency = "medium", "today"
            events.append(
                {
                    "event_code": "temperature_warning",
                    "event_name": "体温异常",
                    "severity": severity,
                    "urgency": urgency,
                    "status": "active",
                    "summary": "体温偏高，需要继续观察变化",
                    "evidence": {
                        "current_temperature": temp,
                        "trend_label": str(temp_trend.get("label", "")),
                        "trend_delta": temp_trend.get("delta"),
                    },
                    "recommended_action_levels": [
                        "remeasure_temperature_30min",
                        "watch_fever_symptoms",
                        "notify_family_member",
                    ],
                }
            )

        if isinstance(anomaly_payload, dict):
            probability = anomaly_payload.get("probability")
            sustained_minutes = anomaly_payload.get("sustained_minutes")
            alarm_ready = bool(anomaly_payload.get("alarm_ready", False))
            if isinstance(probability, (int, float)) and probability >= 0.45:
                events.append(
                    {
                        "event_code": "single_abnormality",
                        "event_name": "异常波动",
                        "severity": "medium" if probability >= 0.6 else "low",
                        "urgency": "today" if probability >= 0.6 else "routine",
                        "status": "active",
                        "summary": str(anomaly_payload.get("reason", "")).strip() or "出现值得继续观察的异常波动",
                        "evidence": {
                            "probability": probability,
                            "sustained_minutes": sustained_minutes,
                        },
                        "recommended_action_levels": ["continue_observation", "remeasure_vitals_60min"],
                    }
                )
            if isinstance(sustained_minutes, (int, float)) and sustained_minutes >= 20:
                events.append(
                    {
                        "event_code": "sustained_abnormality",
                        "event_name": "持续异常",
                        "severity": "high" if sustained_minutes >= 40 else "medium",
                        "urgency": "soon" if sustained_minutes >= 40 else "today",
                        "status": "active",
                        "summary": f"异常状态已持续约 {sustained_minutes:.0f} 分钟",
                        "evidence": {
                            "sustained_minutes": sustained_minutes,
                            "reason": str(anomaly_payload.get("reason", "")).strip(),
                        },
                        "recommended_action_levels": ["community_followup_needed", "notify_family_member"],
                    }
                )
            if alarm_ready or active_alarm_count > 0:
                events.append(
                    {
                        "event_code": "alarm_ready",
                        "event_name": "需要立即复核",
                        "severity": "high",
                        "urgency": "immediate",
                        "status": "active",
                        "summary": "当前异常已达到需要立即复核的程度",
                        "evidence": {
                            "alarm_ready": alarm_ready,
                            "active_alarm_count": active_alarm_count,
                        },
                        "recommended_action_levels": [
                            "community_followup_needed",
                            "notify_family_member",
                            "seek_medical_help_if_persistent",
                        ],
                    }
                )

        score_trend = trend.get("health_score", {}) if isinstance(trend, dict) else {}
        active_problem_count = len(events)
        if active_problem_count >= 2 or (
            isinstance(score_trend, dict) and str(score_trend.get("label", "")) == "falling" and active_problem_count >= 1
        ):
            events.append(
                {
                    "event_code": "multi_signal_deterioration",
                    "event_name": "多指标联动恶化",
                    "severity": "high" if active_problem_count >= 3 or risk_level == "high" else "medium",
                    "urgency": "soon" if active_problem_count >= 3 else "today",
                    "status": "active",
                    "summary": "近一段时间多项指标同时变差，整体状态较前走弱",
                    "evidence": {
                        "event_count": active_problem_count,
                        "risk_level": risk_level,
                        "health_score_trend": str(score_trend.get("label", "")) if isinstance(score_trend, dict) else "",
                    },
                    "recommended_action_levels": [
                        "notify_family_member",
                        "community_followup_needed",
                        "seek_medical_help_if_persistent",
                    ],
                }
            )

        if not events and (
            (isinstance(score_trend, dict) and str(score_trend.get("label", "")) == "falling")
            or list(analysis_payload.get("recommendations", []))
        ):
            events.append(
                {
                    "event_code": "followup_needed",
                    "event_name": "需要继续观察",
                    "severity": "low" if risk_level == "low" else "medium",
                    "urgency": "today",
                    "status": "active",
                    "summary": "当前未到高危，但趋势提示还需要继续观察",
                    "evidence": {
                        "risk_level": risk_level,
                        "health_score_trend": str(score_trend.get("label", "")) if isinstance(score_trend, dict) else "",
                    },
                    "recommended_action_levels": ["continue_observation", "remeasure_vitals_60min"],
                }
            )

        if isinstance(data_quality, dict) and int(data_quality.get("gaps_over_30_minutes", 0) or 0) > 0:
            events.append(
                {
                    "event_code": "data_quality_limited",
                    "event_name": "数据质量受限",
                    "severity": "low",
                    "urgency": "routine",
                    "status": "active",
                    "summary": "当前数据存在时间缺口，需要先核对设备与采集情况",
                    "evidence": {
                        "gaps_over_30_minutes": int(data_quality.get("gaps_over_30_minutes", 0) or 0),
                    },
                    "recommended_action_levels": ["check_device_wearing", "remeasure_after_device_check"],
                }
            )

        action_labels = self._collect_dialogue_action_labels(events)
        return {
            "events": events,
            "action_labels": action_labels,
            "primary_event": self._pick_primary_dialogue_event(events),
        }

    def _build_community_dialogue_events(self, analysis_payload: dict[str, Any]) -> dict[str, Any]:
        distribution = analysis_payload.get("risk_distribution", {}) if isinstance(analysis_payload, dict) else {}
        priority_devices = list(analysis_payload.get("priority_devices", [])) if isinstance(analysis_payload, dict) else []
        device_count = int(analysis_payload.get("device_count", 0)) if isinstance(analysis_payload, dict) else 0
        high_count = int(distribution.get("high", 0)) if isinstance(distribution, dict) else 0
        medium_count = int(distribution.get("medium", 0)) if isinstance(distribution, dict) else 0

        events: list[dict[str, Any]] = []
        if high_count > 0:
            events.append(
                {
                    "event_code": "community_followup_needed",
                    "event_name": "社区优先跟进",
                    "severity": "high",
                    "urgency": "soon",
                    "status": "active",
                    "summary": f"当前有 {high_count} 台高风险设备需要优先处理",
                    "evidence": {
                        "device_count": device_count,
                        "high_count": high_count,
                        "medium_count": medium_count,
                    },
                    "recommended_action_levels": ["prioritize_phone_followup", "arrange_onsite_review"],
                }
            )
        elif medium_count > 0:
            events.append(
                {
                    "event_code": "followup_needed",
                    "event_name": "需要继续跟进",
                    "severity": "medium",
                    "urgency": "today",
                    "status": "active",
                    "summary": f"当前有 {medium_count} 台中风险设备需要今天内继续跟进",
                    "evidence": {
                        "device_count": device_count,
                        "medium_count": medium_count,
                    },
                    "recommended_action_levels": ["prioritize_phone_followup"],
                }
            )
        if not events:
            events.append(
                {
                    "event_code": "single_abnormality",
                    "event_name": "整体基本平稳",
                    "severity": "low",
                    "urgency": "routine",
                    "status": "active",
                    "summary": "当前社区整体风险较低，以常规观察为主",
                    "evidence": {
                        "device_count": device_count,
                    },
                    "recommended_action_levels": ["continue_observation"],
                }
            )
        return {
            "events": events,
            "action_labels": self._collect_dialogue_action_labels(events),
            "primary_event": self._pick_primary_dialogue_event(events),
            "priority_devices": priority_devices,
        }

    @staticmethod
    def _severity_rank(level: str) -> int:
        return {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(level, 0)

    def _pick_primary_dialogue_event(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        if not events:
            return {}
        return sorted(events, key=lambda item: (self._severity_rank(str(item.get("severity", ""))), str(item.get("urgency", ""))), reverse=True)[0]

    def _collect_dialogue_action_labels(self, events: list[dict[str, Any]]) -> list[str]:
        labels: list[str] = []
        seen: set[str] = set()
        for event in events:
            for item in event.get("recommended_action_levels", []):
                code = str(item).strip()
                if not code or code in seen:
                    continue
                seen.add(code)
                labels.append(code)
        return labels

    def _build_dialogue_expression(
        self,
        *,
        scope: str,
        role: UserRole,
        analysis_payload: dict[str, Any],
        event_layer: dict[str, Any],
    ) -> dict[str, Any]:
        if scope == "community":
            answer = self._render_community_dialogue(role=role, analysis_payload=analysis_payload, event_layer=event_layer)
        else:
            answer = self._render_device_dialogue(role=role, analysis_payload=analysis_payload, event_layer=event_layer)
        return {
            "answer": answer,
            "primary_event_code": str(event_layer.get("primary_event", {}).get("event_code", "")),
        }

    def _render_device_dialogue(
        self,
        *,
        role: UserRole,
        analysis_payload: dict[str, Any],
        event_layer: dict[str, Any],
    ) -> str:
        latest = analysis_payload.get("latest", {}) if isinstance(analysis_payload, dict) else {}
        primary_event = event_layer.get("primary_event", {}) if isinstance(event_layer, dict) else {}
        actions = list(event_layer.get("action_labels", [])) if isinstance(event_layer, dict) else []
        event_code = str(primary_event.get("event_code", ""))
        severity = str(primary_event.get("severity", "low"))
        summary = str(primary_event.get("summary", "")).strip() or "当前还需要继续观察。"

        if role == UserRole.ELDER:
            first = {
                "low_oxygen_risk": "现在血氧有点偏低。",
                "temperature_warning": "现在体温有点不稳。",
                "sustained_abnormality": "现在状态需要多留意一下。",
                "alarm_ready": "现在情况不太稳定。",
                "multi_signal_deterioration": "最近身体状态有点变差。",
            }.get(event_code, "现在还需要再看看。")
            action_text = self._render_action_sentence(role, actions[0] if actions else "continue_observation")
            escalate = ""
            if severity in {"high", "critical"}:
                escalate = "如果还是不舒服，可以马上请家人或社区人员帮你看看。"
            return " ".join(part for part in [first, action_text, escalate] if part).strip()

        if role == UserRole.COMMUNITY:
            overall = {
                "critical": "当前为紧急风险。",
                "high": "当前为高风险。",
                "medium": "当前为中风险。",
            }.get(severity, "当前为低风险。")
            priority = "建议优先处理当前对象。" if severity in {"medium", "high", "critical"} else ""
            reason = f"主要问题是：{summary}"
            action = self._render_action_sentence(role, actions[0] if actions else "continue_observation")
            next_action = self._render_action_sentence(role, actions[1] if len(actions) > 1 else "")
            return " ".join(part for part in [overall, priority, reason, action, next_action] if part).strip()

        # family
        stable_text = {
            "critical": "当前整体状态不稳定，需要立即处理。",
            "high": "当前整体风险较高，需要尽快处理。",
            "medium": "当前整体存在中等风险，需要重点关注。",
        }.get(severity, "当前整体还算平稳，但需要继续观察。")
        reason = f"主要原因是：{summary}"
        action = self._render_action_sentence(role, actions[0] if actions else "continue_observation")
        escalate = self._render_escalation_sentence(event_code=event_code, latest=latest)
        return " ".join(part for part in [stable_text, reason, action, escalate] if part).strip()

    def _render_community_dialogue(
        self,
        *,
        role: UserRole,
        analysis_payload: dict[str, Any],
        event_layer: dict[str, Any],
    ) -> str:
        distribution = analysis_payload.get("risk_distribution", {}) if isinstance(analysis_payload, dict) else {}
        priority_devices = list(event_layer.get("priority_devices", [])) if isinstance(event_layer, dict) else []
        primary_event = event_layer.get("primary_event", {}) if isinstance(event_layer, dict) else {}
        actions = list(event_layer.get("action_labels", [])) if isinstance(event_layer, dict) else []
        if role == UserRole.FAMILY:
            device_count = int(analysis_payload.get("device_count", len(priority_devices) or 0))
            high_count = int(distribution.get("high", 0)) if isinstance(distribution, dict) else 0
            medium_count = int(distribution.get("medium", 0)) if isinstance(distribution, dict) else 0
            overview = (
                f"当前选中的 {device_count} 台设备里，高风险 {high_count} 台，中风险 {medium_count} 台。"
                if device_count
                else "当前选中的设备还需要继续观察。"
            )
            focus_text = ""
            if priority_devices:
                first = priority_devices[0]
                if isinstance(first, dict):
                    focus_text = (
                        f"最需要先关注的是设备 {first.get('device_mac', '')}，"
                        f"原因是 {', '.join(str(item) for item in first.get('notable_events', [])[:1]) or str(primary_event.get('summary', '当前变化更明显'))}。"
                    )
            action = self._render_action_sentence(role, actions[0] if actions else "continue_observation")
            next_action = self._render_action_sentence(role, actions[1] if len(actions) > 1 else "")
            return " ".join(part for part in [overview, focus_text, action, next_action] if part).strip()
        if role == UserRole.ELDER:
            return "现在社区正在关注整体情况，如果你感觉不舒服，可以先请家人或社区工作人员帮你看看。"

        high_count = int(distribution.get("high", 0)) if isinstance(distribution, dict) else 0
        medium_count = int(distribution.get("medium", 0)) if isinstance(distribution, dict) else 0
        overall = (
            f"当前社区整体判断为：高风险设备 {high_count} 台，中风险设备 {medium_count} 台。"
            if high_count or medium_count
            else "当前社区整体风险较低，以常规观察为主。"
        )
        priority_text = ""
        if priority_devices:
            first = priority_devices[0]
            if isinstance(first, dict):
                priority_text = (
                    f"优先处理设备 {first.get('device_mac', '')}，"
                    f"原因是 {', '.join(str(item) for item in first.get('notable_events', [])[:1]) or str(primary_event.get('summary', '存在较高关注需求'))}。"
                )
        action = self._render_action_sentence(role, actions[0] if actions else "continue_observation")
        next_action = self._render_action_sentence(role, actions[1] if len(actions) > 1 else "")
        return " ".join(part for part in [overall, priority_text, action, next_action] if part).strip()

    def _render_action_sentence(self, role: UserRole, action_code: str) -> str:
        if not action_code:
            return ""
        mapping = {
            "rest_in_sitting_position": {
                UserRole.ELDER: "建议先坐着休息一下。",
                UserRole.FAMILY: "建议先让老人保持坐位或半卧位休息。",
                UserRole.COMMUNITY: "建议先指导老人保持坐位休息。",
            },
            "remeasure_spo2_30min": {
                UserRole.ELDER: "建议 30 分钟后再量一次。",
                UserRole.FAMILY: "建议每 30 分钟复测 1 次血氧。",
                UserRole.COMMUNITY: "建议 30 分钟内完成一次复测并记录结果。",
            },
            "watch_breathing_symptoms": {
                UserRole.ELDER: "如果觉得喘不过气，要马上告诉家人。",
                UserRole.FAMILY: "请留意是否出现气短、胸闷或呼吸不顺。",
                UserRole.COMMUNITY: "电话核实时要重点询问呼吸症状变化。",
            },
            "seek_medical_help_if_persistent": {
                UserRole.ELDER: "如果一直没有好转，可以请家人尽快带你去看医生。",
                UserRole.FAMILY: "如果持续异常没有改善，请尽快联系医生或就医。",
                UserRole.COMMUNITY: "若持续异常，应升级为转诊或现场干预。",
            },
            "notify_family_member": {
                UserRole.ELDER: "可以请家人现在帮你看一下。",
                UserRole.FAMILY: "建议现在把情况同步给主要照护家属。",
                UserRole.COMMUNITY: "建议同步通知家属参与后续处理。",
            },
            "community_followup_needed": {
                UserRole.ELDER: "可以请社区人员帮忙留意一下。",
                UserRole.FAMILY: "如家里处理不便，可请社区人员跟进。",
                UserRole.COMMUNITY: "建议尽快列入社区跟进清单。",
            },
            "prioritize_phone_followup": {
                UserRole.COMMUNITY: "建议先电话随访核实当前状态。",
            },
            "arrange_onsite_review": {
                UserRole.COMMUNITY: "如电话随访无法确认状态，建议安排上门复核。",
            },
            "continue_observation": {
                UserRole.ELDER: "现在先继续观察一下就好。",
                UserRole.FAMILY: "建议继续观察接下来几次测量变化。",
                UserRole.COMMUNITY: "先纳入常规观察即可。",
            },
            "remeasure_vitals_60min": {
                UserRole.ELDER: "可以晚一点再量一次看看。",
                UserRole.FAMILY: "建议 1 小时内再复测一次关键指标。",
                UserRole.COMMUNITY: "建议在下一轮巡查前完成一次复测。",
            },
            "remeasure_temperature_30min": {
                UserRole.ELDER: "建议过一会再量一下体温。",
                UserRole.FAMILY: "建议 30 分钟后复测体温。",
                UserRole.COMMUNITY: "建议尽快复测体温并记录变化。",
            },
            "watch_fever_symptoms": {
                UserRole.ELDER: "如果觉得发冷、发热或更不舒服，要告诉家人。",
                UserRole.FAMILY: "请同时留意精神状态、食欲和发热症状。",
                UserRole.COMMUNITY: "随访时重点核实发热相关症状和持续时间。",
            },
            "check_device_wearing": {
                UserRole.ELDER: "先看看设备有没有戴好。",
                UserRole.FAMILY: "建议先检查设备佩戴状态和电量。",
                UserRole.COMMUNITY: "建议先排查设备佩戴和采集链路。",
            },
            "remeasure_after_device_check": {
                UserRole.ELDER: "调整好设备后再量一次。",
                UserRole.FAMILY: "排查设备后建议重新测一次。",
                UserRole.COMMUNITY: "排查设备后再复测一次，确认是否仍异常。",
            },
        }
        role_mapping = mapping.get(action_code, {})
        return role_mapping.get(role, role_mapping.get(UserRole.FAMILY, ""))

    def _render_escalation_sentence(self, *, event_code: str, latest: dict[str, Any]) -> str:
        spo2 = latest.get("blood_oxygen") if isinstance(latest, dict) else None
        if event_code == "low_oxygen_risk":
            if isinstance(spo2, (int, float)):
                if spo2 <= 92:
                    return "如果连续两次低于 92%，或出现气短、胸闷，请尽快就医。"
            return "如果继续下降或伴随不适，请尽快联系医生或社区人员。"
        if event_code in {"alarm_ready", "sustained_abnormality", "multi_signal_deterioration"}:
            return "如果接下来仍持续变差，建议尽快联系医生或社区人员处理。"
        return ""

    def _build_dialogue_retrieval_query(
        self,
        *,
        scope: str,
        question: str,
        analysis_payload: dict[str, Any],
        event_layer: dict[str, Any],
    ) -> str:
        primary_event = event_layer.get("primary_event", {}) if isinstance(event_layer, dict) else {}
        action_labels = list(event_layer.get("action_labels", [])) if isinstance(event_layer, dict) else []
        if scope == "community":
            distribution = analysis_payload.get("risk_distribution", {}) if isinstance(analysis_payload, dict) else {}
            return " ".join(
                part
                for part in [
                    question,
                    str(primary_event.get("event_code", "")),
                    str(primary_event.get("summary", "")),
                    f"high={distribution.get('high', 0)}" if isinstance(distribution, dict) else "",
                    f"medium={distribution.get('medium', 0)}" if isinstance(distribution, dict) else "",
                    *action_labels[:3],
                ]
                if part
            )
        return " ".join(
            part
            for part in [
                question,
                str(primary_event.get("event_code", "")),
                str(primary_event.get("summary", "")),
                str(primary_event.get("severity", "")),
                *action_labels[:4],
            ]
            if part
        )

    def _retrieve_node(self, state: AgentState) -> AgentState:
        query = str(state.get("retrieval_query") or state.get("question", "")).strip()
        if not query:
            return {"knowledge_hits": []}

        hits = self._rag.search(
            query,
            top_k=self._settings.rag_top_k,
            network_online=False,
            allow_rerank=self._settings.qwen_enable_rerank,
        )
        return {"knowledge_hits": hits}

    def _prompt_node(self, state: AgentState) -> AgentState:
        # Extract search results from tool_results
        tool_results = list(state.get("tool_results", []))
        search_hits = []
        for res in tool_results:
            if res.get("name") == "run_tavily_search" and res.get("success"):
                data = res.get("data", {})
                if isinstance(data, dict):
                    results = data.get("results", [])
                    if isinstance(results, list):
                        for r in results:
                            search_hits.append(f"{r.get('title')}: {r.get('snippet')}")

        package = build_prompt_package(
            role=state.get("role", UserRole.FAMILY),
            scope=str(state.get("scope", "device")),
            question=str(state.get("question", "")),
            analysis_context=self._compose_analysis_context(state),
            knowledge_context="\n\n".join(state.get("knowledge_hits", [])),
            search_context="\n\n".join(search_hits),
        )
        system_text = package["system"]
        user_text = package["user"]
        prompt_text = f"{system_text}\n\n{user_text}".strip()
        messages: list[Any] = []
        if ChatPromptTemplate is not None:
            try:
                prompt = ChatPromptTemplate.from_messages([("system", system_text), ("human", user_text)])
                messages = prompt.format_messages()
            except Exception:
                messages = []
        return {
            "system_prompt": system_text,
            "user_prompt": user_text,
            "prompt_text": prompt_text,
            "messages": messages,
        }

    def _generate_node(self, state: AgentState) -> AgentState:
        return {
            "answer": self._build_answer(state),
            "selected_mode": str(state.get("selected_mode", "local")),
        }

    def _build_answer(self, state: AgentState) -> str:
        fragments = list(self._stream_build_answer(state))
        return "".join(fragment for fragment in fragments if fragment)

    def _stream_build_answer(self, state: AgentState) -> Iterator[str]:
        prompt_text = str(state.get("prompt_text", "")).strip()
        system_prompt = str(state.get("system_prompt", "")).strip()
        user_prompt = str(state.get("user_prompt", "")).strip()
        messages = list(state.get("messages", []))
        scope = str(state.get("scope", "device"))
        selected_model = str(state.get("selected_model", self._settings.local_default_model))
        selected_provider = str(state.get("selected_provider", self._settings.preferred_llm_provider))
        dialogue_expression = dict(state.get("dialogue_expression", {}))

        if not prompt_text:
            fallback = str(dialogue_expression.get("answer", "")).strip() or self._fallback_answer(state.get("analysis_payload", {}), scope)
            yield from self._iter_stream_fragments(fallback)
            return

        has_yielded = False
        for chunk in self._stream_invoke_local(
            prompt_text,
            messages,
            selected_model=selected_model,
            selected_provider=selected_provider,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_predict_tokens=self._settings.dialogue_max_predict_tokens,
        ):
            if chunk:
                has_yielded = True
                yield chunk

        if not has_yielded:
            event_answer = str(dialogue_expression.get("answer", "")).strip()
            fallback_text = event_answer if event_answer else self._fallback_answer(state.get("analysis_payload", {}), scope)
            yield from self._iter_stream_fragments(fallback_text)

    def _iter_stream_fragments(self, text: str) -> Iterator[str]:
        if not text:
            return

        fragments = [
            item
            for item in re.split(r"(?<=[，。！？；：,.!?;\n])", text)
            if item
        ]
        if not fragments:
            fragments = [text]

        for fragment in fragments:
            current = fragment
            while len(current) > 20:
                split_at = 15
                for separator in ("，", "。", "！", "？", "；", "：", ",", ".", "!", "?", ";", "\n", " "):
                    candidate = current.rfind(separator, 0, 20)
                    if candidate >= 3:
                        split_at = candidate + 1
                        break
                piece = current[:split_at]
                if piece:
                    yield piece
                current = current[split_at:]
            if current:
                yield current

    def _stream_invoke_local(
        self,
        prompt_text: str,
        messages: list[Any],
        *,
        selected_model: str,
        selected_provider: str = "",
        system_prompt: str = "",
        user_prompt: str = "",
        max_predict_tokens: int | None = None,
    ) -> Iterator[str]:
        provider = (selected_provider or self._settings.preferred_llm_provider).strip().lower()
        local_fallback_model = self._settings.local_reasoning_model or self._settings.local_default_model

        if provider == "qwen":
            # Attempt Tongyi streaming if available
            stream = self._stream_call_tongyi(
                prompt_text,
                messages,
                selected_model=selected_model,
                max_predict_tokens=max_predict_tokens,
            )
            if stream:
                yield from stream
                return

        # Fallback to Ollama or compatible HTTP streaming
        if ChatOllama is not None:
            local_llm = self._build_local_llm(
                local_fallback_model if provider == "qwen" else selected_model,
                max_predict_tokens=max_predict_tokens,
                streaming=True,
            )
            if local_llm is not None:
                try:
                    for chunk in local_llm.stream(messages or prompt_text):
                        text = self._extract_message_text(chunk)
                        if text:
                            yield text
                    return
                except Exception:
                    pass

        # Final HTTP-based streaming fallback if needed (Ollama only for now)
        yield from self._stream_call_ollama_http(
            prompt_text,
            selected_model=local_fallback_model if provider == "qwen" else selected_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_predict_tokens=max_predict_tokens,
        )

    def _stream_call_tongyi(
        self,
        prompt_text: str,
        messages: list[Any],
        *,
        selected_model: str,
        max_predict_tokens: int | None = None,
    ) -> Iterator[str] | None:
        if ChatTongyi is None or not self._settings.qwen_llm_configured:
            return None
        cloud_llm = self._build_tongyi_llm(selected_model, max_predict_tokens=max_predict_tokens, streaming=True)
        if cloud_llm is None:
            return None
        try:
            for chunk in cloud_llm.stream(messages or prompt_text):
                text = self._extract_message_text(chunk)
                if text:
                    yield text
        except Exception:
            return None

    def _build_tongyi_llm(self, model_name: str, *, max_predict_tokens: int | None = None, streaming: bool = False):
        if ChatTongyi is None or not self._settings.qwen_llm_configured:
            return None
        cache_key = f"tongyi|{model_name}|{max_predict_tokens or 'default'}|{streaming}"
        if cache_key in self._local_llms:
            return self._local_llms[cache_key]
        try:
            kwargs: dict[str, Any] = {
                "model": model_name,
                "api_key": self._settings.qwen_api_key,
                "streaming": streaming,
            }
            if max_predict_tokens is not None:
                kwargs["max_tokens"] = max_predict_tokens
            llm = ChatTongyi(**kwargs)
            self._local_llms[cache_key] = llm
            return llm
        except Exception:
            return None

    def _build_local_llm(self, model_name: str, *, max_predict_tokens: int | None = None, streaming: bool = False):
        if ChatOllama is None:
            return None
        cache_key = f"{model_name}|{max_predict_tokens or 'default'}|{streaming}"
        if cache_key in self._local_llms:
            return self._local_llms[cache_key]
        try:
            kwargs: dict[str, Any] = {
                "model": model_name,
                "base_url": self._settings.ollama_base_url,
                "temperature": 0.2,
            }
            if max_predict_tokens is not None:
                kwargs["num_predict"] = max_predict_tokens
            # Some ChatOllama versions might not support streaming flag in constructor but do in stream() method
            llm = ChatOllama(**kwargs)
            self._local_llms[cache_key] = llm
            return llm
        except Exception:
            return None

    def _stream_call_ollama_http(
        self,
        prompt_text: str,
        *,
        selected_model: str,
        system_prompt: str = "",
        user_prompt: str = "",
        max_predict_tokens: int | None = None,
    ) -> Iterator[str]:
        url = f"{self._settings.ollama_base_url.rstrip('/')}/api/chat"
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if user_prompt:
            messages.append({"role": "user", "content": user_prompt})
        if not messages:
            messages.append({"role": "user", "content": prompt_text})
        payload = json.dumps(
            {
                "model": selected_model,
                "stream": True,
                "messages": messages,
                "options": {"num_predict": max_predict_tokens} if max_predict_tokens is not None else {},
            },
            ensure_ascii=False,
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        
        req = request.Request(url=url, data=payload, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=self._settings.llm_timeout_seconds) as response:
                for line in response:
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line.decode("utf-8"))
                        content = chunk.get("message", {}).get("content")
                        if content:
                            yield content
                        if chunk.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass

    def _aggregate_node(self, state: AgentState) -> AgentState:
        attachments = self._collect_attachments(list(state.get("tool_results", [])))
        context_bundle = dict(state.get("context_bundle", {}))
        subject = context_bundle.get("elder_profile") if str(state.get("scope", "device")) == "elder" else context_bundle.get("community")
        final_payload = {
            "scope": str(state.get("scope", "device")),
            "window": str(state.get("window") or self._window_value_from_history(int(state.get("history_minutes", 1440) or 1440))),
            "mode": str(state.get("selected_mode", "local")),
            "network_online": bool(state.get("network_online", False)),
            "selected_provider": str(state.get("selected_provider", self._settings.preferred_llm_provider)),
            "selected_model": str(state.get("selected_model", self._settings.local_default_model)),
            "answer": str(state.get("answer", "")).strip(),
            "references": list(state.get("knowledge_hits", [])),
            "analysis": dict(state.get("analysis_payload", {})),
            "context": context_bundle,
            "subject": subject if isinstance(subject, dict) else None,
            "tool_results": list(state.get("tool_results", [])),
            "attachments": attachments,
            "model_results": dict(state.get("model_results", {})),
            "degraded": list(state.get("degraded_notes", [])),
        }
        return {"final_payload": final_payload}

    @staticmethod
    def _collect_attachments(tool_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        attachments: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for item in tool_results:
            for attachment in item.get("attachments", []):
                if not isinstance(attachment, dict):
                    continue
                attachment_id = str(attachment.get("id", "")).strip()
                if not attachment_id or attachment_id in seen_ids:
                    continue
                seen_ids.add(attachment_id)
                attachments.append(attachment)
        return attachments

    def _build_stage_notes(self, stage: str, state: AgentState) -> list[str]:
        if stage == "route":
            provider = str(state.get("selected_provider", self._settings.preferred_llm_provider))
            model_name = state.get("selected_model", self._settings.local_default_model)
            provider_label = "Tongyi/Qwen API" if provider == "qwen" else "本地 Ollama"
            return [f"已选择 {provider_label}，模型 {model_name}。"]
        if stage == "context":
            context_bundle = state.get("context_bundle", {})
            if isinstance(context_bundle, dict):
                return [f"已整理 {len(context_bundle.keys())} 组业务上下文。"]
        if stage == "tools":
            tool_results = list(state.get("tool_results", []))
            return [f"已完成 {len(tool_results)} 个工具调用。"] if tool_results else []
        if stage == "analysis":
            analysis_payload = state.get("analysis_payload", {})
            if isinstance(analysis_payload, dict):
                risk_level = str(analysis_payload.get("risk_level", "")).strip()
                device_count = analysis_payload.get("device_count")
                if risk_level and device_count is not None:
                    return [f"社区结构分析完成，当前风险等级分布已更新，覆盖 {device_count} 台设备。"]
                if risk_level:
                    return [f"结构分析完成，当前综合风险等级为 {risk_level}。"]
        if stage == "models":
            model_results = state.get("model_results", {})
            if isinstance(model_results, dict) and model_results:
                return [f"已整合 {len(model_results.keys())} 路模型信号。"]
        if stage == "dialogue":
            events = state.get("dialogue_events", [])
            if isinstance(events, list) and events:
                return [str(event.get("title", "") or event.get("message", "")).strip() for event in events[:3] if isinstance(event, dict)]
        if stage == "retrieve":
            hits = list(state.get("knowledge_hits", []))
            return [f"检索到 {len(hits)} 条参考信息。"] if hits else ["未命中额外参考信息，继续使用本地上下文生成结果。"]
        if stage == "prompt":
            return ["已构建回答提示，不向前端暴露原始提示内容。"]
        if stage == "generate":
            answer = str(state.get("answer", "")).strip()
            return ["回答已生成，正在推送到前端。"] if answer else []
        if stage == "aggregate":
            return ["已聚合最终回答、分析摘要和参考信息。"]
        return []

    def _chunk_answer(self, answer: str, *, size: int = 32) -> list[str]:
        text = answer.strip()
        if not text:
            return []
        return [text[index:index + size] for index in range(0, len(text), size)]

    def _invoke_local(
        self,
        prompt_text: str,
        messages: list[Any],
        *,
        selected_model: str,
        selected_provider: str = "",
        system_prompt: str = "",
        user_prompt: str = "",
        max_predict_tokens: int | None = None,
        max_output_chars: int | None = None,
    ) -> str | None:
        provider = (selected_provider or self._settings.preferred_llm_provider).strip().lower()
        local_fallback_model = self._settings.local_reasoning_model or self._settings.local_default_model

        if provider == "qwen":
            answer = self._truncate_output(
                self._call_tongyi(
                    prompt_text,
                    messages,
                    selected_model=selected_model,
                    max_predict_tokens=max_predict_tokens,
                ),
                max_output_chars,
            )
            if answer:
                return answer
            answer = self._truncate_output(
                self._call_qwen_compatible_http(
                    prompt_text,
                    selected_model=selected_model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_predict_tokens=max_predict_tokens,
                ),
                max_output_chars,
            )
            if answer:
                return answer

        if ChatOllama is not None:
            local_llm = self._build_local_llm(
                local_fallback_model if provider == "qwen" else selected_model,
                max_predict_tokens=max_predict_tokens,
            )
            if local_llm is not None:
                try:
                    response = local_llm.invoke(messages or prompt_text)
                    answer = self._extract_message_text(response)
                    if answer:
                        return self._truncate_output(answer, max_output_chars)
                except Exception:
                    pass
        return self._truncate_output(
            self._call_ollama_http(
                prompt_text,
                selected_model=local_fallback_model if provider == "qwen" else selected_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_predict_tokens=max_predict_tokens,
            ),
            max_output_chars,
        )

    def _call_tongyi(
        self,
        prompt_text: str,
        messages: list[Any],
        *,
        selected_model: str,
        max_predict_tokens: int | None = None,
    ) -> str | None:
        if ChatTongyi is None or not self._settings.qwen_llm_configured:
            return None
        cloud_llm = self._build_tongyi_llm(selected_model, max_predict_tokens=max_predict_tokens)
        if cloud_llm is None:
            return None
        try:
            response = cloud_llm.invoke(messages or prompt_text)
            return self._extract_message_text(response)
        except Exception:
            return None

    def _call_qwen_compatible_http(
        self,
        prompt_text: str,
        *,
        selected_model: str,
        system_prompt: str = "",
        user_prompt: str = "",
        max_predict_tokens: int | None = None,
    ) -> str | None:
        if not self._settings.qwen_llm_configured:
            return None
        base = self._settings.qwen_api_base.rstrip("/")
        url = base if base.endswith("/chat/completions") else f"{base}/chat/completions"
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if user_prompt:
            messages.append({"role": "user", "content": user_prompt})
        if not messages:
            messages.append({"role": "user", "content": prompt_text})
        body: dict[str, Any] = {
            "model": selected_model,
            "messages": messages,
            "temperature": 0.2,
            "stream": False,
        }
        if max_predict_tokens is not None:
            body["max_tokens"] = max_predict_tokens
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._settings.qwen_api_key}",
        }
        return self._post_json(url, payload, headers, parser=self._extract_openai_compatible_content)

    def _call_ollama_http(
        self,
        prompt_text: str,
        *,
        selected_model: str,
        system_prompt: str = "",
        user_prompt: str = "",
        max_predict_tokens: int | None = None,
    ) -> str | None:
        url = f"{self._settings.ollama_base_url.rstrip('/')}/api/chat"
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if user_prompt:
            messages.append({"role": "user", "content": user_prompt})
        if not messages:
            messages.append({"role": "user", "content": prompt_text})
        payload = json.dumps(
            {
                "model": selected_model,
                "stream": False,
                "messages": messages,
                "options": {"num_predict": max_predict_tokens} if max_predict_tokens is not None else {},
            },
            ensure_ascii=False,
        ).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        return self._post_json(
            url,
            payload,
            headers,
            parser=lambda body: body.get("message", {}).get("content"),
        )

    @staticmethod
    def _truncate_output(text: str | None, max_output_chars: int | None) -> str | None:
        if text is None:
            return None
        value = str(text).strip()
        if not value:
            return None
        if max_output_chars is None or max_output_chars <= 0 or len(value) <= max_output_chars:
            return value
        clipped = value[:max_output_chars]
        sentence_break = max(
            clipped.rfind("。"),
            clipped.rfind("！"),
            clipped.rfind("？"),
            clipped.rfind(". "),
            clipped.rfind("! "),
            clipped.rfind("? "),
            clipped.rfind("；"),
            clipped.rfind(";"),
        )
        if sentence_break >= max(0, max_output_chars // 2):
            clipped = clipped[: sentence_break + 1]
        clipped = clipped.rstrip(" \n，,;；:：")
        return f"{clipped}…"

    def _post_json(self, url: str, payload: bytes, headers: dict[str, str], parser) -> str | None:
        req = request.Request(url=url, data=payload, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=self._settings.llm_timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
                parsed = parser(body)
                return str(parsed).strip() if parsed else None
        except (error.URLError, error.HTTPError, TimeoutError, json.JSONDecodeError):
            return None

    def _build_report_model_signals(
        self,
        *,
        role: UserRole,
        device_mac: str,
        samples: list[HealthSample],
        context_bundle: dict[str, Any],
    ) -> dict[str, Any]:
        if self._model_suite is None or not samples:
            return {}
        active_alarm_rows = context_bundle.get("active_alarms", []) if isinstance(context_bundle, dict) else []
        alarms = [_alarm_from_payload(row) for row in active_alarm_rows if isinstance(row, dict)]
        try:
            results = self._model_suite.run_all(
                AgentModelInput(
                    scope="device",
                    role=role,
                    question="health report",
                    device_mac=device_mac.upper(),
                    samples=samples,
                    alarms=alarms,
                    context=context_bundle if isinstance(context_bundle, dict) else {},
                )
            )
        except Exception:
            return {}

        payload: dict[str, Any] = {}
        for key in (
            "health_assessment",
            "risk_scoring",
            "anomaly_explain",
            "care_suggestion",
            "alarm_interpretation",
        ):
            result = results.get(key)
            if result is None:
                continue
            payload[key] = {
                "status": result.status,
                "source": result.source,
                "summary": result.summary,
                "payload": dict(result.payload),
                "confidence": result.confidence,
            }
        return payload

    def _build_report_health_model_evidence(
        self,
        *,
        device_mac: str,
        samples: list[HealthSample],
        analysis_payload: dict[str, Any],
        model_signals: dict[str, Any],
    ) -> dict[str, Any]:
        risk_level = str(analysis_payload.get("risk_level", "unknown")) if isinstance(analysis_payload, dict) else "unknown"
        raw_risk_flags = list(analysis_payload.get("risk_flags", [])) if isinstance(analysis_payload, dict) else []
        risk_flags = self._unique_texts(
            [flag for flag in raw_risk_flags if str(flag).strip() and str(flag) != "within_expected_range"],
            limit=8,
        )
        latest = analysis_payload.get("latest", {}) if isinstance(analysis_payload, dict) else {}
        averages = analysis_payload.get("averages", {}) if isinstance(analysis_payload, dict) else {}
        trend = analysis_payload.get("trend", {}) if isinstance(analysis_payload, dict) else {}
        notable_events = list(analysis_payload.get("notable_events", [])) if isinstance(analysis_payload, dict) else []
        recommendations = list(analysis_payload.get("recommendations", [])) if isinstance(analysis_payload, dict) else []

        health_assessment_signal = model_signals.get("health_assessment", {})
        risk_signal = model_signals.get("risk_scoring", {})
        care_signal = model_signals.get("care_suggestion", {})
        alarm_signal = model_signals.get("alarm_interpretation", {})
        anomaly_payload = self._extract_report_anomaly_payload(model_signals)

        health_assessment_payload = health_assessment_signal.get("payload", {}) if isinstance(health_assessment_signal, dict) else {}
        risk_signal_payload = risk_signal.get("payload", {}) if isinstance(risk_signal, dict) else {}
        care_signal_payload = care_signal.get("payload", {}) if isinstance(care_signal, dict) else {}
        alarm_signal_payload = alarm_signal.get("payload", {}) if isinstance(alarm_signal, dict) else {}

        latest_health_score = latest.get("health_score") if isinstance(latest, dict) else None
        if not isinstance(latest_health_score, (int, float)):
            latest_health_score = risk_signal_payload.get("score") if isinstance(risk_signal_payload, dict) else None
        average_health_score = averages.get("health_score") if isinstance(averages, dict) else None

        trend_evidence = self._build_report_trend_evidence(trend if isinstance(trend, dict) else {})
        derived_sustained = self._derive_report_sustained_abnormality(samples=samples, anomaly_payload=anomaly_payload)
        anomaly_reason = str(anomaly_payload.get("reason", "")).strip()
        anomaly_probability = anomaly_payload.get("probability")
        if not isinstance(anomaly_probability, (int, float)):
            anomaly_probability = None
        sustained_minutes = anomaly_payload.get("sustained_minutes")
        if isinstance(sustained_minutes, (int, float)) and sustained_minutes > 0:
            sustained_minutes = float(sustained_minutes)
        else:
            sustained_minutes = float(derived_sustained["sustained_minutes"])
        alarm_ready = bool(anomaly_payload.get("alarm_ready", False)) or bool(derived_sustained["alarm_ready"])
        normalized_anomaly_payload = dict(anomaly_payload)
        normalized_anomaly_payload["sustained_minutes"] = sustained_minutes
        normalized_anomaly_payload["alarm_ready"] = alarm_ready
        normalized_anomaly_payload["abnormal_points"] = derived_sustained["abnormal_points"]
        anomaly_stage = self._classify_report_anomaly_stage(
            risk_level=risk_level,
            anomaly_payload=normalized_anomaly_payload,
            risk_flags=risk_flags,
        )
        active_alarm_count = (
            int(alarm_signal_payload.get("active_alarm_count", 0))
            if isinstance(alarm_signal_payload, dict)
            else 0
        )
        care_recommendations = (
            [str(item) for item in care_signal_payload.get("recommendations", [])]
            if isinstance(care_signal_payload, dict) and isinstance(care_signal_payload.get("recommendations"), list)
            else []
        )

        key_evidence: list[str] = []
        if isinstance(latest_health_score, (int, float)):
            key_evidence.append(f"当前健康评分为 {round(float(latest_health_score), 1)} 分。")
        if risk_flags:
            key_evidence.append(f"当前主要风险标志包括：{'、'.join(risk_flags[:3])}。")
        if isinstance(health_assessment_signal, dict) and str(health_assessment_signal.get("summary", "")).strip():
            key_evidence.append(str(health_assessment_signal.get("summary", "")).strip())
        key_evidence.extend(trend_evidence[:2])
        if isinstance(anomaly_probability, (int, float)):
            key_evidence.append(
                f"时序模型评估异常概率约为 {anomaly_probability:.0%}，"
                f"主要依据：{anomaly_reason or '多指标联合偏移'}。"
            )
        if sustained_minutes > 0:
            key_evidence.append(f"持续异常已累计约 {sustained_minutes:.0f} 分钟。")
        if alarm_ready:
            key_evidence.append("持续异常已达到智能告警条件。")
        if active_alarm_count > 0:
            key_evidence.append(f"当前仍有 {active_alarm_count} 条未确认告警需要复核。")

        summary_inputs: list[str] = [f"综合风险等级为 {self._risk_label(risk_level)}。"]
        if isinstance(latest_health_score, (int, float)):
            summary_inputs.append(f"当前健康评分 {round(float(latest_health_score), 1)}。")
        if notable_events:
            summary_inputs.append(str(notable_events[0]))
        summary_inputs.extend(trend_evidence[:2])
        if alarm_ready:
            summary_inputs.append("时序模型判断当前异常已达到持续告警条件。")
        elif isinstance(anomaly_probability, (int, float)) and anomaly_stage != "normal":
            summary_inputs.append(f"时序模型异常概率约 {anomaly_probability:.0%}。")

        report_recommendations: list[str] = []
        if alarm_ready:
            report_recommendations.append("时序模型判断已达到持续异常告警条件，建议优先按告警流程复核老人当前状态，并确认是否需要现场干预。")
        elif anomaly_stage == "sustained_abnormal":
            report_recommendations.append("时序模型提示异常趋势已持续，建议缩短复测间隔并尽快电话核查。")
        elif anomaly_stage == "abnormal":
            report_recommendations.append("时序模型提示存在早期异常波动，建议继续复测并重点观察趋势变化。")
        if alarm_ready:
            report_recommendations.append("建议优先按照持续异常告警流程复核老人当前状态，并确认是否需要现场干预。")
        elif anomaly_stage == "sustained_abnormal":
            report_recommendations.append("时序模型提示异常趋势已持续，建议缩短复测间隔并尽快电话核查。")
        elif anomaly_stage == "abnormal":
            report_recommendations.append("时序模型提示存在早期异常波动，建议继续复测并重点观察趋势变化。")
        if active_alarm_count > 0:
            report_recommendations.append("建议同步核对当前未确认告警，避免遗漏需要立即处理的异常。")
        report_recommendations.extend(care_recommendations[:3])
        report_recommendations.extend(recommendations[:3])

        return {
            "evidence_version": "hm_report_v2",
            "device_mac": device_mac.upper(),
            "input_window": {
                "report_sample_count": len(samples),
                "transformer_window": 6,
                "feature_names": ["heart_rate", "temperature", "blood_oxygen", "systolic"],
            },
            "health_score": {
                "latest": latest_health_score,
                "average": average_health_score,
                "source": "health_score_model",
            },
            "risk_level": risk_level,
            "risk_flags": risk_flags,
            "anomaly_stage": anomaly_stage,
            "health_assessment_summary": str(health_assessment_signal.get("summary", "")).strip() if isinstance(health_assessment_signal, dict) else "",
            "risk_scoring_summary": str(risk_signal.get("summary", "")).strip() if isinstance(risk_signal, dict) else "",
            "alarm_summary": str(alarm_signal.get("summary", "")).strip() if isinstance(alarm_signal, dict) else "",
            "active_alarm_count": active_alarm_count,
            "sustained_abnormality": {
                "alarm_ready": alarm_ready,
                "sustained_minutes": sustained_minutes,
                "probability": anomaly_probability,
                "score": anomaly_payload.get("score"),
                "reason": anomaly_reason or None,
                "abnormal_points": derived_sustained["abnormal_points"],
            },
            "trend_evidence": trend_evidence,
            "key_evidence": self._unique_texts(key_evidence, limit=8),
            "summary_inputs": self._unique_texts(summary_inputs, limit=6),
            "key_findings": self._unique_texts(key_evidence + notable_events, limit=6),
            "recommendations": self._unique_texts(report_recommendations, limit=5),
            "care_recommendations": self._unique_texts(care_recommendations, limit=4),
            "model_payloads": {
                "health_assessment": health_assessment_payload if isinstance(health_assessment_payload, dict) else {},
                "risk_scoring": risk_signal_payload if isinstance(risk_signal_payload, dict) else {},
                "anomaly_explain": normalized_anomaly_payload if isinstance(normalized_anomaly_payload, dict) else {},
                "care_suggestion": care_signal_payload if isinstance(care_signal_payload, dict) else {},
                "alarm_interpretation": alarm_signal_payload if isinstance(alarm_signal_payload, dict) else {},
            },
        }

    def _build_report_trend_evidence(self, trend: dict[str, Any]) -> list[str]:
        evidence: list[str] = []
        for metric_name in ("blood_oxygen", "temperature", "heart_rate", "health_score"):
            row = trend.get(metric_name, {})
            if not isinstance(row, dict):
                continue
            label = self._trend_label_for_report(str(row.get("label", "")))
            if label in {"稳定", "数据不足", ""}:
                continue
            delta = row.get("delta")
            delta_text = f"{delta:+.2f}" if isinstance(delta, (int, float)) else ""
            metric_label = self._metric_label_for_report(metric_name)
            if delta_text:
                evidence.append(f"{metric_label}趋势{label}，变化幅度 {delta_text}。")
            else:
                evidence.append(f"{metric_label}趋势{label}。")
        return evidence

    @staticmethod
    def _metric_label_for_report(metric_name: str) -> str:
        return {
            "blood_oxygen": "血氧",
            "temperature": "体温",
            "heart_rate": "心率",
            "health_score": "健康评分",
        }.get(metric_name, metric_name)

    @staticmethod
    def _trend_label_for_report(label: str) -> str:
        return {
            "rising": "上升",
            "falling": "下降",
            "stable": "稳定",
            "insufficient_data": "数据不足",
        }.get(label, label)

    def _derive_report_sustained_abnormality(
        self,
        *,
        samples: list[HealthSample],
        anomaly_payload: dict[str, Any],
    ) -> dict[str, object]:
        if not samples:
            return {"sustained_minutes": 0.0, "alarm_ready": False, "abnormal_points": 0}

        abnormal_points = []
        for sample in samples:
            flags = [flag for flag in self._analysis._risk_flags(sample) if flag != "within_expected_range"]
            if flags:
                abnormal_points.append(sample)

        if not abnormal_points:
            return {"sustained_minutes": 0.0, "alarm_ready": False, "abnormal_points": 0}

        sustained_minutes = max(
            (abnormal_points[-1].timestamp - abnormal_points[0].timestamp).total_seconds() / 60.0,
            0.0,
        )
        probability = anomaly_payload.get("probability")
        alarm_ready = len(abnormal_points) >= 3 and sustained_minutes >= 20
        if isinstance(probability, (int, float)) and probability >= 0.8 and len(abnormal_points) >= 2:
            alarm_ready = True
        return {
            "sustained_minutes": sustained_minutes,
            "alarm_ready": alarm_ready,
            "abnormal_points": len(abnormal_points),
        }

    def _classify_report_anomaly_stage(
        self,
        *,
        risk_level: str,
        anomaly_payload: dict[str, Any],
        risk_flags: list[str],
    ) -> str:
        if anomaly_payload.get("alarm_ready") is True:
            return "alarm"
        sustained_minutes = anomaly_payload.get("sustained_minutes")
        probability = anomaly_payload.get("probability")
        if isinstance(sustained_minutes, (int, float)) and sustained_minutes >= 20:
            return "sustained_abnormal"
        if isinstance(probability, (int, float)) and probability >= 0.45:
            return "abnormal"
        if risk_level in {"high", "medium"} or any(flag.endswith("_warning") or flag.endswith("_critical") for flag in risk_flags):
            return "abnormal"
        return "normal"

    def _build_report_key_findings(
        self,
        analysis_payload: dict[str, Any],
        *,
        model_signals: dict[str, Any],
        health_model_evidence: dict[str, Any],
    ) -> list[str]:
        del model_signals
        findings = list(health_model_evidence.get("key_findings", []))
        if isinstance(analysis_payload, dict):
            findings.extend(list(analysis_payload.get("notable_events", [])))
        return self._unique_texts(findings, limit=6)

    def _build_report_recommendations(
        self,
        analysis_payload: dict[str, Any],
        *,
        model_signals: dict[str, Any],
        health_model_evidence: dict[str, Any],
    ) -> list[str]:
        del model_signals
        recommendations = list(health_model_evidence.get("recommendations", []))
        if isinstance(analysis_payload, dict):
            recommendations.extend(list(analysis_payload.get("recommendations", [])))
        return self._unique_texts(recommendations, limit=5)

    def _build_retrieval_query(self, *, scope: str, question: str, analysis_payload: dict[str, Any]) -> str:
        if scope == "community":
            distribution = analysis_payload.get("risk_distribution", {})
            priority_devices = analysis_payload.get("priority_devices", [])
            focus_terms: list[str] = []
            if isinstance(priority_devices, list):
                for item in priority_devices[:3]:
                    if not isinstance(item, dict):
                        continue
                    flags = item.get("risk_flags", [])
                    joined_flags = " ".join(str(flag) for flag in flags)
                    focus_terms.append(f"{item.get('device_mac', '')} {joined_flags}".strip())
            return " ".join(
                part
                for part in [
                    question or "summarize recent community health data",
                    "community elder care prioritization risk distribution patrol follow-up",
                    f"high={distribution.get('high', 0)}",
                    f"medium={distribution.get('medium', 0)}",
                    *focus_terms,
                ]
                if part
            )

        risk_flags = analysis_payload.get("risk_flags", [])
        notable_events = analysis_payload.get("notable_events", [])
        return " ".join(
            part
            for part in [
                question or "analyze recent device health data",
                "elder health monitoring trends risk follow-up suggestions",
                *(str(flag) for flag in risk_flags[:4]),
                *(str(event) for event in notable_events[:2]),
            ]
            if part
        )

    def _build_report_retrieval_query(
        self,
        *,
        role: UserRole,
        device_mac: str,
        start_at: datetime,
        end_at: datetime,
        analysis_payload: dict[str, Any],
        model_signals: dict[str, Any],
        health_model_evidence: dict[str, Any],
    ) -> str:
        risk_flags = analysis_payload.get("risk_flags", [])
        notable_events = analysis_payload.get("notable_events", [])
        recommendations = analysis_payload.get("recommendations", [])
        trend = analysis_payload.get("trend", {})
        duration_minutes = max(int((end_at - start_at).total_seconds() // 60), 0)
        role_hint = "family report template wording follow-up guidance" if role == UserRole.FAMILY else "community report template handoff wording patrol follow-up"
        anomaly_summary = ""
        anomaly_reason = ""
        anomaly_payload = self._extract_report_anomaly_payload(model_signals)
        anomaly_signal = model_signals.get("anomaly_explain", {})
        if isinstance(anomaly_signal, dict):
            anomaly_summary = str(anomaly_signal.get("summary", ""))
        if anomaly_payload:
            anomaly_reason = str(anomaly_payload.get("reason", ""))
        trend_terms: list[str] = []
        if isinstance(trend, dict):
            for metric_name, row in trend.items():
                if not isinstance(row, dict):
                    continue
                trend_terms.append(f"{metric_name} {row.get('label', '')}".strip())
        return " ".join(
            part
            for part in [
                "health report report template wording guide event interpretation follow-up guidance",
                "时间段 健康报告 指标解释 趋势含义 风险说明 报告措辞模板",
                role_hint,
                device_mac,
                f"duration_minutes={duration_minutes}",
                *(str(flag) for flag in risk_flags[:4]),
                *(str(event) for event in notable_events[:2]),
                *(str(item) for item in recommendations[:2]),
                anomaly_summary,
                anomaly_reason,
                f"sustained_minutes={anomaly_payload.get('sustained_minutes', '')}",
                "transformer temporal attention sustained anomaly report wording",
                *(str(item) for item in health_model_evidence.get("summary_inputs", [])[:3]),
                *(str(item) for item in health_model_evidence.get("key_evidence", [])[:3]),
                *trend_terms[:4],
            ]
            if part
        )

    def _format_result(self, result: AgentState) -> dict[str, object]:
        final_payload = result.get("final_payload")
        if isinstance(final_payload, dict) and final_payload:
            answer = str(final_payload.get("answer", "")).strip()
            if not answer:
                final_payload["answer"] = self._fallback_answer(
                    result.get("analysis_payload", {}),
                    str(result.get("scope", "device")),
                )
            return sanitize_agent_response(final_payload)

        answer = str(result.get("answer", "")).strip()
        scope = str(result.get("scope", "device"))
        if not answer:
            answer = self._fallback_answer(result.get("analysis_payload", {}), scope)
        return sanitize_agent_response(
            {
                "scope": scope,
                "mode": str(result.get("selected_mode", "local")),
                "network_online": bool(result.get("network_online", False)),
                "selected_provider": str(result.get("selected_provider", self._settings.preferred_llm_provider)),
                "selected_model": str(result.get("selected_model", self._settings.local_default_model)),
                "answer": answer,
                "references": list(result.get("knowledge_hits", [])),
                "analysis": dict(result.get("analysis_payload", {})),
            }
        )

    def _compose_analysis_context(self, state: AgentState) -> str:
        sections = [
            "### Analysis",
            json.dumps(
                self._sanitize_agent_content(state.get("analysis_payload", {})),
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
        ]
        conversation_history = state.get("conversation_history", [])
        if conversation_history:
            sections.extend(
                [
                    "### Conversation History",
                    json.dumps(conversation_history, ensure_ascii=False, indent=2, default=str),
                ]
            )
        dialogue_events = state.get("dialogue_events", [])
        if dialogue_events:
            sections.extend(
                [
                    "### Health Events",
                    json.dumps(
                        self._sanitize_agent_content(dialogue_events),
                        ensure_ascii=False,
                        indent=2,
                        default=str,
                    ),
                ]
            )
        dialogue_action_labels = state.get("dialogue_action_labels", [])
        if dialogue_action_labels:
            sections.extend(
                [
                    "### Action Labels",
                    json.dumps(
                        self._sanitize_agent_content(dialogue_action_labels),
                        ensure_ascii=False,
                        indent=2,
                        default=str,
                    ),
                ]
            )
        context_bundle = state.get("context_bundle", {})
        if context_bundle:
            sections.extend(
                [
                    "### Business Context",
                    json.dumps(
                        self._sanitize_agent_content(context_bundle),
                        ensure_ascii=False,
                        indent=2,
                        default=str,
                    ),
                ]
            )
        tool_results = state.get("tool_results", [])
        if tool_results:
            sections.extend(
                [
                    "### Tool Results",
                    json.dumps(
                        self._sanitize_agent_content(tool_results),
                        ensure_ascii=False,
                        indent=2,
                        default=str,
                    ),
                ]
            )
        model_results = state.get("model_results", {})
        if model_results:
            sections.extend(
                [
                    "### Model Results",
                    json.dumps(
                        self._sanitize_agent_content(model_results),
                        ensure_ascii=False,
                        indent=2,
                        default=str,
                    ),
                ]
            )
        degraded_notes = state.get("degraded_notes", [])
        if degraded_notes:
            sections.extend(
                [
                    "### Degraded Notes",
                    json.dumps(degraded_notes, ensure_ascii=False, indent=2, default=str),
                ]
            )
        return "\n\n".join(section for section in sections if section)

    def _build_report_prompt(
        self,
        *,
        role: UserRole,
        device_mac: str,
        start_at: datetime,
        end_at: datetime,
        analysis_payload: dict[str, Any],
        knowledge_hits: list[str],
        context_bundle: dict[str, Any],
        model_signals: dict[str, Any],
        health_model_evidence: dict[str, Any],
    ) -> dict[str, Any]:
        role_prompt = "Generate a family health report for this time window." if role == UserRole.FAMILY else "Generate a community-facing health report for this time window."
        report_context = {
            "device_mac": device_mac.upper(),
            "period": {
                "start_at": start_at.astimezone(timezone.utc).isoformat(),
                "end_at": end_at.astimezone(timezone.utc).isoformat(),
                "duration_minutes": max(int((end_at - start_at).total_seconds() // 60), 0),
            },
            "analysis_payload": analysis_payload,
            "context_bundle": context_bundle,
            "model_signals": model_signals,
            "health_model_evidence": health_model_evidence,
            "report_requirements": {
                "audience": "family" if role == UserRole.FAMILY else "community operator",
                "must_cover": [
                    "summary",
                    "indicator interpretation",
                    "risk judgment",
                    "recommended actions",
                    "uncertainty or data quality note",
                ],
            },
        }
        package = build_prompt_package(
            role=role,
            scope="device",
            question=role_prompt,
            analysis_context=json.dumps(report_context, ensure_ascii=False, indent=2, default=str),
            knowledge_context="\n\n".join(knowledge_hits),
        )
        system_text = package["system"]
        user_text = package["user"]
        prompt_text = f"{system_text}\n\n{user_text}".strip()
        messages: list[Any] = []
        if ChatPromptTemplate is not None:
            try:
                prompt = ChatPromptTemplate.from_messages([("system", system_text), ("human", user_text)])
                messages = prompt.format_messages()
            except Exception:
                messages = []
        return {
            "system_prompt": system_text,
            "user_prompt": user_text,
            "prompt_text": prompt_text,
            "messages": messages,
        }

    def _build_report_metrics(
        self,
        *,
        latest: dict[str, Any],
        averages: dict[str, Any],
        ranges: dict[str, Any],
        trend: dict[str, Any],
    ) -> dict[str, dict[str, object]]:
        metric_map = {
            "heart_rate": "heart_rate",
            "temperature": "temperature",
            "blood_oxygen": "blood_oxygen",
            "health_score": "health_score",
        }
        metrics: dict[str, dict[str, object]] = {}
        for public_key, source_key in metric_map.items():
            range_row = ranges.get(source_key, {})
            trend_row = trend.get(source_key, {})
            if not isinstance(range_row, dict):
                range_row = {}
            if not isinstance(trend_row, dict):
                trend_row = {}
            metrics[public_key] = {
                "latest": latest.get(source_key),
                "average": averages.get(source_key),
                "min": range_row.get("min"),
                "max": range_row.get("max"),
                "trend": trend_row.get("label"),
            }
        return metrics

    def _extract_report_anomaly_payload(self, model_signals: dict[str, Any]) -> dict[str, Any]:
        anomaly_signal = model_signals.get("anomaly_explain", {})
        if not isinstance(anomaly_signal, dict):
            return {}
        payload = anomaly_signal.get("payload", {})
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _unique_texts(items: list[object], *, limit: int) -> list[str]:
        seen: set[str] = set()
        normalized: list[str] = []
        for item in items:
            text = str(item).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            normalized.append(text)
            if len(normalized) >= limit:
                break
        return normalized

    def _fallback_report_summary_with_model_signals(
        self,
        analysis_payload: dict[str, Any],
        *,
        model_signals: dict[str, Any],
        health_model_evidence: dict[str, Any],
    ) -> str:
        del model_signals
        risk_level = self._risk_label(str(health_model_evidence.get("risk_level") or analysis_payload.get("risk_level", "unknown")))
        latest = analysis_payload.get("latest", {}) if isinstance(analysis_payload, dict) else {}
        if not isinstance(latest, dict):
            latest = {}

        summary_inputs = list(health_model_evidence.get("summary_inputs", []))
        if summary_inputs:
            return " ".join(str(item) for item in summary_inputs if str(item).strip()).strip()
        key_evidence = list(health_model_evidence.get("key_evidence", []))
        transformer_line = next((item for item in key_evidence if "时序模型" in item), "")
        recommendations = list(health_model_evidence.get("recommendations", []))
        if not recommendations and isinstance(analysis_payload, dict):
            recommendations = list(analysis_payload.get("recommendations", []))

        summary_parts = [
            f"本时段健康报告结论：综合风险等级为{risk_level}。",
            (
                f"关键指标显示血氧 {latest.get('blood_oxygen', '--')}%，"
                f"体温 {latest.get('temperature', '--')}℃，"
                f"健康评分 {latest.get('health_score', '--')}。"
            ),
            *summary_inputs[:2],
            transformer_line,
            key_evidence[0] if key_evidence else "",
            f"建议动作：{'；'.join(str(item) for item in recommendations[:2])}" if recommendations else "建议继续结合后续监测与线下观察综合判断。",
        ]
        return " ".join(part for part in summary_parts if part).strip()

    def _fallback_answer(self, analysis_payload: dict[str, Any], scope: str) -> str:
        if scope == "community":
            device_count = int(analysis_payload.get("device_count", 0))
            distribution = analysis_payload.get("risk_distribution", {})
            priority_devices = analysis_payload.get("priority_devices", [])
            recommendations = analysis_payload.get("recommendations", [])
            focus = "、".join(
                str(item.get("device_mac"))
                for item in priority_devices[:3]
                if isinstance(item, dict) and item.get("device_mac")
            )
            return (
                f"本次社区汇总覆盖 {device_count} 台设备，"
                f"其中高风险 {distribution.get('high', 0)} 台、中风险 {distribution.get('medium', 0)} 台、低风险 {distribution.get('low', 0)} 台。"
                f"优先关注：{focus or '当前暂无明确重点对象'}。"
                f"建议：{'；'.join(str(item) for item in recommendations[:3]) or '继续保持常规巡检。'}"
            )

        latest = analysis_payload.get("latest", {})
        risk_level = self._risk_label(str(analysis_payload.get("risk_level", "unknown")))
        window = analysis_payload.get("window", {})
        notable_events = analysis_payload.get("notable_events", [])
        recommendations = analysis_payload.get("recommendations", [])
        return (
            f"当前综合风险等级为{risk_level}。"
            f"最近监测窗口约 {window.get('duration_minutes', 0)} 分钟，"
            f"最新指标为心率 {latest.get('heart_rate', '--')} bpm、"
            f"血氧 {latest.get('blood_oxygen', '--')}%、"
            f"血压 {latest.get('blood_pressure', '--')}。"
            f"重点情况：{notable_events[0] if notable_events else '暂无明显异常事件。'}"
            f"建议：{'；'.join(str(item) for item in recommendations[:3]) or '继续监测。'}"
        )

    @staticmethod
    def _risk_label(level: str) -> str:
        return {
            "low": "低",
            "medium": "中",
            "high": "高",
            "unknown": "未知",
        }.get(level, level)

    @staticmethod
    def _extract_message_text(message: Any) -> str | None:
        content = getattr(message, "content", None)
        if isinstance(content, str):
            value = content.strip()
            return value or None
        if isinstance(content, list):
            parts: list[str] = []
            for row in content:
                if isinstance(row, str) and row.strip():
                    parts.append(row.strip())
                elif isinstance(row, dict):
                    text = row.get("text") or row.get("content")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
            if parts:
                return "\n".join(parts)
        if isinstance(message, str):
            value = message.strip()
            return value or None
        return None

    @classmethod
    def _extract_openai_compatible_content(cls, body: dict[str, Any]) -> str | None:
        choices = body.get("choices", [])
        if not isinstance(choices, list) or not choices:
            return None
        first = choices[0]
        if not isinstance(first, dict):
            return None
        message = first.get("message", {})
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str):
                value = content.strip()
                if value:
                    return value
            if isinstance(content, list):
                parts: list[str] = []
                for item in content:
                    if isinstance(item, dict):
                        text = item.get("text")
                        if isinstance(text, str) and text.strip():
                            parts.append(text.strip())
                if parts:
                    return "\n".join(parts)
        return None
