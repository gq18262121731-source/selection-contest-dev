from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Callable, Iterator, TypedDict
from uuid import uuid4

import langchain_community.chat_models.tongyi as tongyi_chat_module
import langchain_community.llms.tongyi as tongyi_llm_module
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.chat_models.tongyi import ChatTongyi
from langgraph.graph import END, StateGraph

try:
    from langchain_ollama import ChatOllama
except ImportError:  # pragma: no cover - optional runtime dependency
    ChatOllama = None

from agent.analysis_service import HealthDataAnalysisService
from agent.langchain_rag_service import LangChainRAGService
from agent.mcp_adapter import ToolAdapter, ToolInvocation
from ai.anomaly_detector import CommunityHealthClusterer, IntelligentAnomalyScorer, RealtimeAnomalyDetector
from backend.config import Settings
from backend.models.analytics_model import AgentElderSubject, AnalysisScope, WindowKind
from backend.models.care_model import AgentDeviceHealthReport, AgentMetricReportItem, AgentReportPeriod
from backend.models.health_model import HealthSample
from backend.models.user_model import UserRole
from backend.services.alarm_service import AlarmService
from backend.services.care_service import CareService
from backend.services.device_service import DeviceService
from backend.services.health_data_repository import HealthDataRepository
from backend.services.health_score_service import HealthScoreService
from backend.services.stream_service import StreamService


class AgentState(TypedDict, total=False):
    scope: str
    role: str
    question: str
    workflow: str
    history: list[dict[str, str]]
    window: str
    history_minutes: int
    provider: str
    selected_provider: str
    selected_model: str
    include_report: bool
    subject_elder_id: str | None
    subject: dict[str, Any] | None
    target_device_macs: list[str]
    device_histories: dict[str, list[HealthSample]]
    analysis_payload: dict[str, Any]
    citations: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    attachments: list[dict[str, Any]]
    report_attachment: dict[str, Any] | None
    degraded_notes: list[str]
    answer: str
    artifact_ids: list[str]
    session_id: str


class TongyiServiceError(RuntimeError):
    """Raised when Tongyi returns a non-2xx response that LangChain wraps unsafely."""


_SAFE_TONGYI_PATCHED = False


def _safe_tongyi_check_response(resp: Any) -> Any:
    """Preserve Tongyi status/code/message instead of crashing with KeyError('request')."""

    status_code = int(resp.get("status_code", 500))
    if status_code == 200:
        return resp

    request_id = str(resp.get("request_id", "") or "")
    error_code = str(resp.get("code", "") or "")
    message = str(resp.get("message", "") or "")
    detail = " | ".join(
        part
        for part in (
            f"request_id: {request_id}" if request_id else "",
            f"status_code: {status_code}",
            f"code: {error_code}" if error_code else "",
            f"message: {message}" if message else "",
        )
        if part
    )
    if status_code in {400, 401}:
        raise ValueError(detail)
    raise TongyiServiceError(detail)


def _ensure_safe_tongyi_patch() -> None:
    global _SAFE_TONGYI_PATCHED
    if _SAFE_TONGYI_PATCHED:
        return
    tongyi_llm_module.check_response = _safe_tongyi_check_response
    tongyi_chat_module.check_response = _safe_tongyi_check_response
    _SAFE_TONGYI_PATCHED = True


