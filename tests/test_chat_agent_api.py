from __future__ import annotations

import asyncio

from backend.api.agent_api import list_agent_elders
from backend.api.chat_api import CommunityAnalysisRequest, analyze_community
from backend.dependencies import get_agent_service
from backend.models.user_model import UserRole
from backend.dependencies import get_care_service


def _community_authorization() -> str:
    accounts = get_care_service().list_auth_accounts()
    community_account = next(
        account for account in accounts if getattr(account.role, "value", account.role) == "community"
    )
    login = get_care_service().login(community_account.username, community_account.default_password)
    assert login is not None
    return f"Bearer {login.token}"


def test_agent_elders_returns_real_and_demo_subjects() -> None:
    subjects = asyncio.run(list_agent_elders(authorization=_community_authorization()))

    assert subjects
    assert any(subject.is_demo_subject for subject in subjects)
    assert all(subject.elder_name for subject in subjects)


def test_chat_api_supports_community_scope_analysis() -> None:
    payload = CommunityAnalysisRequest(
        question="请总结当前社区一天内的重点风险。",
        scope="community",
        window="day",
        workflow="overview",
        provider="ollama",
        mode="ollama",
    )

    result = asyncio.run(analyze_community(payload))

    assert result["scope"] == "community"
    assert isinstance(result.get("attachments"), list)
    assert isinstance(result.get("citations"), list)
    assert result["answer"]


def test_chat_api_supports_elder_scope_analysis() -> None:
    subjects = asyncio.run(list_agent_elders(authorization=_community_authorization()))
    subject = subjects[0]
    payload = CommunityAnalysisRequest(
        question="请分析这位老人过去一周的主要风险和建议动作。",
        scope="elder",
        subject_elder_id=subject.elder_id,
        window="week",
        workflow="elder_focus",
        provider="ollama",
        mode="ollama",
    )

    result = asyncio.run(analyze_community(payload))

    assert result["scope"] == "elder"
    assert result.get("subject")
    assert isinstance(result.get("attachments"), list)
    assert result["answer"]


def test_agent_stream_emits_trace_and_high_level_tool_events() -> None:
    events = list(
        get_agent_service().stream_analyze_community(
            role=UserRole.COMMUNITY,
            question="请总结当前社区过去一天的风险态势并给出处置建议。",
            scope="community",
            window="day",
            workflow="overview",
            provider="ollama",
            mode="ollama",
        )
    )

    stage_events = [event for event in events if event.get("type") == "stage.changed"]
    tool_events = [event for event in events if event.get("type") == "tool.finished"]
    tool_names = {event.get("tool_name") for event in tool_events}

    assert stage_events
    assert any(event.get("group") == "trace" for event in stage_events)
    assert any(isinstance(event.get("summary"), str) and event.get("summary") for event in stage_events)
    assert "query_window_dataset" in tool_names
    assert "analyze_health_window" in tool_names
    assert "synthesize_recommendations" in tool_names

    dataset_event = next(event for event in tool_events if event.get("tool_name") == "query_window_dataset")
    assert dataset_event.get("tool_kind") == "data_query"
    assert isinstance(dataset_event.get("input_preview"), str)
    assert isinstance(dataset_event.get("output_preview"), str)


def test_agent_stream_emits_report_attachment_before_final_answer() -> None:
    events = list(
        get_agent_service().stream_analyze_community(
            role=UserRole.COMMUNITY,
            question="请生成当前社区过去一天的结构化分析报告。",
            scope="community",
            window="day",
            workflow="community_report",
            provider="ollama",
            mode="ollama",
            include_report=True,
        )
    )

    tool_events = [event for event in events if event.get("type") == "tool.finished"]
    report_event = next(event for event in tool_events if event.get("tool_name") == "generate_analysis_report")
    answer_completed_index = next(index for index, event in enumerate(events) if event.get("type") == "answer.completed")
    report_tool_index = next(index for index, event in enumerate(events) if event is report_event)

    assert report_tool_index < answer_completed_index
    assert isinstance(report_event.get("attachments"), list)
    assert report_event["attachments"]
    assert report_event["attachments"][0]["render_type"] == "report_document"
