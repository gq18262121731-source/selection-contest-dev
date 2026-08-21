from __future__ import annotations

import pytest

from backend.models.robot_emergency_model import RobotDialogueIntent
from backend.models.robot_navigation_model import RobotNavigationExecutionState

from test_robot_navigation_api import add_navigation_points, activate_map, build_service


def prepare_dispatched_case(tmp_path, incident_id="incident_dialogue"):
    client, service, _ = build_service(tmp_path)
    activate_map(service)
    add_navigation_points(client)
    response = client.post(
        f"/api/v1/robot/emergency/{incident_id}/dispatch",
        json={"area_id": "area_a", "area_name": "A区", "request_id": f"dispatch-{incident_id}"},
    )
    assert response.status_code == 201
    return client, service


def prepare_case(tmp_path, incident_id="incident_dialogue"):
    client, service = prepare_dispatched_case(tmp_path, incident_id)
    response = client.post(
        f"/api/v1/robot/emergency/{incident_id}/mock/dialogue/start",
        json={"request_id": f"dialogue-{incident_id}"},
    )
    assert response.status_code == 200
    return client, service


def test_mock_dialogue_start_advances_all_required_states_without_gateway_call(tmp_path):
    client, service = prepare_dispatched_case(tmp_path)
    case = service.emergency.require_case("incident_dialogue")
    task_id = case.robot_task_id or ""
    gateway_calls = len(service.gateway.session.calls)

    response = client.post(
        "/api/v1/robot/emergency/incident_dialogue/mock/dialogue/start",
        json={
            "request_id": "dialogue-start",
            "mock_prompt_text": "您还好吗？需要帮助吗？",
        },
    )

    assert response.status_code == 200
    bundle = response.json()["data"]
    assert bundle["provider"] == "mock" and bundle["real_motion_enabled"] is False
    assert bundle["emergency_case"]["execution_state"] == "waiting_response"
    assert [event["event_type"] for event in bundle["navigation_events"][-3:]] == [
        "arrived",
        "voice_prompting",
        "waiting_response",
    ]
    assert [item.message for item in service.tasks.list_timeline(task_id)[-3:]] == [
        "arrived",
        "voice_prompting",
        "waiting_response",
    ]
    assert bundle["emergency_case"]["metadata"]["mock_prompt"] == {
        "text": "您还好吗？需要帮助吗？",
        "asr_status": "pending_mock",
        "tts_status": "pending_mock",
        "source": "mock",
    }
    assert len(service.gateway.session.calls) == gateway_calls


def test_mock_dialogue_start_can_continue_from_arrived(tmp_path):
    client, service = prepare_dispatched_case(tmp_path)
    case = service.emergency.require_case("incident_dialogue")
    task = service.navigation.transition(
        case.robot_task_id or "",
        RobotNavigationExecutionState.ARRIVED,
        "pre-arrived",
        "arrived",
        incident_id=case.incident_id,
    )
    service.emergencies.save_case(
        case.model_copy(
            update={
                "execution_state": task.execution_state,
                "navigation_state": task.execution_state,
            }
        )
    )

    response = client.post(
        "/api/v1/robot/emergency/incident_dialogue/mock/dialogue/start",
        json={"request_id": "dialogue-from-arrived"},
    )
    assert response.status_code == 200
    events = response.json()["data"]["navigation_events"]
    assert [event["event_type"] for event in events[-2:]] == [
        "voice_prompting",
        "waiting_response",
    ]