class HealthAgentService:
    """Community-focused LangGraph runtime with Tongyi/Ollama selection and real analysis tools."""

    def __init__(
        self,
        settings: Settings,
        rag_service: LangChainRAGService,
        analysis_service: HealthDataAnalysisService,
        *,
        tool_adapter: ToolAdapter,
        device_service: DeviceService,
        care_service: CareService,
        repository: HealthDataRepository,
        stream_service: StreamService,
        health_score_service: HealthScoreService,
        alarm_service: AlarmService,
        intelligent_scorer: IntelligentAnomalyScorer,
        community_clusterer: CommunityHealthClusterer,
        demo_subject_provider: Callable[[], list[AgentElderSubject]],
        demo_status_provider: Callable[[], dict[str, Any]],
    ) -> None:
        self._settings = settings
        self._rag = rag_service
        self._analysis = analysis_service
        self._tool_adapter = tool_adapter
        self._device_service = device_service
        self._care_service = care_service
        self._repository = repository
        self._stream = stream_service
        self._health_score_service = health_score_service
        self._alarm_service = alarm_service
        self._intelligent_scorer = intelligent_scorer
        self._community_clusterer = community_clusterer
        self._demo_subject_provider = demo_subject_provider
        self._demo_status_provider = demo_status_provider
        self._graph = self._build_graph()

    def analyze(
        self,
        *,
        role: UserRole,
        question: str,
        samples: list[HealthSample],
        mode: str = "qwen",
    ) -> dict[str, object]:
        return self.analyze_device(role=role, question=question, samples=samples, mode=mode)

    def analyze_device(
        self,
        *,
        role: UserRole,
        question: str,
        samples: list[HealthSample],
        mode: str = "qwen",
    ) -> dict[str, object]:
        ordered = sorted(samples, key=lambda item: item.timestamp)
        if not ordered:
            return {"answer": "当前设备还没有可用样本，暂时无法生成分析。", "references": [], "analysis": {}}
        analysis = self._analyze_device_sequence(ordered[-1].device_mac, ordered)
        prompt_state: AgentState = {
            "scope": "elder",
            "role": role.value,
            "question": question,
            "workflow": "device_focus",
            "history": [],
            "window": WindowKind.DAY.value,
            "history_minutes": 24 * 60,
            "provider": self._normalize_provider(mode),
            "selected_provider": self._normalize_provider(mode),
            "selected_model": self._resolve_model_name(self._normalize_provider(mode)),
            "analysis_payload": {
                "scope": AnalysisScope.ELDER.value,
                "device_analysis": analysis,
                "key_findings": analysis.get("key_findings", []),
                "recommendations": analysis.get("recommendations", []),
            },
            "citations": self._rag.retrieve(question, top_k=self._settings.rag_top_k),
            "tool_results": [],
            "attachments": self._build_device_attachments(ordered[-1].device_mac, analysis, ordered),
            "report_attachment": None,
            "degraded_notes": [],
            "artifact_ids": [],
        }
        answer = self._generate_answer(prompt_state)
        return {
            "answer": answer,
            "references": [item["source_path"] for item in prompt_state["citations"]],
            "analysis": prompt_state["analysis_payload"],
            "attachments": prompt_state["attachments"],
            "citations": prompt_state["citations"],
            "artifact_ids": [],
            "scope": "device",
            "window": WindowKind.DAY.value,
            "subject": {"device_mac": ordered[-1].device_mac},
        }

    def stream_analyze_device(
        self,
        *,
        role: UserRole,
        question: str,
        samples: list[HealthSample],
        mode: str = "qwen",
    ) -> Iterator[dict[str, object]]:
        """Stream device analysis – yields NDJSON events including answer.delta chunks."""
        import logging
        logger = logging.getLogger(__name__)
        
        ordered = sorted(samples, key=lambda item: item.timestamp)
        session_id = str(uuid4())
        
        logger.info(f"[stream_analyze_device] session_id={session_id}, question={question[:100]}, samples_count={len(ordered)}, mode={mode}")

        if not ordered:
            yield {"type": "answer.delta", "delta": "当前设备还没有可用样本，暂时无法生成分析。", "session_id": session_id}
            yield {"type": "answer.completed", "answer": "当前设备还没有可用样本，暂时无法生成分析。", "session_id": session_id}
            return

        analysis = self._analyze_device_sequence(ordered[-1].device_mac, ordered)
        prompt_state: AgentState = {
            "scope": "elder",
            "role": role.value,
            "question": question,
            "workflow": "device_focus",
            "history": [],
            "window": WindowKind.DAY.value,
            "history_minutes": 24 * 60,
            "provider": self._normalize_provider(mode),
            "selected_provider": self._normalize_provider(mode),
            "selected_model": self._resolve_model_name(self._normalize_provider(mode)),
            "analysis_payload": {
                "scope": AnalysisScope.ELDER.value,
                "device_analysis": analysis,
                "key_findings": analysis.get("key_findings", []),
                "recommendations": analysis.get("recommendations", []),
            },
            "citations": self._rag.retrieve(question, top_k=self._settings.rag_top_k),
            "tool_results": [],
            "attachments": self._build_device_attachments(ordered[-1].device_mac, analysis, ordered),
            "report_attachment": None,
            "degraded_notes": [],
            "artifact_ids": [],
            "session_id": session_id,
        }

        yield {
            "type": "session.started",
            "session_id": session_id,
            "scope": "elder",
            "selected_model": prompt_state["selected_model"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        provider_name = prompt_state.get("selected_provider", "qwen") or "qwen"
        if provider_name == "auto":
            provider_name = "qwen"

        if provider_name == "qwen" and not self._settings.tongyi_chat_configured:
            answer = self._qwen_unavailable_message()
            yield {
                "type": "answer.delta",
                "session_id": session_id,
                "delta": answer,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            yield {
                "type": "answer.completed",
                "session_id": session_id,
                "answer": answer,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            return

        answer = ""
        try:
            llm = self._build_llm(provider_name, streaming=True)
            if llm is None:
                raise RuntimeError("llm_not_available")
            prompt_messages = self._build_prompt(prompt_state)
            logger.info(f"[stream_analyze_device] session_id={session_id}, prompt_ready, starting LLM stream, provider={provider_name}")
            for chunk in llm.stream(prompt_messages):
                content = getattr(chunk, "content", "")
                if content:
                    answer += content
                    yield {
                        "type": "answer.delta",
                        "session_id": session_id,
                        "delta": content,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error("[stream_analyze_device] LLM failed: %s", exc)
            degraded = list(prompt_state.get("degraded_notes", []))
            degraded.append(f"llm_fallback_to_deterministic_summary:{type(exc).__name__}:{str(exc)[:120]}")
            prompt_state["degraded_notes"] = self._dedupe_strings(degraded)
            answer = self._fallback_answer(prompt_state, exc)
            yield {
                "type": "answer.delta",
                "session_id": session_id,
                "delta": answer,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        yield {
            "type": "answer.completed",
            "session_id": session_id,
            "answer": answer,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def analyze_community(
        self,
        *,
        role: UserRole,
        question: str,
        device_samples: dict[str, list[HealthSample]] | None = None,
        mode: str = "qwen",
        history_minutes: int = 1440,
        workflow: str = "free_chat",
        focus_device_mac: str | None = None,
        history: list[dict[str, str]] | None = None,
        scope: str = AnalysisScope.COMMUNITY.value,
        subject_elder_id: str | None = None,
        window: str = WindowKind.DAY.value,
        provider: str | None = None,
        include_report: bool = False,
        per_device_limit: int = 240,
        device_macs: list[str] | None = None,
    ) -> dict[str, object]:
        del focus_device_mac
        del per_device_limit
        state = self._invoke(
            {
                "scope": scope,
                "role": role.value,
                "question": question,
                "workflow": workflow,
                "history": history or [],
                "window": window,
                "history_minutes": history_minutes,
                "provider": self._normalize_provider(provider or mode),
                "selected_provider": self._normalize_provider(provider or mode),
                "selected_model": self._resolve_model_name(self._normalize_provider(provider or mode)),
                "include_report": include_report or workflow in {"community_report", "elder_report", "report_generation"},
                "subject_elder_id": subject_elder_id,
                "target_device_macs": [item.upper() for item in (device_macs or []) if item],
                "device_histories": device_samples or {},
                "citations": [],
                "artifact_ids": [],
                "session_id": f"sync-{uuid4()}",
            }
        )
        return self._format_result(state)

    def stream_analyze_community(
        self,
        *,
        role: UserRole,
        question: str,
        device_samples: dict[str, list[HealthSample]] | None = None,
        mode: str = "qwen",
        history_minutes: int = 1440,
        workflow: str = "free_chat",
        focus_device_mac: str | None = None,
        history: list[dict[str, str]] | None = None,
        scope: str = AnalysisScope.COMMUNITY.value,
        subject_elder_id: str | None = None,
        window: str = WindowKind.DAY.value,
        provider: str | None = None,
        include_report: bool = False,
        per_device_limit: int = 240,
        device_macs: list[str] | None = None,
    ) -> Iterator[dict[str, object]]:
        del focus_device_mac
        del per_device_limit
        session_id = str(uuid4())
        state: AgentState = {
            "scope": scope,
            "role": role.value,
            "question": question,
            "workflow": workflow,
            "history": history or [],
            "window": window,
            "history_minutes": history_minutes,
            "provider": self._normalize_provider(provider or mode),
            "selected_provider": self._normalize_provider(provider or mode),
            "selected_model": self._resolve_model_name(self._normalize_provider(provider or mode)),
            "include_report": include_report or workflow in {"community_report", "elder_report", "report_generation"},
            "subject_elder_id": subject_elder_id,
            "target_device_macs": [item.upper() for item in (device_macs or []) if item],
            "device_histories": device_samples or {},
            "citations": [],
            "artifact_ids": [],
            "session_id": session_id,
        }
        yield {
            "type": "session.started",
            "session_id": session_id,
            "scope": scope,
            "selected_model": state["selected_model"],
            "degraded_notes": [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        for stage_name, handler in self._stream_steps():
            stage_started_at = datetime.now(timezone.utc)
            yield self._stage_event(stage_name, "running", state=state)
            planned_calls: list[ToolInvocation] = []
            if stage_name == "tool_loop":
                planned_calls = self._build_tool_calls(state)
                for call in planned_calls:
                    yield self._tool_started_event(call)
                state = self._tool_loop_node(state, calls=planned_calls)
            else:
                state = handler(state)
            for note in self._stage_notes(stage_name, state):
                yield {
                    "type": "trace.note",
                    "stage": stage_name,
                    "note": note,
                    "level": "info",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            if stage_name == "tool_loop":
                for item in state.get("tool_results", []):
                    yield from self._stream_tool_events(item)
            if stage_name == "synthesis":
                answer = state.get("answer", "")
                for index in range(0, len(answer), 32):
                    yield {
                        "type": "answer.delta",
                        "session_id": session_id,
                        "delta": answer[index : index + 32],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
            elapsed_ms = int((datetime.now(timezone.utc) - stage_started_at).total_seconds() * 1000)
            yield self._stage_event(stage_name, "completed", state=state, elapsed_ms=elapsed_ms)
        yield {
            "type": "answer.completed",
            "session_id": session_id,
            "answer": state.get("answer", ""),
            "references": [item["source_path"] for item in state.get("citations", [])],
            "analysis": state.get("analysis_payload", {}),
            "attachments": state.get("attachments", []),
            "citations": state.get("citations", []),
            "artifact_ids": state.get("artifact_ids", []),
            "scope": state.get("scope", AnalysisScope.COMMUNITY.value),
            "window": state.get("window", WindowKind.DAY.value),
            "subject": state.get("subject"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        yield {
            "type": "session.completed",
            "session_id": session_id,
            "selected_model": state.get("selected_model", ""),
            "degraded_notes": state.get("degraded_notes", []),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def capability_report(self) -> dict[str, object]:
        return {
            "runtime": "langgraph_qwen_community_agent",
            "default_provider": "qwen",
            "selected_provider": "qwen",
            "providers": {
                "qwen": {
                    "configured": self._settings.qwen_llm_configured,
                    "chat_configured": self._settings.tongyi_chat_configured,
                    "chat_model": self._settings.tongyi_chat_model,
                    "embedding_model": self._settings.tongyi_embedding_model if self._settings.tongyi_embedding_configured else "",
                    "rerank_model": self._settings.tongyi_rerank_model if self._settings.tongyi_rerank_configured else "",
                    "missing_config": self._settings.qwen_missing_config_fields,
                },
                "tongyi": {
                    "chat_configured": self._settings.tongyi_chat_configured,
                    "chat_model": self._settings.tongyi_chat_model,
                    "embedding_model": self._settings.tongyi_embedding_model if self._settings.tongyi_embedding_configured else "",
                    "rerank_model": self._settings.tongyi_rerank_model if self._settings.tongyi_rerank_configured else "",
                },
                "ollama": {
                    "configured": bool(ChatOllama and self._settings.ollama_base_url and self._settings.ollama_model),
                    "base_url": self._settings.ollama_base_url,
                    "model": self._settings.ollama_model,
                },
            },
            "retrieval": self._rag.stats(),
            "analysis_tools": [
                "query_window_dataset",
                "analyze_health_window",
                "generate_analysis_report",
                "synthesize_recommendations",
            ],
            "tool_specs": [asdict(item) for item in self._tool_adapter.list_tools()],
            "extensions": {
                "mcp_connected": False,
                "demo_data": self._demo_status_provider(),
            },
        }

    def _build_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node("scope_resolve", self._scope_resolve_node)
        graph.add_node("window_resolve", self._window_resolve_node)
        graph.add_node("data_load", self._data_load_node)
        graph.add_node("model_analysis", self._model_analysis_node)
        graph.add_node("rag_retrieve", self._rag_retrieve_node)
        graph.add_node("tool_loop", self._tool_loop_node)
        graph.add_node("synthesis", self._synthesis_node)
        graph.add_node("artifact_render", self._artifact_render_node)
        graph.add_node("session_persist", self._session_persist_node)
        graph.set_entry_point("scope_resolve")
        graph.add_edge("scope_resolve", "window_resolve")
        graph.add_edge("window_resolve", "data_load")
        graph.add_edge("data_load", "model_analysis")
        graph.add_edge("model_analysis", "rag_retrieve")
        graph.add_edge("rag_retrieve", "tool_loop")
        graph.add_edge("tool_loop", "synthesis")
        graph.add_edge("synthesis", "artifact_render")
        graph.add_edge("artifact_render", "session_persist")
        graph.add_edge("session_persist", END)
        return graph.compile()

    def _stream_steps(self) -> list[tuple[str, Callable[[AgentState], AgentState]]]:
        return [
            ("scope_resolve", self._scope_resolve_node),
            ("window_resolve", self._window_resolve_node),
            ("data_load", self._data_load_node),
            ("model_analysis", self._model_analysis_node),
            ("rag_retrieve", self._rag_retrieve_node),
            ("tool_loop", self._tool_loop_node),
            ("synthesis", self._synthesis_node),
            ("artifact_render", self._artifact_render_node),
            ("session_persist", self._session_persist_node),
        ]

    def _invoke(self, initial_state: AgentState) -> AgentState:
        return self._graph.invoke(initial_state)

    def generate_device_health_report(
        self,
        *,
        role: UserRole,
        device_mac: str,
        start_at: datetime,
        end_at: datetime,
        samples: list[HealthSample],
        mode: str = "qwen",
    ) -> dict[str, object]:
        ordered = sorted(samples, key=lambda item: item.timestamp)
        analysis = self._analyze_device_sequence(device_mac, ordered) if ordered else {}
        question = f"请生成 {device_mac} 在 {start_at.isoformat()} 到 {end_at.isoformat()} 的健康报告。"
        citations = self._rag.retrieve(question, top_k=self._settings.rag_top_k)
        report_attachment = self._build_report_attachment(
            scope=AnalysisScope.ELDER.value,
            subject={"label": device_mac.upper()},
            analysis_payload={"device_analysis": analysis, "key_findings": analysis.get("key_findings", []), "recommendations": analysis.get("recommendations", [])},
            citations=citations,
            window_label=self._window_label(WindowKind.DAY.value),
        )
        report_sections = report_attachment["render_payload"]["sections"]
        metrics = {}
        metric_snapshot = analysis.get("metric_snapshot", {})
        for key, payload in metric_snapshot.items():
            metrics[key] = AgentMetricReportItem(**payload)
        return AgentDeviceHealthReport(
            device_mac=device_mac.upper(),
            subject_name=device_mac.upper(),
            device_name=self._device_service.get_device(device_mac).device_name if self._device_service.get_device(device_mac) else None,
            generated_at=datetime.now(timezone.utc).isoformat(),
            period=AgentReportPeriod(
                start_at=start_at.isoformat(),
                end_at=end_at.isoformat(),
                duration_minutes=max(1, int((end_at - start_at).total_seconds() / 60)),
                sample_count=len(ordered),
            ),
            summary=report_sections[0]["content"] if report_sections else "暂无摘要。",
            risk_level=analysis.get("risk_level", "unknown"),
            risk_flags=list(analysis.get("abnormal_tags", [])),
            key_findings=list(analysis.get("key_findings", [])),
            recommendations=list(analysis.get("recommendations", [])),
            metrics=metrics,
            references=[item["source_path"] for item in citations],
        ).model_dump(mode="json")

    def _scope_resolve_node(self, state: AgentState) -> AgentState:
        scope = AnalysisScope.ELDER.value if state.get("scope") == AnalysisScope.ELDER.value else AnalysisScope.COMMUNITY.value
        subject = self._resolve_subject(state.get("subject_elder_id"))
        return {**state, "scope": scope, "subject": subject}

    def _window_resolve_node(self, state: AgentState) -> AgentState:
        window = WindowKind.WEEK.value if state.get("window") == WindowKind.WEEK.value else WindowKind.DAY.value
        return {
            **state,
            "window": window,
            "history_minutes": 7 * 24 * 60 if window == WindowKind.WEEK.value else 24 * 60,
        }

    def _data_load_node(self, state: AgentState) -> AgentState:
        subject = state.get("subject") or {}
        provided = state.get("device_histories") or {}
        if state["scope"] == AnalysisScope.ELDER.value:
            target_device_macs = [item.upper() for item in subject.get("device_macs", []) if item]
        else:
            target_device_macs = state.get("target_device_macs") or sorted(
                [device.mac_address for device in self._device_service.list_devices()]
            )
        if not target_device_macs and provided:
            target_device_macs = sorted(provided.keys())
        device_histories: dict[str, list[HealthSample]] = {}
        for device_mac in target_device_macs:
            samples = list(provided.get(device_mac, []))
            if not samples:
                samples = self._load_history(device_mac, minutes=state["history_minutes"])
            if samples:
                device_histories[device_mac] = samples
        return {**state, "target_device_macs": target_device_macs, "device_histories": device_histories}

    def _model_analysis_node(self, state: AgentState) -> AgentState:
        if state["scope"] == AnalysisScope.ELDER.value:
            analysis_payload = self._build_elder_analysis(state)
        else:
            analysis_payload = self._build_community_analysis(state)
        return {**state, "analysis_payload": analysis_payload}

    def _rag_retrieve_node(self, state: AgentState) -> AgentState:
        citations = self._rag.retrieve(self._build_retrieval_query(state), top_k=self._settings.rag_top_k, allow_rerank=True)
        degraded_notes = list(state.get("degraded_notes", []))
        if not citations:
            degraded_notes.append("knowledge_retrieval_empty")
        return {**state, "citations": citations, "degraded_notes": self._dedupe_strings(degraded_notes)}

    def _tool_loop_node(self, state: AgentState, calls: list[ToolInvocation] | None = None) -> AgentState:
        calls = calls or self._build_tool_calls(state)
        if not calls:
            return {**state, "tool_results": []}
        results = self._tool_adapter.invoke_many(calls)
        tool_results: list[dict[str, Any]] = []
        attachments = list(state.get("attachments", []))
        degraded_notes = list(state.get("degraded_notes", []))
        for call, result in zip(calls, results, strict=False):
            data = result.data if isinstance(result.data, dict) else {}
            payload_attachments = self._attachments_from_tool_result(
                call.name,
                data,
                attachment_id=call.request_id if call.name == "generate_analysis_report" else None,
            )
            attachments.extend(payload_attachments)
            degraded_notes.extend(item for item in data.get("degraded_notes", []) if isinstance(item, str))
            tool_results.append(
                {
                    "request_id": call.request_id or str(uuid4()),
                    "tool_name": call.name,
                    "source": result.source,
                    "status": result.status,
                    "success": result.success,
                    "title": data.get("title") or self._tool_title(call.name),
                    "tool_kind": data.get("tool_kind") or self._tool_kind(call.name),
                    "summary": data.get("summary") or self._tool_summary(call.name, data),
                    "input_preview": data.get("input_preview") or self._tool_input_preview(call.name, call.payload),
                    "output_preview": data.get("output_preview") or self._tool_output_preview(call.name, data),
                    "child_tools": self._extract_child_tools(data),
                    "data": data,
                    "attachments": payload_attachments,
                }
            )
        return {
            **state,
            "tool_results": tool_results,
            "attachments": attachments,
            "degraded_notes": self._dedupe_strings(degraded_notes),
            "analysis_payload": self._merge_tool_results_into_payload(state.get("analysis_payload", {}), tool_results),
        }

    def _synthesis_node(self, state: AgentState) -> AgentState:
        return {**state, "answer": self._generate_answer(state)}

    def _merge_tool_results_into_payload(self, analysis_payload: dict[str, Any], tool_results: list[dict[str, Any]]) -> dict[str, Any]:
        """Merge tool execution results back into analysis_payload so LLM can see real data."""
        merged = dict(analysis_payload)
        for result in tool_results:
            if not result.get("success"):
                continue
            data = result.get("data", {})
            tool_name = result.get("tool_name", "")
            if tool_name == "analyze_health_window":
                analysis = data.get("analysis", {})
                if analysis:
                    merged.setdefault("key_findings", [])
                    merged.setdefault("recommendations", [])
                    if analysis.get("risk_level"):
                        merged["risk_level"] = analysis["risk_level"]
                    if analysis.get("health_score") is not None:
                        merged["health_score"] = analysis["health_score"]
                    if analysis.get("high_risk_entities"):
                        merged["high_risk_entities"] = analysis["high_risk_entities"]
                    if analysis.get("alert_count") is not None:
                        merged["alert_count"] = analysis["alert_count"]
                    if analysis.get("anomaly_probability") is not None:
                        merged["anomaly_probability"] = analysis["anomaly_probability"]
                    if analysis.get("abnormal_tags"):
                        merged.setdefault("abnormal_tags", []).extend(
                            t for t in analysis["abnormal_tags"] if t not in merged.get("abnormal_tags", [])
                        )
                    # Merge device_analysis if scope is elder
                    if analysis.get("device_mac"):
                        device_analysis = merged.get("device_analysis", {})
                        device_analysis.update({k: v for k, v in analysis.items() if v is not None})
                        merged["device_analysis"] = device_analysis
            elif tool_name == "query_window_dataset":
                dataset = data.get("dataset", {})
                if dataset.get("sample_count"):
                    merged["sample_count"] = dataset["sample_count"]
                if dataset.get("device_count"):
                    merged["device_count"] = dataset["device_count"]
                if dataset.get("latest_points"):
                    merged["latest_points"] = dataset["latest_points"]
            elif tool_name == "synthesize_recommendations":
                recs = data.get("recommendations", [])
                if recs:
                    existing = set(merged.get("recommendations", []))
                    merged["recommendations"] = list(merged.get("recommendations", [])) + [
                        r for r in recs if r not in existing
                    ]
                if data.get("web_results"):
                    merged["web_results"] = data["web_results"]
                    merged.setdefault("key_findings", []).append(
                        f"联网搜索补充了 {len(data['web_results'])} 条参考资料"
                    )
            elif tool_name == "generate_analysis_report":
                report = data.get("report", {})
                if report.get("sections"):
                    # Extract findings and recommendations from LLM-generated sections
                    for section in report["sections"]:
                        title = section.get("title", "")
                        content = section.get("content", "").strip()
                        if not content or content in {"暂无关键发现。", "暂无重点风险项。"}:
                            continue
                        if title == "关键发现":
                            items = [line.lstrip("•- ").strip() for line in content.splitlines() if line.strip()]
                            existing = set(merged.get("key_findings", []))
                            merged.setdefault("key_findings", []).extend(i for i in items if i and i not in existing)
                        elif title in {"处置建议", "风险对象 / 风险点"}:
                            items = [line.lstrip("•- ").strip() for line in content.splitlines() if line.strip()]
                            existing = set(merged.get("recommendations", []))
                            merged.setdefault("recommendations", []).extend(i for i in items if i and i not in existing)
        return merged

    def _artifact_render_node(self, state: AgentState) -> AgentState:
        attachments = list(state.get("attachments", []))
        analysis_payload = state.get("analysis_payload", {})
        if state["scope"] == AnalysisScope.ELDER.value:
            device_histories = state.get("device_histories", {})
            if device_histories:
                # For elder scope, the "main" device should match the one selected by
                # _build_elder_analysis (highest risk). Using dict iteration order here
                # causes chart data to come from a different device.
                primary_mac = str((analysis_payload.get("device_analysis") or {}).get("device_mac") or next(iter(device_histories.keys())))
                attachments.extend(self._build_device_attachments(primary_mac, analysis_payload.get("device_analysis", {}), device_histories[primary_mac]))
        else:
            attachments.extend(self._build_community_attachments(analysis_payload))

        report_attachment = None
        if state.get("include_report"):
            report_attachment = next(
                (
                    item
                    for item in attachments
                    if item.get("render_type") == "report_document"
                    and item.get("source_tool") in {"generate_analysis_report", "report_generation"}
                ),
                None,
            )
            if report_attachment is None:
                report_attachment = self._build_report_attachment(
                    scope=state["scope"],
                    subject=state.get("subject"),
                    analysis_payload=analysis_payload,
                    citations=state.get("citations", []),
                    window_label=self._window_label(state["window"]),
                )
                attachments.append(report_attachment)
        return {**state, "attachments": self._dedupe_attachments(attachments), "report_attachment": report_attachment}

    def _session_persist_node(self, state: AgentState) -> AgentState:
        return state

    def _resolve_subject(self, elder_id: str | None) -> dict[str, Any] | None:
        if not elder_id:
            return None
        directory = self._care_service.get_directory()
        elder = next((item for item in directory.elders if item.id == elder_id), None)
        if elder is not None:
            return {
                "id": elder.id,
                "label": elder.name,
                "apartment": elder.apartment,
                "device_macs": list(getattr(elder, "device_macs", [])) or ([elder.device_mac] if elder.device_mac else []),
                "is_demo_subject": False,
            }
        demo_subject = next((item for item in self._demo_subject_provider() if item.elder_id == elder_id), None)
        if demo_subject is None:
            return None
        return {
            "id": demo_subject.elder_id,
            "label": demo_subject.elder_name,
            "apartment": demo_subject.apartment,
            "device_macs": list(demo_subject.device_macs),
            "is_demo_subject": demo_subject.is_demo_subject,
        }

    def _load_history(self, device_mac: str, *, minutes: int) -> list[HealthSample]:
        end_at = datetime.now(timezone.utc)
        start_at = end_at - timedelta(minutes=minutes)
        samples = self._repository.list_samples(
            device_mac=device_mac,
            start_at=start_at,
            end_at=end_at,
            limit=max(180, int(minutes / 3)),
        )
        if samples:
            return samples
        return self._stream.recent_in_window(device_mac, minutes=minutes, limit=max(120, int(minutes / 5)))

    def _build_elder_analysis(self, state: AgentState) -> dict[str, Any]:
        subject = state.get("subject") or {"label": "未命名对象", "device_macs": []}
        analyses: list[dict[str, Any]] = []
        for device_mac, samples in state.get("device_histories", {}).items():
            analyses.append(self._analyze_device_sequence(device_mac, samples))
        if not analyses:
            return {
                "scope": AnalysisScope.ELDER.value,
                "subject": subject,
                "risk_level": "unknown",
                "key_findings": ["当前时间窗口内还没有可用样本。"],
                "recommendations": ["请先确认设备是否有实时上报或历史样本。"],
                "device_analysis": {},
                "device_analyses": [],
            }
        primary = max(analyses, key=lambda item: self._risk_weight(item["risk_level"]))
        return {
            "scope": AnalysisScope.ELDER.value,
            "subject": subject,
            "risk_level": primary["risk_level"],
            "key_findings": self._dedupe_strings([finding for item in analyses for finding in item["key_findings"]])[:6],
            "recommendations": self._dedupe_strings([item for record in analyses for item in record["recommendations"]])[:5],
            "device_analysis": primary,
            "device_analyses": analyses,
        }

    def _build_community_analysis(self, state: AgentState) -> dict[str, Any]:
        device_analyses = [
            self._analyze_device_sequence(device_mac, samples)
            for device_mac, samples in state.get("device_histories", {}).items()
            if samples
        ]
        latest_samples = [samples[-1] for samples in state.get("device_histories", {}).values() if samples]
        cluster_summary = self._community_clusterer.summarize(latest_samples, state.get("device_histories", {}))
        aggregated = self._analysis.summarize_community_history(state.get("device_histories", {}))
        high_risk = sorted(
            device_analyses,
            key=lambda item: (self._risk_weight(item["risk_level"]), -(item["latest_health_score"] or 999)),
            reverse=True,
        )
        return {
            "scope": AnalysisScope.COMMUNITY.value,
            "window": state["window"],
            "risk_distribution": dict(Counter(item["risk_level"] for item in device_analyses)),
            "cluster_summary": {
                "clusters": cluster_summary.clusters,
                "trend": cluster_summary.trend,
                "risk_heatmap": cluster_summary.risk_heatmap,
            },
            "high_risk_entities": [
                {
                    "device_mac": item["device_mac"],
                    "subject_label": item["subject_label"],
                    "risk_level": item["risk_level"],
                    "latest_health_score": item["latest_health_score"],
                    "abnormal_tags": item["abnormal_tags"],
                    "active_alarm_count": len(item["alarm_messages"]),
                }
                for item in high_risk[:8]
            ],
            "community_summary": aggregated,
            "device_analyses": device_analyses,
            "key_findings": self._build_community_findings(device_analyses, cluster_summary, aggregated),
            "recommendations": self._build_community_recommendations(device_analyses, cluster_summary),
        }

    def _analyze_device_sequence(self, device_mac: str, samples: list[HealthSample]) -> dict[str, Any]:
        ordered = sorted(samples, key=lambda item: item.timestamp)
        latest = ordered[-1]
        summary = self._analysis.summarize_device(ordered)
        valid_window_samples = [item for item in ordered[-36:] if self._sample_within_supported_range(item)]
        try:
            if not valid_window_samples:
                raise ValueError("no_valid_window_samples")
            score_response = self._health_score_service.evaluate_window(
                window_points=[self._sample_to_window_point(item) for item in valid_window_samples],
                elderly_id="COMMUNITY_AGENT",
                device_id=device_mac,
            )
        except Exception:
            fallback_score = float(latest.health_score) if latest.health_score is not None else 72.0
            fallback_risk = self._analysis.sample_risk_level(latest)
            score_response = SimpleNamespace(
                health_score=fallback_score,
                risk_level=fallback_risk,
                rule_health_score=fallback_score,
                model_health_score=None,
                abnormal_tags=list(self._analysis.sample_risk_flags(latest)),
                trigger_reasons=["fallback_to_stream_metrics"],
                recommendation_code="monitor",
                score_adjustment_reason="agent_window_fallback",
                active_events=[],
            )
        detector = RealtimeAnomalyDetector()
        realtime_alarms = []
        try:
            for sample in ordered[-12:]:
                realtime_alarms = detector.evaluate(sample)
        except Exception:
            realtime_alarms = []
        try:
            anomaly_result = self._intelligent_scorer.infer_device(device_mac, ordered, force=True)
        except Exception:
            anomaly_result = None
        alarm_messages = [alarm.message for alarm in realtime_alarms]
        if anomaly_result is not None:
            anomaly_alarm = self._intelligent_scorer.build_alarm(latest, anomaly_result)
            if anomaly_alarm is not None:
                alarm_messages.append(anomaly_alarm.message)

        return {
            "device_mac": device_mac,
            "subject_label": self._subject_label_for_device(device_mac),
            "latest_timestamp": latest.timestamp.isoformat(),
            "latest_health_score": score_response.health_score,
            "risk_level": score_response.risk_level,
            "rule_health_score": score_response.rule_health_score,
            "model_health_score": score_response.model_health_score,
            "abnormal_tags": list(score_response.abnormal_tags),
            "trigger_reasons": list(score_response.trigger_reasons),
            "recommendation_code": score_response.recommendation_code,
            "score_adjustment_reason": score_response.score_adjustment_reason,
            "active_event_count": len(score_response.active_events),
            "metric_snapshot": {
                "heart_rate": self._metric_snapshot(ordered, "heart_rate"),
                "blood_oxygen": self._metric_snapshot(ordered, "blood_oxygen"),
                "temperature": self._metric_snapshot(ordered, "temperature"),
            },
            "alarm_messages": alarm_messages,
            "analysis_summary": summary,
            "anomaly_model": {
                "probability": round(anomaly_result.probability, 4) if anomaly_result else None,
                "score": round(anomaly_result.score, 4) if anomaly_result else None,
                "drift_score": round(anomaly_result.drift_score, 4) if anomaly_result else None,
                "reconstruction_score": round(anomaly_result.reconstruction_score, 4) if anomaly_result else None,
                "reason": anomaly_result.reason if anomaly_result else "",
                "health_score": round(anomaly_result.health_score, 4) if anomaly_result and anomaly_result.health_score is not None else None,
            },
            "key_findings": self._build_device_findings(self._subject_label_for_device(device_mac), score_response, anomaly_result, alarm_messages),
            "recommendations": self._build_device_recommendations(score_response, anomaly_result, latest),
        }

    def _sample_within_supported_range(self, sample: HealthSample) -> bool:
        systolic, diastolic = sample.blood_pressure_pair
        return (
            30 <= float(sample.heart_rate) <= 220
            and 70 <= float(sample.blood_oxygen) <= 100
            and 30 <= float(sample.temperature) <= 43
            and 70 <= float(systolic) <= 240
            and 40 <= float(diastolic) <= 150
        )

    def _build_device_findings(self, subject_label: str, score_response, anomaly_result, alarm_messages: list[str]) -> list[str]:
        findings = [f"{subject_label} 当前风险等级为 {score_response.risk_level}，健康评分 {score_response.health_score:.1f}。"]
        if score_response.abnormal_tags:
            findings.append(f"主要异常标签：{'、'.join(score_response.abnormal_tags[:4])}。")
        if anomaly_result and anomaly_result.probability >= 0.55:
            findings.append(f"时序异常概率 {anomaly_result.probability:.0%}，漂移分数 {anomaly_result.drift_score:.2f}。")
        if alarm_messages:
            findings.append(f"当前需要关注的告警：{alarm_messages[0]}")
        return findings

    def _build_device_recommendations(self, score_response, anomaly_result, latest: HealthSample) -> list[str]:
        recommendations = ["继续保持连续监测，关注下一轮采样是否延续当前趋势。"]
        if score_response.risk_level in {"warning", "critical"}:
            recommendations.append("建议值守人员优先复核该对象近期趋势，并视情况安排电话或上门随访。")
        if latest.blood_oxygen < 93:
            recommendations.append("血氧偏低时应缩短复测间隔，排查体位、呼吸状态和设备佩戴质量。")
        if latest.temperature >= 37.6:
            recommendations.append("体温偏高时应结合近期血压和心率判断是否存在持续炎症或感染风险。")
        if anomaly_result and anomaly_result.probability >= 0.68:
            recommendations.append("时序模型已识别持续偏移，建议结合人工复核与告警处置闭环。")
        return self._dedupe_strings(recommendations)

    def _build_community_findings(self, device_analyses, cluster_summary, aggregated: dict[str, Any]) -> list[str]:
        high_count = sum(1 for item in device_analyses if item["risk_level"] in {"warning", "critical", "high", "danger"})
        findings = [f"当前窗口内共分析 {len(device_analyses)} 台设备，其中重点关注对象 {high_count} 台。"]
        if aggregated.get("priority_devices"):
            findings.append("群体分析已形成优先处置名单，可直接用于值守排班。")
        if cluster_summary.trend:
            attention = cluster_summary.trend.get("attention", 0)
            danger = cluster_summary.trend.get("danger", 0)
            if attention or danger:
                findings.append(
                    f"社区聚类结果显示关注级 {attention} 台，危险级 {danger} 台。"
                )
        return findings

    def _build_community_recommendations(self, device_analyses, cluster_summary) -> list[str]:
        recommendations = ["优先跟进高风险老人，再安排对持续告警和离线设备的补查。"]
        if cluster_summary.trend.get("danger", 0) >= 2:
            recommendations.append("当前危险簇对象较多，建议按楼栋或片区重新梳理巡查优先级。")
        if any(item["anomaly_model"]["probability"] and item["anomaly_model"]["probability"] >= 0.72 for item in device_analyses):
            recommendations.append("对时序异常持续偏高的对象应启用人工复核和二次测量。")
        return self._dedupe_strings(recommendations)

    def _build_tool_calls(self, state: AgentState) -> list[ToolInvocation]:
        make_id = lambda: str(uuid4())
        device_macs = [item.upper() for item in state.get("target_device_macs", []) if item]
        base_payload = {
            "scope": state["scope"],
            "subject_elder_id": state.get("subject_elder_id"),
            "subject": state.get("subject"),
            "device_macs": device_macs,
            "window": state["window"],
        }
        calls = [
            ToolInvocation(
                name="query_window_dataset",
                request_id=make_id(),
                payload={
                    **base_payload,
                    "metrics": ["heart_rate", "blood_oxygen", "blood_pressure", "temperature", "steps"],
                    "bucket": "hour" if state["window"] == WindowKind.WEEK.value else "raw",
                },
            ),
            ToolInvocation(
                name="analyze_health_window",
                request_id=make_id(),
                payload=base_payload,
            ),
        ]
        if state.get("include_report"):
            calls.append(
                ToolInvocation(
                    name="generate_analysis_report",
                    request_id=make_id(),
                    payload={
                        **base_payload,
                        "analysis_payload": state.get("analysis_payload", {}),
                        "citations": state.get("citations", []),
                    },
                )
            )
        calls.append(
            ToolInvocation(
                name="synthesize_recommendations",
                request_id=make_id(),
                payload={
                    **base_payload,
                    "question": state.get("question", ""),
                    "analysis_payload": state.get("analysis_payload", {}),
                    "citations": state.get("citations", []),
                },
            )
        )
        return calls

    def _attachments_from_tool_result(
        self,
        tool_name: str,
        data: dict[str, Any],
        *,
        attachment_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if not data:
            return []
        if tool_name == "build_chart_payloads":
            charts = list(data.get("charts", []))
            if charts:
                return [{
                    "id": f"{tool_name}-{uuid4()}",
                    "title": "趋势图表",
                    "summary": f"基于{self._window_label(data.get('window', WindowKind.DAY.value))}窗口生成。",
                    "render_type": "echarts",
                    "render_payload": {"charts": charts},
                    "source_tool": tool_name,
                }]
            return []
        if tool_name == "summarize_window_metrics":
            metrics = data.get("key_metrics", {})
            cards = [{"id": key, "label": key.replace("_", " ").title(), "value": value, "tone": "accent"} for key, value in list(metrics.items())[:6]]
            return [{
                "id": f"{tool_name}-{uuid4()}",
                "title": "窗口概览",
                "summary": "智能体用于建立社区整体态势的结构化摘要。",
                "render_type": "metric_cards",
                "render_payload": {"cards": cards},
                "source_tool": tool_name,
            }] if cards else []
        if tool_name == "query_alert_history":
            alerts = list(data.get("alerts", []))
            rows = [{
                "time": item.get("created_at", ""),
                "device": item.get("device_mac", ""),
                "level": item.get("alarm_level", ""),
                "type": item.get("alarm_type", ""),
                "message": item.get("message", ""),
            } for item in alerts[:8]]
            return [{
                "id": f"{tool_name}-{uuid4()}",
                "title": "告警摘要",
                "summary": "最近窗口内的重点告警列表。",
                "render_type": "table",
                "render_payload": {
                    "columns": [
                        {"key": "time", "label": "时间"},
                        {"key": "device", "label": "设备"},
                        {"key": "level", "label": "级别"},
                        {"key": "type", "label": "类型"},
                        {"key": "message", "label": "内容"},
                    ],
                    "rows": rows,
                },
                "source_tool": tool_name,
            }] if rows else []
        if tool_name == "generate_analysis_report":
            report = data.get("report", {})
            if isinstance(report, dict) and report.get("sections"):
                document_title = str(report.get("document_title") or data.get("title") or "结构化分析报告")
                sections = report.get("sections", [])
                return [{
                    "id": attachment_id or f"{tool_name}-{uuid4()}",
                    "title": document_title,
                    "summary": str(data.get("summary") or "当前分析窗口的结构化报告已生成。"),
                    "render_type": "report_document",
                    "render_payload": {
                        "document_title": document_title,
                        "sections": sections,
                        "markdown": self._report_markdown(document_title, sections),
                    },
                    "source_tool": tool_name,
                }]
            return []
        if tool_name in {"evaluate_window_health", "analyze_device_anomaly", "analyze_community_risk"}:
            cards = [{"id": key, "label": key.replace("_", " "), "value": value, "tone": "default"} for key, value in data.items() if isinstance(value, (str, int, float)) and key not in {"device_mac"}]
            return [{
                "id": f"{tool_name}-{uuid4()}",
                "title": "模型分析结果",
                "summary": "由评分和异常检测模型输出的结构化信号。",
                "render_type": "metric_cards",
                "render_payload": {"cards": cards[:8]},
                "source_tool": tool_name,
            }] if cards else []
        return []

    def _build_device_attachments(self, device_mac: str, analysis: dict[str, Any], samples: list[HealthSample]) -> list[dict[str, Any]]:
        if not analysis or not samples:
            return []
        _risk_cn = {"low": "低风险", "medium": "中风险", "high": "高风险", "warning": "预警", "critical": "危急", "normal": "稳定", "stable": "稳定", "attention": "关注", "danger": "高风险", "unknown": "待评估"}
        cards = [
            {"id": "risk_level", "label": "风险等级", "value": _risk_cn.get(analysis.get("risk_level", ""), analysis.get("risk_level", "--")), "tone": "danger" if analysis.get("risk_level") in {"warning", "critical", "high", "danger"} else "accent"},
            {"id": "health_score", "label": "健康评分", "value": analysis.get("latest_health_score", "--"), "tone": "accent"},
            {"id": "anomaly_probability", "label": "异常概率", "value": analysis.get("anomaly_model", {}).get("probability", "--"), "tone": "default"},
            {"id": "active_events", "label": "活动事件", "value": analysis.get("active_event_count", 0), "tone": "default"},
        ]
        # Ensure chart uses the latest N samples by timestamp.
        ordered_samples = sorted(samples, key=lambda item: item.timestamp)
        points = ordered_samples[-24:]
        chart = {
            "id": f"{device_mac}-trend",
            "title": f"{device_mac} 关键指标趋势",
            "summary": "最近窗口内的心率、血氧和体温变化。",
            "echarts_option": {
                "tooltip": {"trigger": "axis", "backgroundColor": "rgba(8,16,30,0.96)", "borderColor": "rgba(34,211,238,0.20)", "textStyle": {"color": "#e2f0ff"}},
                "legend": {"data": ["心率", "血氧", "体温"], "textStyle": {"color": "#7eb8d4"}},
                "grid": {"left": "4%", "right": "3%", "top": 48, "bottom": 32, "containLabel": True},
                "xAxis": {"type": "category", "data": [item.timestamp.strftime("%m-%d %H:%M") for item in points], "axisLabel": {"color": "#4d7a94"}, "axisLine": {"lineStyle": {"color": "rgba(56,189,248,0.15)"}}},
                "yAxis": [{"type": "value", "axisLabel": {"color": "#4d7a94"}, "splitLine": {"lineStyle": {"color": "rgba(56,189,248,0.08)"}}}, {"type": "value", "axisLabel": {"color": "#4d7a94"}, "splitLine": {"lineStyle": {"color": "rgba(56,189,248,0.08)"}}}],
                "series": [
                    {"name": "心率", "type": "line", "smooth": True, "showSymbol": False, "data": [item.heart_rate for item in points], "lineStyle": {"width": 2.5, "color": "#ff6b7a"}, "areaStyle": {"color": "rgba(255,107,122,0.10)"}},
                    {"name": "血氧", "type": "line", "smooth": True, "showSymbol": False, "data": [item.blood_oxygen for item in points], "lineStyle": {"width": 2.5, "color": "#22d3ee"}, "areaStyle": {"color": "rgba(34,211,238,0.10)"}},
                    {"name": "体温", "type": "line", "smooth": True, "showSymbol": False, "yAxisIndex": 1, "data": [item.temperature for item in points], "lineStyle": {"width": 2.5, "color": "#fb923c"}, "areaStyle": {"color": "rgba(251,146,60,0.10)"}},
                ],
            },
        }
        return [
            {
                "id": f"{device_mac}-cards",
                "title": "对象分析摘要",
                "summary": "评分、异常检测和最新风险信号的汇总。",
                "render_type": "metric_cards",
                "render_payload": {"cards": cards},
                "source_tool": "analysis_model",
            },
            {
                "id": f"{device_mac}-chart",
                "title": "趋势图",
                "summary": "用于观察连续变化和异常抬升。",
                "render_type": "echarts",
                "render_payload": {"charts": [chart]},
                "source_tool": "analysis_model",
            },
        ]

    def _build_community_attachments(self, analysis_payload: dict[str, Any]) -> list[dict[str, Any]]:
        high_risk_entities = analysis_payload.get("high_risk_entities", [])
        risk_distribution = analysis_payload.get("risk_distribution", {})
        cluster_summary = analysis_payload.get("cluster_summary", {})
        attachments: list[dict[str, Any]] = []
        risk_label_map = {"low": "低风险", "medium": "中风险", "high": "高风险", "warning": "预警", "critical": "危急", "normal": "稳定", "unknown": "待评估", "stable": "稳定", "attention": "关注", "danger": "高风险"}
        risk_tone_map = {"low": "accent", "normal": "accent", "stable": "accent", "medium": "default", "attention": "default", "high": "danger", "warning": "danger", "critical": "danger", "danger": "danger", "unknown": "default"}
        cards = [
            {
                "id": key,
                "label": risk_label_map.get(key, key),
                "value": f"{value} 人",
                "tone": risk_tone_map.get(key, "default"),
            }
            for key, value in risk_distribution.items()
        ]
        if cards:
            attachments.append({
                "id": "community-risk-cards",
                "title": "社区风险分布",
                "summary": "用于快速判断当前值守窗口的风险结构。",
                "render_type": "metric_cards",
                "render_payload": {"cards": cards},
                "source_tool": "analysis_model",
            })
        _risk_cn = {"low": "低风险", "medium": "中风险", "high": "高风险", "warning": "预警", "critical": "危急", "normal": "稳定", "stable": "稳定", "attention": "关注", "danger": "高风险", "unknown": "待评估"}
        rows = [{
            "subject": item.get("subject_label", ""),
            "device": item.get("device_mac", ""),
            "risk": _risk_cn.get(item.get("risk_level", ""), item.get("risk_level", "--")),
            "score": item.get("latest_health_score", ""),
            "alarms": item.get("active_alarm_count", 0),
        } for item in high_risk_entities]
        if rows:
            attachments.append({
                "id": "community-risk-table",
                "title": "重点关注名单",
                "summary": "按风险等级和健康评分排序的对象列表。",
                "render_type": "table",
                "render_payload": {
                    "columns": [
                        {"key": "subject", "label": "对象"},
                        {"key": "device", "label": "设备"},
                        {"key": "risk", "label": "风险"},
                        {"key": "score", "label": "评分"},
                        {"key": "alarms", "label": "告警"},
                    ],
                    "rows": rows,
                },
                "source_tool": "analysis_model",
            })
        if cluster_summary.get("trend"):
            trend_data = cluster_summary["trend"]
            label_map = {"healthy": "健康", "attention": "关注", "danger": "危险", "normal": "正常", "warning": "预警", "critical": "危急"}
            color_map = {
                "healthy": "#34d399",  # emerald green
                "normal": "#34d399",
                "attention": "#fbbf24",  # amber
                "warning": "#fb923c",   # orange
                "danger": "#f87171",    # red
                "critical": "#e11d48",  # rose
            }
            pie_data = [
                {
                    "name": label_map.get(key, key),
                    "value": value,
                    "itemStyle": {"color": color_map.get(key, "#60a5fa")},
                }
                for key, value in trend_data.items() if isinstance(value, (int, float)) and value > 0
            ]
            if not pie_data:
                pie_data = [{"name": "暂无数据", "value": 1, "itemStyle": {"color": "#334155"}}]
            attachments.append({
                "id": "community-risk-chart",
                "title": "社区健康聚类分布",
                "summary": "展示健康、关注、危险三类老人的当前分布比例。",
                "render_type": "echarts",
                "render_payload": {
                    "charts": [{
                        "id": "community-cluster-trend",
                        "title": "社区聚类概览",
                        "summary": "基于最新样本的健康/关注/危险分布。",
                        "echarts_option": {
                            "backgroundColor": "transparent",
                            "tooltip": {
                                "trigger": "item",
                                "formatter": "{b}: {c} 人 ({d}%)",
                                "backgroundColor": "rgba(8,16,30,0.96)",
                                "borderColor": "rgba(34,211,238,0.20)",
                                "textStyle": {"color": "#e2f0ff", "fontSize": 14},
                            },
                            "legend": {
                                "orient": "vertical",
                                "left": 12,
                                "top": "center",
                                "textStyle": {"color": "#7eb8d4", "fontSize": 15, "fontWeight": "bold"},
                                "data": [item["name"] for item in pie_data],
                                "icon": "circle",
                                "itemWidth": 12,
                                "itemHeight": 12,
                                "itemGap": 14,
                            },
                            "series": [{
                                "type": "pie",
                                "radius": ["40%", "68%"],
                                "center": ["62%", "50%"],
                                "avoidLabelOverlap": True,
                                "label": {
                                    "show": True,
                                    "color": "#e2f0ff",
                                    "fontSize": 15,
                                    "fontWeight": "bold",
                                    "formatter": "{b}\n{d}%",
                                },
                                "labelLine": {
                                    "show": True,
                                    "lineStyle": {"color": "rgba(56,189,248,0.35)", "width": 1.5},
                                },
                                "emphasis": {
                                    "label": {"fontSize": 17, "fontWeight": "bold"},
                                    "itemStyle": {"shadowBlur": 12, "shadowColor": "rgba(0,0,0,0.4)"},
                                },
                                "data": pie_data,
                            }],
                        },
                    }],
                },
                "source_tool": "analysis_model",
            })
        return attachments

    def _report_markdown(self, document_title: str, sections: list[dict[str, Any]]) -> str:
        lines = [f"# {document_title}"]
        for section in sections:
            title = str(section.get("title", "未命名章节")).strip() or "未命名章节"
            content = str(section.get("content", "暂无内容。")).strip() or "暂无内容。"
            lines.append(f"\n## {title}\n{content}")
        return "\n".join(lines)

    def _build_report_attachment(self, *, scope: str, subject: dict[str, Any] | None, analysis_payload: dict[str, Any], citations: list[dict[str, Any]], window_label: str) -> dict[str, Any]:
        subject_label = "社区辖区" if scope == AnalysisScope.COMMUNITY.value else str((subject or {}).get("label", "目标对象"))
        sections = [
            {"title": "执行摘要", "content": self._report_summary_text(scope, subject_label, analysis_payload, window_label)},
            {"title": "关键发现", "content": "\n".join(f"• {item}" for item in analysis_payload.get("key_findings", [])[:6]) or "暂无。"},
            {"title": "处置建议", "content": "\n".join(f"• {item}" for item in analysis_payload.get("recommendations", [])[:6]) or "暂无。"},
            {"title": "知识证据", "content": "\n".join(f"• {item['title']} - {item['source_path']}" for item in citations[:6]) or "暂无。"},
        ]
        return {
            "render_type": "report_document",
            "title": f"{subject_label}{window_label}健康分析报告",
            "subject": subject or {"label": subject_label},
            "window_label": window_label,
            "summary": sections[0]["content"] if sections else "暂无摘要。",
            "render_payload": {
                "document_title": f"{subject_label}{window_label}健康分析报告",
                "sections": sections,
                "markdown": self._report_markdown(
                    f"{subject_label}{window_label}健康分析报告",
                    sections,
                ),
                "citations": [
                    {
                        "title": item.get("title", ""),
                        "source_path": item.get("source_path", ""),
                    }
                    for item in citations[:6]
                ],
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source_tool": "generate_analysis_report",
        }

    def _missing_qwen_config_fields(self) -> list[str]:
        return list(self._settings.qwen_missing_config_fields)

    def _qwen_unavailable_message(self) -> str:
        missing = self._missing_qwen_config_fields()
        if missing:
            return f"当前智能体默认使用 Qwen，但服务端尚未完成配置：缺少 {', '.join(missing)}。请在后端 .env 中补齐后重试。"
        return "当前智能体默认使用 Qwen，但 Qwen 服务暂不可用，请检查后端配置后重试。"

    def _llm_failure_notice(self, exc: Exception) -> str:
        detail = str(exc).strip()
        normalized = detail.lower()
        if "freetieronly" in normalized or "allocationquota" in normalized or "free tier" in normalized:
            return (
                "当前 Qwen 免费额度已耗尽。请在阿里云百炼 / DashScope 控制台关闭 "
                "\"use free tier only\" 或开通可用额度后重试；以下先提供基于监测数据的结构化摘要。"
            )
        if "llm_not_available" in normalized:
            return "当前 Qwen 服务暂不可用，以下先提供基于监测数据的结构化摘要。"
        return "当前 Qwen 调用失败，以下先提供基于监测数据的结构化摘要。"

    def _fallback_answer(self, state: AgentState, exc: Exception | None = None) -> str:
        summary = self._deterministic_answer(state)
        if exc is None:
            return summary
        notice = self._llm_failure_notice(exc)
        return f"{notice}\n{summary}" if summary else notice

    def _generate_answer(self, state: AgentState) -> str:
        import logging
        import traceback

        _logger = logging.getLogger(__name__)
        provider = state.get("selected_provider", "qwen") or "qwen"
        if provider == "auto":
            provider = "qwen"

        if provider == "qwen" and not self._settings.tongyi_chat_configured:
            degraded = list(state.get("degraded_notes", []))
            degraded.append(f"qwen_not_configured:{','.join(self._missing_qwen_config_fields()) or 'unknown'}")
            state["degraded_notes"] = self._dedupe_strings(degraded)
            return self._qwen_unavailable_message()

        _logger.warning("[_generate_answer] resolved provider=%s tongyi_configured=%s", provider, self._settings.tongyi_chat_configured)
        fallback_exc: Exception | None = None
        try:
            llm = self._build_llm(provider, streaming=False)
            if llm is None:
                raise RuntimeError("llm_not_available")
            prompt_messages = self._build_prompt(state)
            _logger.warning("[_generate_answer] invoking LLM with %d messages", len(prompt_messages))
            message = llm.invoke(prompt_messages)
            content = getattr(message, "content", "") or ""
            if isinstance(content, list):
                content = "\n".join(str(item) for item in content)
            if str(content).strip():
                _logger.warning("[_generate_answer] LLM returned %d chars", len(content))
                return str(content).strip()
            _logger.warning("[_generate_answer] LLM returned empty content")
        except Exception as exc:
            _logger.error("[_generate_answer] LLM call failed: %s\n%s", exc, traceback.format_exc())
            degraded = list(state.get("degraded_notes", []))
            degraded.append(f"llm_fallback_to_deterministic_summary:{type(exc).__name__}:{str(exc)[:120]}")
            state["degraded_notes"] = self._dedupe_strings(degraded)
            fallback_exc = exc
        return self._fallback_answer(state, fallback_exc)

    def _compact_analysis_payload(self, analysis_payload: dict[str, Any]) -> str:
        if not analysis_payload:
            return "暂无结构化分析数据。"
        scope = analysis_payload.get("scope", "")
        lines: list[str] = []
        if scope == AnalysisScope.COMMUNITY.value:
            risk_dist = analysis_payload.get("risk_distribution", {})
            if risk_dist:
                lines.append("风险分布：" + "、".join(f"{k} {v}台" for k, v in risk_dist.items()))
            high_risk = analysis_payload.get("high_risk_entities", [])[:4]
            if high_risk:
                lines.append("重点关注：" + "；".join(
                    f"{item.get('subject_label', item.get('device_mac', ''))}（{item.get('risk_level', '')} 评分{item.get('latest_health_score', '--')}）"
                    for item in high_risk
                ))
        else:
            device_analysis = analysis_payload.get("device_analysis", {})
            if device_analysis:
                lines.append(f"设备风险：{device_analysis.get('risk_level', '--')} 健康评分：{device_analysis.get('latest_health_score', '--')}")
                tags = device_analysis.get("abnormal_tags", [])[:4]
                if tags:
                    lines.append(f"异常标签：{'、'.join(tags)}")
        for finding in analysis_payload.get("key_findings", [])[:4]:
            lines.append(f"发现：{finding}")
        for rec in analysis_payload.get("recommendations", [])[:3]:
            lines.append(f"建议：{rec}")
        return "\n".join(lines) or "暂无关键数据。"

    def _build_llm(self, provider: str, streaming: bool = True):
        import logging

        logging.getLogger(__name__).warning("[_build_llm] provider=%s streaming=%s configured=%s", provider, streaming, self._settings.tongyi_chat_configured)
        if provider == "qwen":
            if not self._settings.tongyi_chat_configured:
                return None
            _ensure_safe_tongyi_patch()
            return ChatTongyi(
                model=self._settings.tongyi_chat_model,
                api_key=self._settings.qwen_api_key,
                streaming=streaming,
            )
        if provider == "ollama" and ChatOllama and self._settings.ollama_base_url:
            return ChatOllama(
                model=self._settings.ollama_model,
                base_url=self._settings.ollama_base_url,
                temperature=0.1,
                streaming=streaming,
            )
        return None

    def _format_result(self, state: AgentState) -> dict[str, object]:
        return {
            "answer": state.get("answer", ""),
            "references": [item["source_path"] for item in state.get("citations", [])],
            "analysis": state.get("analysis_payload", {}),
            "attachments": state.get("attachments", []),
            "citations": list(state.get("citations") or []),
            "artifact_ids": state.get("artifact_ids", []),
            "scope": state.get("scope", AnalysisScope.COMMUNITY.value),
            "window": state.get("window", WindowKind.DAY.value),
            "subject": state.get("subject"),
        }

    def _scope_label(self, scope: str) -> str:
        return "某位老人" if scope == AnalysisScope.ELDER.value else "整个社区"

    def _window_label(self, window: str) -> str:
        return "过去一周" if window == WindowKind.WEEK.value else "过去一天"

    def _normalize_provider(self, provider: str) -> str:
        normalized = (provider or "qwen").strip().lower()
        if normalized in {"qwen", "tongyi"}:
            return "qwen"
        return normalized if normalized in {"ollama"} else "qwen"

    def _resolve_model_name(self, provider: str) -> str:
        if provider in {"qwen", "tongyi", "auto"}:
            return self._settings.tongyi_chat_model
        if provider == "ollama" and ChatOllama and self._settings.ollama_model:
            return self._settings.ollama_model
        return self._settings.tongyi_chat_model

    def _sample_to_window_point(self, sample: HealthSample) -> dict[str, Any]:
        systolic, diastolic = sample.blood_pressure_pair
        return {
            "timestamp": sample.timestamp,
            "heart_rate": sample.heart_rate,
            "spo2": sample.blood_oxygen,
            "sbp": systolic,
            "dbp": diastolic,
            "body_temp": sample.temperature,
            "fall_detection": sample.sos_flag,
            "data_accuracy": 96,
        }

    def _metric_snapshot(self, samples: list[HealthSample], attr: str) -> dict[str, Any]:
        values = [getattr(item, attr) for item in samples if getattr(item, attr) is not None]
        if not values:
            return {"latest": None, "average": None, "min": None, "max": None, "trend": "flat"}
        trend = "flat"
        if len(values) >= 2 and values[-1] > values[0]:
            trend = "up"
        elif len(values) >= 2 and values[-1] < values[0]:
            trend = "down"
        return {
            "latest": values[-1],
            "average": round(sum(values) / len(values), 2),
            "min": min(values),
            "max": max(values),
            "trend": trend,
        }

    def _subject_label_for_device(self, device_mac: str) -> str:
        directory = self._care_service.get_directory()
        elder = next((item for item in directory.elders if device_mac.upper() in list(getattr(item, "device_macs", [])) or item.device_mac == device_mac.upper()), None)
        if elder is not None:
            return elder.name
        demo_subject = next((item for item in self._demo_subject_provider() if device_mac.upper() in item.device_macs), None)
        return demo_subject.elder_name if demo_subject else device_mac.upper()

    def _build_retrieval_query(self, state: AgentState) -> str:
        analysis = state.get("analysis_payload", {})
        abnormal_tags: list[str] = []
        if state.get("scope") == AnalysisScope.ELDER.value:
            abnormal_tags = analysis.get("device_analysis", {}).get("abnormal_tags", [])
        else:
            abnormal_tags = [item for row in analysis.get("device_analyses", []) for item in row.get("abnormal_tags", [])]
        return f"{state.get('question', '')} {self._scope_label(state.get('scope', 'community'))} {self._window_label(state.get('window', 'day'))} {' '.join(self._dedupe_strings(abnormal_tags)[:5])}".strip()

    def _dedupe_strings(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for value in values:
            normalized = str(value).strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(normalized)
        return ordered

    def _dedupe_attachments(self, attachments: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen_ids: set[str] = set()
        seen_report_document = False
        ordered: list[dict[str, Any]] = []
        for attachment in attachments:
            attachment_id = str(attachment.get("id", ""))
            render_type = str(attachment.get("render_type", ""))
            # Only keep the first report_document attachment — subsequent ones are duplicates
            # generated by fallback paths (e.g. _build_report_attachment after tool already produced one).
            if render_type == "report_document":
                if seen_report_document:
                    continue
                seen_report_document = True
            if not attachment_id or attachment_id in seen_ids:
                continue
            seen_ids.add(attachment_id)
            ordered.append(attachment)
        return ordered

    def _total_sample_count(self, state: AgentState) -> int:
        return sum(len(samples) for samples in state.get("device_histories", {}).values())

    def _stage_summary(self, stage: str, state: AgentState | None = None, *, status: str = "completed") -> str:
        if status == "running":
            return {
                "scope_resolve": "正在识别当前提问对应的分析对象。",
                "window_resolve": "正在确认时间窗口与取数范围。",
                "data_load": "正在读取数据库与实时流中的窗口样本。",
                "model_analysis": "正在调用评分、异常检测与群体分析能力。",
                "rag_retrieve": "正在检索知识证据并执行重排序。",
                "tool_loop": "正在执行高层工具并整理关键输出。",
                "synthesis": "正在综合数据结论、证据与建议。",
                "artifact_render": "正在整理图表、表格与报告。",
                "session_persist": "正在完成本次会话收尾。",
            }.get(stage, "正在处理相关上下文。")

        state = state or {}
        if stage == "scope_resolve":
            subject = state.get("subject") or {}
            subject_label = str(subject.get("label") or self._scope_label(state.get("scope", AnalysisScope.COMMUNITY.value)))
            return f"已锁定分析对象：{subject_label}。"
        if stage == "window_resolve":
            return f"已确认分析窗口：{self._window_label(state.get('window', WindowKind.DAY.value))}。"
        if stage == "data_load":
            return f"已载入 {len(state.get('device_histories', {}))} 台设备、{self._total_sample_count(state)} 条窗口样本。"
        if stage == "model_analysis":
            return "已完成健康评分、异常检测和群体风险分析。"
        if stage == "rag_retrieve":
            count = len(state.get("citations", []))
            return f"知识检索命中 {count} 条证据，已用于后续建议生成。"
        if stage == "tool_loop":
            return f"已整理 {len(state.get('tool_results', []))} 个高层工具结果。"
        if stage == "synthesis":
            return "已生成面向社区值守的综合结论。"
        if stage == "artifact_render":
            return f"已整理 {len(state.get('attachments', []))} 个线程内附件与报告。"
        if stage == "session_persist":
            return "本次分析结果已完成会话收尾。"
        return "已完成当前步骤。"

    def _tool_kind(self, tool_name: str) -> str:
        return {
            "query_window_dataset": "data_query",
            "analyze_health_window": "analysis",
            "generate_analysis_report": "report",
            "synthesize_recommendations": "recommendation",
        }.get(tool_name, "analysis")

    def _tool_title(self, tool_name: str) -> str:
        return {
            "query_window_dataset": "读取窗口数据",
            "analyze_health_window": "综合健康分析",
            "generate_analysis_report": "生成分析报告",
            "synthesize_recommendations": "综合建议生成",
        }.get(tool_name, tool_name)

    def _tool_input_preview(self, tool_name: str, payload: dict[str, Any]) -> str:
        subject = payload.get("subject") if isinstance(payload.get("subject"), dict) else {}
        subject_label = str(subject.get("label") or ("整个社区" if payload.get("scope") != AnalysisScope.ELDER.value else "目标老人"))
        window_label = self._window_label(str(payload.get("window") or WindowKind.DAY.value))
        device_count = len([item for item in payload.get("device_macs", []) if item])
        if tool_name == "query_window_dataset":
            metrics = payload.get("metrics", [])
            metric_text = ", ".join(str(item) for item in metrics[:4]) if isinstance(metrics, list) and metrics else "默认指标"
            return f"{subject_label} / {window_label} / {metric_text}"
        if tool_name == "analyze_health_window":
            return f"{subject_label} / {window_label} / {device_count or 1} 台设备"
        if tool_name == "generate_analysis_report":
            return f"{subject_label} / {window_label} / 结构化报告"
        if tool_name == "synthesize_recommendations":
            return f"{subject_label} / {window_label} / 数据 + RAG + 搜索"
        return "已准备工具输入。"

    def _tool_output_preview(self, tool_name: str, data: dict[str, Any]) -> str:
        if tool_name == "query_window_dataset":
            dataset = data.get("dataset", {})
            return f"命中 {dataset.get('device_count', 0)} 台设备，样本 {dataset.get('sample_count', 0)} 条。"
        if tool_name == "analyze_health_window":
            analysis = data.get("analysis", {})
            if analysis.get("scope") == AnalysisScope.ELDER.value:
                return f"风险等级 {analysis.get('risk_level', '--')}，异常概率 {analysis.get('anomaly_probability', '--')}。"
            return f"高风险对象 {len(analysis.get('high_risk_entities', []))} 个，图表 {analysis.get('chart_count', 0)} 张。"
        if tool_name == "generate_analysis_report":
            report = data.get("report", {})
            return f"报告章节 {len(report.get('sections', []))} 段。"
        if tool_name == "synthesize_recommendations":
            return f"建议 {len(data.get('recommendations', []))} 条，外部参考 {len(data.get('web_results', []))} 条。"
        return "工具调用已完成。"

    def _extract_child_tools(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        raw = data.get("child_tools", [])
        if not isinstance(raw, list):
            return []
        child_tools: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            child_tools.append(
                {
                    "name": str(item.get("name", "child_tool")),
                    "title": str(item.get("title", item.get("name", "child_tool"))),
                    "summary": str(item.get("summary", "")),
                    "status": str(item.get("status", "completed")),
                }
            )
        return child_tools

    def _tool_context_lines(self, state: AgentState) -> list[str]:
        lines: list[str] = []
        for item in state.get("tool_results", []):
            title = str(item.get("title") or item.get("tool_name", "工具"))
            summary = str(item.get("summary", "")).strip()
            output_preview = str(item.get("output_preview", "")).strip()
            if summary:
                lines.append(f"{title}：{summary}")
            if output_preview:
                lines.append(f"{title}输出：{output_preview}")
            for child in item.get("child_tools", []):
                if not isinstance(child, dict):
                    continue
                child_title = str(child.get("title") or child.get("name", "子工具"))
                child_summary = str(child.get("summary", "")).strip()
                if child_summary:
                    lines.append(f"{child_title}：{child_summary}")
        return lines[:10]

    def _recommendation_lines(self, state: AgentState) -> list[str]:
        lines: list[str] = []
        for item in state.get("tool_results", []):
            if item.get("tool_name") != "synthesize_recommendations":
                continue
            data = item.get("data", {})
            if not isinstance(data, dict):
                continue
            lines.extend(str(entry) for entry in data.get("recommendations", []) if str(entry).strip())
        return self._dedupe_strings(lines)

    def _tool_started_event(self, call: ToolInvocation) -> dict[str, object]:
        return {
            "type": "tool.started",
            "stage": "tool_loop",
            "tool_name": call.name,
            "request_id": call.request_id or str(uuid4()),
            "title": self._tool_title(call.name),
            "tool_kind": self._tool_kind(call.name),
            "summary": "已进入执行队列。",
            "input_preview": self._tool_input_preview(call.name, call.payload),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _tool_finished_event(self, item: dict[str, Any]) -> dict[str, object]:
        return {
            "type": "tool.finished",
            "stage": "tool_loop",
            "tool_name": item["tool_name"],
            "request_id": item["request_id"],
            "source": item.get("source", "internal_tool"),
            "status": item.get("status", "ok"),
            "success": item.get("success", True),
            "title": item.get("title"),
            "tool_kind": item.get("tool_kind"),
            "summary": item.get("summary", ""),
            "input_preview": item.get("input_preview", ""),
            "output_preview": item.get("output_preview", ""),
            "child_tools": item.get("child_tools", []),
            "attachments": item.get("attachments", []),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _stream_tool_events(self, item: dict[str, Any]) -> Iterator[dict[str, object]]:
        if item.get("tool_name") != "generate_analysis_report":
            yield self._tool_finished_event(item)
            return

        attachments = item.get("attachments", [])
        report_attachment = next(
            (attachment for attachment in attachments if attachment.get("render_type") == "report_document"),
            None,
        )
        if not report_attachment:
            yield self._tool_finished_event(item)
            return

        payload = report_attachment.get("render_payload", {})
        if not isinstance(payload, dict):
            yield self._tool_finished_event(item)
            return

        sections = payload.get("sections", [])
        if not isinstance(sections, list) or not sections:
            yield self._tool_finished_event(item)
            return

        document_title = str(payload.get("document_title") or report_attachment.get("title") or "结构化分析报告")
        partial_sections: list[dict[str, Any]] = []
        total_sections = len(sections)
        for index, section in enumerate(sections, start=1):
            if not isinstance(section, dict):
                continue
            partial_sections.append(section)
            partial_attachment = {
                **report_attachment,
                "summary": f"报告已生成第 {index}/{total_sections} 个章节。",
                "render_payload": {
                    **payload,
                    "sections": list(partial_sections),
                    "markdown": self._report_markdown(document_title, partial_sections),
                },
            }
            yield self._tool_finished_event(
                {
                    **item,
                    "status": "streaming" if index < total_sections else item.get("status", "completed"),
                    "summary": (
                        f"报告已整理到第 {index}/{total_sections} 个章节。"
                        if index < total_sections
                        else item.get("summary", "")
                    ),
                    "output_preview": (
                        f"当前可查看 {index}/{total_sections} 个章节。"
                        if index < total_sections
                        else item.get("output_preview", "")
                    ),
                    "attachments": [partial_attachment],
                }
            )

    def _risk_weight(self, level: str) -> int:
        return {"critical": 4, "warning": 3, "high": 3, "attention": 2, "medium": 2, "low": 1, "normal": 0}.get(level, 0)

    def _tool_summary(self, tool_name: str, data: dict[str, Any]) -> str:
        if tool_name == "query_alert_history":
            return f"已提取 {len(data.get('alerts', []))} 条窗口告警。"
        if tool_name == "build_chart_payloads":
            return f"已生成 {len(data.get('charts', []))} 张图表。"
        if tool_name == "summarize_window_metrics":
            return "已生成社区窗口结构化摘要。"
        if tool_name == "evaluate_window_health":
            return f"窗口健康评分 {data.get('health_score', '--')}，风险等级 {data.get('risk_level', '--')}。"
        if tool_name == "analyze_device_anomaly":
            return f"时序异常概率 {data.get('probability', '--')}。"
        if tool_name == "analyze_community_risk":
            return f"已完成 {data.get('device_count', 0)} 台设备的群体分析。"
        return "工具调用已完成。"

    def _stage_event(self, stage: str, status: str) -> dict[str, object]:
        labels = {
            "scope_resolve": "分析对象识别",
            "window_resolve": "分析窗口确认",
            "data_load": "样本数据载入",
            "model_analysis": "评分与异常分析",
            "rag_retrieve": "知识检索与重排序",
            "tool_loop": "工具结果整合",
            "synthesis": "答案综合生成",
            "artifact_render": "图表与报告整理",
            "session_persist": "会话收尾",
        }
        return {
            "type": "stage.changed",
            "stage": stage,
            "status": status,
            "label": labels.get(stage, stage),
            "detail": "",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _stage_notes(self, stage: str, state: AgentState) -> list[str]:
        if stage == "data_load":
            return [f"已载入 {len(state.get('device_histories', {}))} 台设备的窗口样本。"]
        if stage == "model_analysis":
            return ["已完成真实评分、异常检测和群体归纳。"]
        if stage == "rag_retrieve":
            return [f"知识证据命中 {len(state.get('citations', []))} 条。"]
        if stage == "artifact_render":
            return [f"当前共整理 {len(state.get('attachments', []))} 个结构化附件。"]
        return []

    def _build_prompt(self, state: AgentState):
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "你是社区健康监测工作台中的真实智能体。必须严格基于结构化健康数据、模型分析结果和工具输出作答，禁止臆测。直接给出专业结论，不要使用空泛套话，不要单列“参考知识”栏目，也不要复述工具名称。",
                ),
                (
                    "human",
                    "分析范围：{scope}\n分析窗口：{window}\n用户问题：{question}\n历史对话：{history}\n结构化分析摘要：\n{analysis_payload}\n工具结果摘要：\n{tool_results}\n知识证据（仅供内部参考，不必单列输出）：\n{citations}\n请输出自然语言分析，至少包含：1. 当前健康分与风险等级；2. 心率、血氧、血压、体温等关键指标趋势；3. 异常可能原因；4. 明确、可执行的处置建议。",
                ),
            ]
        )
        return prompt.format_messages(
            scope=self._scope_label(state.get("scope", "")),
            window=self._window_label(state.get("window", WindowKind.DAY.value)),
            question=state.get("question", ""),
            history="\n".join(f"{item['role']}: {item['content'][:120]}" for item in state.get("history", [])[-6:]) or "无",
            analysis_payload=self._compact_analysis_payload(state.get("analysis_payload", {})),
            tool_results="\n".join(self._tool_context_lines(state)) or "无",
            citations="\n".join(f"- {item.get('title', '')}: {item.get('snippet', '')[:100]}" for item in state.get("citations", [])[:3]) or "无",
        )

    def _deterministic_answer(self, state: AgentState) -> str:
        analysis = state.get("analysis_payload", {})
        findings = [str(item).strip() for item in analysis.get("key_findings", []) if str(item).strip()]
        recommendations = self._dedupe_strings(
            [str(item).strip() for item in analysis.get("recommendations", []) if str(item).strip()]
            + self._recommendation_lines(state)
        )
        tool_lines = [str(item).strip() for item in self._tool_context_lines(state) if str(item).strip()]

        scope_text = self._scope_label(state.get("scope", AnalysisScope.COMMUNITY.value))
        window_text = self._window_label(state.get("window", WindowKind.DAY.value))

        facts = findings if findings else tool_lines
        lines: list[str] = []
        if facts:
            lines.extend(f"- {item}" for item in facts[:6])
        else:
            lines.append(f"- 已完成{scope_text}{window_text}的数据汇总与风险扫描。")

        lines.extend(f"- 建议：{item}" for item in recommendations[:4])
        return "\n".join(lines)

    def _tool_summary(self, tool_name: str, data: dict[str, Any]) -> str:
        if tool_name == "query_window_dataset":
            dataset = data.get("dataset", {})
            return f"已读取 {dataset.get('device_count', 0)} 台设备、{dataset.get('sample_count', 0)} 条时间窗样本。"
        if tool_name == "analyze_health_window":
            analysis = data.get("analysis", {})
            if analysis.get("scope") == AnalysisScope.ELDER.value:
                return f"已完成单老人窗口评分、异常检测和图表整理，风险等级 {analysis.get('risk_level', '--')}。"
            return f"已完成社区窗口评分、聚类排序和图表整理，高风险对象 {len(analysis.get('high_risk_entities', []))} 个。"
        if tool_name == "generate_analysis_report":
            report = data.get("report", {})
            return f"已整理结构化报告，共 {len(report.get('sections', []))} 个章节。"
        if tool_name == "synthesize_recommendations":
            return f"已生成 {len(data.get('recommendations', []))} 条综合建议，并整合 {len(data.get('web_results', []))} 条外部参考。"
        return "工具调用已完成。"

    def _stage_event(
        self,
        stage: str,
        status: str,
        *,
        state: AgentState | None = None,
        elapsed_ms: int | None = None,
    ) -> dict[str, object]:
        labels = {
            "scope_resolve": "分析对象识别",
            "window_resolve": "分析窗口确认",
            "data_load": "数据读取",
            "model_analysis": "评分与异常分析",
            "rag_retrieve": "知识检索与重排序",
            "tool_loop": "工具结果整合",
            "synthesis": "答案与建议生成",
            "artifact_render": "图表与报告整理",
            "session_persist": "会话收尾",
        }
        summary = self._stage_summary(stage, state, status=status)
        return {
            "type": "stage.changed",
            "stage": stage,
            "status": status,
            "label": labels.get(stage, stage),
            "detail": summary,
            "summary": summary,
            "elapsed_ms": elapsed_ms,
            "group": "trace",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