@pytest.mark.parametrize("state", ["blocked", "failed", "cancelled", "completed"])
def test_mock_dialogue_start_rejects_terminal_or_blocked_states(tmp_path, state):
    client, service = prepare_dispatched_case(tmp_path, f"incident-{state}")
    case = service.emergency.require_case(f"incident-{state}")
    task = service.tasks.get_task(case.robot_task_id or "")
    state_value = RobotNavigationExecutionState(state)
    service.tasks.update_task(task.model_copy(update={"execution_state": state_value}))
    service.emergencies.save_case(
        case.model_copy(update={"execution_state": state_value, "navigation_state": state_value})
    )
    before_events = len(service.navigation_events.list_for_task(task.task_id))
    before_timeline = len(service.tasks.list_timeline(task.task_id))

    response = client.post(
        f"/api/v1/robot/emergency/incident-{state}/mock/dialogue/start",
        json={"request_id": f"dialogue-reject-{state}"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "INVALID_STATE_TRANSITION"
    assert len(service.navigation_events.list_for_task(task.task_id)) == before_events
    assert len(service.tasks.list_timeline(task.task_id)) == before_timeline


def test_mock_dialogue_start_replay_is_idempotent_and_conflicting_body_is_rejected(tmp_path):
    client, service = prepare_dispatched_case(tmp_path)
    body = {"request_id": "dialogue-replay", "mock_prompt_text": "请问您需要帮助吗？"}
    first = client.post(
        "/api/v1/robot/emergency/incident_dialogue/mock/dialogue/start",
        json=body,
    )
    task_id = first.json()["data"]["robot_task_id"]
    event_count = len(service.navigation_events.list_for_task(task_id))
    timeline_count = len(service.tasks.list_timeline(task_id))
    ws_sequence = service.event_hub.current_sequence

    replay = client.post(
        "/api/v1/robot/emergency/incident_dialogue/mock/dialogue/start",
        json=body,
    )
    assert replay.status_code == 200
    assert replay.json()["data"] == first.json()["data"]
    assert len(service.navigation_events.list_for_task(task_id)) == event_count
    assert len(service.tasks.list_timeline(task_id)) == timeline_count
    assert service.event_hub.current_sequence == ws_sequence

    conflict = client.post(
        "/api/v1/robot/emergency/incident_dialogue/mock/dialogue/start",
        json={**body, "mock_prompt_text": "另一段提示"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"

    another_operation = client.post(
        "/api/v1/robot/emergency/incident_dialogue/mock/dialogue/start",
        json={"request_id": "dialogue-already-started"},
    )
    assert another_operation.status_code == 409
    assert another_operation.json()["code"] == "DIALOGUE_ALREADY_STARTED"


def test_mock_state_advance_endpoints_report_missing_incident_and_task(tmp_path):
    client, service, _ = build_service(tmp_path)
    missing = client.post(
        "/api/v1/robot/emergency/missing/mock/dialogue/start",
        json={"request_id": "missing-incident"},
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == "INCIDENT_NOT_FOUND"

    client, service = prepare_dispatched_case(tmp_path / "missing-task")
    case = service.emergency.require_case("incident_dialogue")
    service.emergencies.save_case(case.model_copy(update={"robot_task_id": None}))
    missing_task = client.post(
        "/api/v1/robot/emergency/incident_dialogue/mock/dialogue/start",
        json={"request_id": "missing-task"},
    )
    assert missing_task.status_code == 404
    assert missing_task.json()["code"] == "TASK_NOT_FOUND"


@pytest.mark.parametrize(
    ("case_updates", "expected_code"),
    [
        ({"provider": "real"}, "MOCK_PROVIDER_CONTRACT_VIOLATION"),
        ({"real_motion_enabled": True}, "REAL_MOTION_DISABLED"),
    ],
)
def test_mock_state_advance_rejects_invalid_safety_contract(
    tmp_path,
    monkeypatch,
    case_updates,
    expected_code,
):
    client, service = prepare_dispatched_case(tmp_path)
    case = service.emergency.require_case("incident_dialogue")
    monkeypatch.setattr(
        service.emergency,
        "require_case",
        lambda _incident_id: case.model_copy(update=case_updates),
    )
    response = client.post(
        "/api/v1/robot/emergency/incident_dialogue/mock/dialogue/start",
        json={"request_id": "invalid-contract"},
    )
    assert response.status_code == 502
    assert response.json()["code"] == expected_code


@pytest.mark.parametrize(
    "extra",
    [
        {"target_state": "waiting_response"},
        {"provider": "mock"},
        {"real_motion_enabled": False},
        {"cmd_vel": 1},
        {"mock_prompt_text": "<b>帮助</b>"},
    ],
)
def test_mock_state_advance_dtos_reject_control_and_html_fields(tmp_path, extra):
    client, _ = prepare_dispatched_case(tmp_path)
    response = client.post(
        "/api/v1/robot/emergency/incident_dialogue/mock/dialogue/start",
        json={"request_id": "strict-dialogue", **extra},
    )
    assert response.status_code == 422


def test_four_dialogue_results_are_persisted(tmp_path):
    for intent in RobotDialogueIntent:
        incident_id = f"incident_{intent.value}"
        client, _ = prepare_case(tmp_path / intent.value, incident_id)
        response = client.post(
            f"/api/v1/robot/emergency/{incident_id}/escalate",
            json={"turn_id": f"turn-{intent.value}", "intent": intent.value, "request_id": f"result-{intent.value}"},
        )
        assert response.status_code == 200
        dialogue = client.get(f"/api/v1/robot/emergency/{incident_id}/dialogue").json()["data"]
        assert dialogue[0]["intent"] == intent.value


def test_safe_response_requires_ack_before_return(tmp_path):
    client, service = prepare_case(tmp_path)
    client.post(
        "/api/v1/robot/emergency/incident_dialogue/escalate",
        json={"turn_id": "turn-safe", "intent": "safe_response", "request_id": "safe-result"},
    )
    blocked = client.post(
        "/api/v1/robot/emergency/incident_dialogue/resolve-and-return",
        json={"request_id": "return-before-ack", "resolution": "安全"},
    )
    assert blocked.status_code == 409
    acknowledge_body = {"admin_id": "admin", "request_id": "ack"}
    acknowledged = client.post(
        "/api/v1/robot/emergency/incident_dialogue/acknowledge",
        json=acknowledge_body,
    )
    event_sequence = service.event_hub.current_sequence
    replayed_ack = client.post(
        "/api/v1/robot/emergency/incident_dialogue/acknowledge",
        json=acknowledge_body,
    )
    assert acknowledged.status_code == 200 and replayed_ack.status_code == 200
    assert service.event_hub.current_sequence == event_sequence
    return_body = {"request_id": "return-after-ack", "resolution": "安全"}
    returning = client.post(
        "/api/v1/robot/emergency/incident_dialogue/resolve-and-return",
        json=return_body,
    )
    assert returning.status_code == 200
    assert returning.json()["data"]["execution_state"] == RobotNavigationExecutionState.RETURNING_HOME.value
    gateway_calls = len(service.gateway.session.calls)
    event_sequence = service.event_hub.current_sequence
    replayed_return = client.post(
        "/api/v1/robot/emergency/incident_dialogue/resolve-and-return",
        json=return_body,
    )
    assert replayed_return.status_code == 200
    assert len(service.gateway.session.calls) == gateway_calls
    assert service.event_hub.current_sequence == event_sequence


def prepare_returning_case(tmp_path, incident_id="incident_return_complete"):
    client, service = prepare_case(tmp_path, incident_id)
    assert client.post(
        f"/api/v1/robot/emergency/{incident_id}/escalate",
        json={
            "turn_id": f"turn-{incident_id}",
            "intent": "safe_response",
            "request_id": f"safe-{incident_id}",
        },
    ).status_code == 200
    assert client.post(
        f"/api/v1/robot/emergency/{incident_id}/acknowledge",
        json={"admin_id": "admin", "request_id": f"ack-{incident_id}"},
    ).status_code == 200
    assert client.post(
        f"/api/v1/robot/emergency/{incident_id}/resolve-and-return",
        json={"request_id": f"return-{incident_id}", "resolution": "安全"},
    ).status_code == 200
    return client, service


def test_mock_return_complete_updates_bundle_task_and_persistence_without_gateway_call(tmp_path):
    client, service = prepare_returning_case(tmp_path)
    case = service.emergency.require_case("incident_return_complete")
    task_id = case.robot_task_id or ""
    gateway_calls = len(service.gateway.session.calls)

    response = client.post(
        "/api/v1/robot/emergency/incident_return_complete/mock/return/complete",
        json={"request_id": "complete-return"},
    )

    assert response.status_code == 200
    bundle = response.json()["data"]
    completed_case = bundle["emergency_case"]
    assert completed_case["status"] == "resolved"
    assert completed_case["execution_state"] == "completed"
    assert completed_case["navigation_state"] == "completed"
    assert completed_case["resolution"] == "Mock 返航完成，事件已结束"
    assert completed_case["resolved_at"] is not None
    task = service.tasks.get_task(task_id)
    assert task.status.value == "COMPLETED"
    assert task.execution_state == RobotNavigationExecutionState.COMPLETED
    assert service.navigation_events.get_event("complete-return").event_type == "return_home_completed"
    assert service.tasks.get_timeline_by_callback_id("complete-return") is not None
    assert len(service.gateway.session.calls) == gateway_calls


def test_mock_return_complete_replay_does_not_repeat_persistence_or_websocket(tmp_path):
    client, service = prepare_returning_case(tmp_path)
    body = {"request_id": "complete-replay"}
    first = client.post(
        "/api/v1/robot/emergency/incident_return_complete/mock/return/complete",
        json=body,
    )
    task_id = first.json()["data"]["robot_task_id"]
    event_count = len(service.navigation_events.list_for_task(task_id))
    timeline_count = len(service.tasks.list_timeline(task_id))
    ws_sequence = service.event_hub.current_sequence
    replay = client.post(
        "/api/v1/robot/emergency/incident_return_complete/mock/return/complete",
        json=body,
    )
    assert replay.status_code == 200
    assert replay.json()["data"] == first.json()["data"]
    assert len(service.navigation_events.list_for_task(task_id)) == event_count
    assert len(service.tasks.list_timeline(task_id)) == timeline_count
    assert service.event_hub.current_sequence == ws_sequence


@pytest.mark.parametrize("intent", ["need_help", "no_response", "uncertain"])
def test_escalated_dialogue_results_cannot_complete_return(tmp_path, intent):
    incident_id = f"incident-complete-{intent}"
    client, _ = prepare_case(tmp_path, incident_id)
    assert client.post(
        f"/api/v1/robot/emergency/{incident_id}/escalate",
        json={
            "turn_id": f"turn-{intent}",
            "intent": intent,
            "request_id": f"result-{intent}",
        },
    ).status_code == 200
    response = client.post(
        f"/api/v1/robot/emergency/{incident_id}/mock/return/complete",
        json={"request_id": f"complete-{intent}"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "SAFE_RESPONSE_REQUIRED"


def test_safe_case_not_returning_cannot_complete_return(tmp_path):
    client, _ = prepare_case(tmp_path)
    assert client.post(
        "/api/v1/robot/emergency/incident_dialogue/escalate",
        json={"turn_id": "turn-safe-wait", "intent": "safe_response", "request_id": "safe-wait"},
    ).status_code == 200
    assert client.post(
        "/api/v1/robot/emergency/incident_dialogue/acknowledge",
        json={"admin_id": "admin", "request_id": "ack-wait"},
    ).status_code == 200
    response = client.post(
        "/api/v1/robot/emergency/incident_dialogue/mock/return/complete",
        json={"request_id": "complete-before-return"},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "RETURN_NOT_IN_PROGRESS"


def test_mock_return_complete_request_rejects_completion_and_motion_fields(tmp_path):
    client, _ = prepare_returning_case(tmp_path)
    for extra in (
        {"success": True},
        {"completed": True},
        {"target_state": "completed"},
        {"robot_pose": {"x": 1, "y": 2}},
        {"speed": 1},
        {"cmd_vel": 1},
    ):
        response = client.post(
            "/api/v1/robot/emergency/incident_return_complete/mock/return/complete",
            json={"request_id": "strict-return", **extra},
        )
        assert response.status_code == 422


def test_help_response_cannot_return_home(tmp_path):
    client, _ = prepare_case(tmp_path)
    client.post(
        "/api/v1/robot/emergency/incident_dialogue/escalate",
        json={"turn_id": "turn-help", "intent": "need_help", "request_id": "help-result"},
    )
    client.post(
        "/api/v1/robot/emergency/incident_dialogue/acknowledge",
        json={"admin_id": "admin", "request_id": "ack-help"},
    )
    response = client.post(
        "/api/v1/robot/emergency/incident_dialogue/resolve-and-return",
        json={"request_id": "return-help", "resolution": "错误返航"},
    )
    assert response.status_code == 409
