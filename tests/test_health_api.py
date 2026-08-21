from __future__ import annotations

from fastapi.testclient import TestClient

from backend.api import agent_api, health_api
from backend.main import app


def _make_client(monkeypatch, test_services: dict[str, object]) -> TestClient:
    monkeypatch.setattr(health_api, "get_structured_health_score_service", lambda: test_services["score_service"])
    monkeypatch.setattr(health_api, "get_warning_evaluation_service", lambda: test_services["warning_service"])
    monkeypatch.setattr(agent_api, "get_explanation_service", lambda: test_services["explanation_service"])
    monkeypatch.setattr("backend.main.settings", __import__("backend.main", fromlist=["settings"]).settings)
    __import__("backend.main", fromlist=["settings"]).settings.use_mock_data = False
    return TestClient(app)


def test_health_score_api_normal(monkeypatch, test_services: dict[str, object]) -> None:
    client = _make_client(monkeypatch, test_services)
    response = client.post(
        "/api/v1/health/score",
        json={
            "elderly_id": "E10001",
            "device_id": "BAND_001",
            "timestamp": "2026-03-23T21:30:00+08:00",
            "heart_rate": 78,
            "spo2": 98,
            "sbp": 118,
            "dbp": 77,
            "body_temp": 36.6,
            "fall_detection": False,
            "data_accuracy": 97,
        },
    )
    body = response.json()
    assert response.status_code == 200
    assert body["code"] == "OK"
    assert body["data"]["risk_level"] in {"normal", "attention"}
    assert body["data"]["stability_mode"] == "robust_demo"
    assert body["data"]["active_events"] == []


def test_health_score_api_jitter_is_smoothed(monkeypatch, test_services: dict[str, object]) -> None:
    client = _make_client(monkeypatch, test_services)
    timestamps = [
        "2026-03-23T21:30:00+08:00",
        "2026-03-23T21:30:10+08:00",
        "2026-03-23T21:30:20+08:00",
    ]
    scores: list[float] = []
    for index, timestamp in enumerate(timestamps):
        response = client.post(
            "/api/v1/health/score",
            json={
                "elderly_id": "E20001",
                "device_id": "BAND_JITTER",
                "timestamp": timestamp,
                "heart_rate": 101 if index == 1 else 99,
                "spo2": 97,
                "sbp": 122,
                "dbp": 80,
                "body_temp": 36.8,
                "fall_detection": False,
                "data_accuracy": 96,
            },
        )
        assert response.status_code == 200
        data = response.json()["data"]
        scores.append(float(data["health_score"]))
        assert data["active_events"] == []
        assert data["risk_level"] in {"normal", "attention"}

    assert max(scores) - min(scores) <= 6.0


def test_health_score_api_sustained_abnormal_event_aggregates(monkeypatch, test_services: dict[str, object]) -> None:
    client = _make_client(monkeypatch, test_services)
    timestamps = [
        "2026-03-23T21:30:00+08:00",
        "2026-03-23T21:30:15+08:00",
        "2026-03-23T21:30:30+08:00",
    ]
    final_data = None
    for timestamp in timestamps:
        response = client.post(
            "/api/v1/health/score",
            json={
                "elderly_id": "E30001",
                "device_id": "BAND_SPO2",
                "timestamp": timestamp,
                "heart_rate": 92,
                "spo2": 88,
                "sbp": 128,
                "dbp": 84,
                "body_temp": 36.8,
                "fall_detection": False,
                "data_accuracy": 95,
            },
        )
        assert response.status_code == 200
        final_data = response.json()["data"]

    assert final_data is not None
    assert any(event["event_type"] == "low_spo2" for event in final_data["active_events"])
    assert final_data["risk_level"] in {"warning", "critical"}
    assert "low_spo2" in final_data["abnormal_tags"]


def test_health_score_api_recovery_requires_more_than_one_point(monkeypatch, test_services: dict[str, object]) -> None:
    client = _make_client(monkeypatch, test_services)
    sequence = [
        ("2026-03-23T21:30:00+08:00", 88),
        ("2026-03-23T21:30:15+08:00", 88),
        ("2026-03-23T21:30:30+08:00", 88),
        ("2026-03-23T21:30:45+08:00", 92),
    ]
    final_data = None
    for timestamp, spo2 in sequence:
        response = client.post(
            "/api/v1/health/score",
            json={
                "elderly_id": "E35001",
                "device_id": "BAND_RECOVERY",
                "timestamp": timestamp,
                "heart_rate": 90,
                "spo2": spo2,
                "sbp": 126,
                "dbp": 84,
                "body_temp": 36.7,
                "fall_detection": False,
                "data_accuracy": 96,
            },
        )
        assert response.status_code == 200
        final_data = response.json()["data"]

    assert final_data is not None
    assert any(event["event_type"] == "low_spo2" for event in final_data["active_events"])


def test_health_score_api_severe_emergency_still_bypasses(monkeypatch, test_services: dict[str, object]) -> None:
    client = _make_client(monkeypatch, test_services)
    response = client.post(
        "/api/v1/health/score",
        json={
            "elderly_id": "E40001",
            "device_id": "BAND_EMERGENCY",
            "timestamp": "2026-03-23T21:30:00+08:00",
            "heart_rate": 142,
            "spo2": 96,
            "sbp": 121,
            "dbp": 79,
            "body_temp": 36.7,
            "fall_detection": False,
            "data_accuracy": 94,
        },
    )
    body = response.json()
    assert response.status_code == 200
    assert body["data"]["risk_level"] == "critical"
    assert "Heart rate above 140 bpm" in body["data"]["trigger_reasons"]
    assert body["data"]["score_adjustment_reason"] == "Immediate severe thresholds bypassed score damping."


def test_health_score_api_out_of_range(monkeypatch, test_services: dict[str, object]) -> None:
    client = _make_client(monkeypatch, test_services)
    response = client.post(
        "/api/v1/health/score",
        json={
            "elderly_id": "E99999",
            "device_id": "BAND_BAD",
            "timestamp": "2026-03-23T21:30:00+08:00",
            "heart_rate": 260,
            "spo2": 98,
            "sbp": 120,
            "dbp": 80,
            "body_temp": 36.6,
            "fall_detection": False,
            "data_accuracy": 99,
        },
    )
    body = response.json()
    assert response.status_code == 400
    assert body["code"] == "VALIDATION_ERROR"


def test_warning_check_and_explain_api(monkeypatch, test_services: dict[str, object]) -> None:
    client = _make_client(monkeypatch, test_services)
    warning_response = client.post(
        "/api/v1/health/warning/check",
        json={
            "window_data": [
                {
                    "timestamp": "2026-03-23T21:00:00+08:00",
                    "heart_rate": 80,
                    "spo2": 97,
                    "sbp": 118,
                    "dbp": 76,
                    "body_temp": 36.6,
                    "fall_detection": False,
                    "data_accuracy": 95,
                },
                {
                    "timestamp": "2026-03-23T21:00:15+08:00",
                    "heart_rate": 92,
                    "spo2": 88,
                    "sbp": 126,
                    "dbp": 84,
                    "body_temp": 36.8,
                    "fall_detection": False,
                    "data_accuracy": 95,
                },
                {
                    "timestamp": "2026-03-23T21:00:30+08:00",
                    "heart_rate": 94,
                    "spo2": 88,
                    "sbp": 128,
                    "dbp": 85,
                    "body_temp": 36.8,
                    "fall_detection": False,
                    "data_accuracy": 94,
                },
            ]
        },
    )
    assert warning_response.status_code == 200
    warning_body = warning_response.json()
    assert warning_body["data"]["window_mode"] == "event_aggregated_window"
    assert any(event["event_type"] == "low_spo2" for event in warning_body["data"]["active_events"])
    assert warning_body["data"]["risk_level"] in {"warning", "critical"}

    explain_response = client.post(
        "/api/v1/agent/health/explain",
        json={
            "role": "children",
            "health_result": {
                "elderly_id": "E10001",
                "device_id": "BAND_001",
                "timestamp": "2026-03-23T21:30:00+08:00",
                "health_score": 58.0,
                "final_health_score": 58.0,
                "rule_health_score": 66.0,
                "model_health_score": 46.0,
                "risk_level": "warning",
                "risk_score_raw": 0.54,
                "sub_scores": {"score_hr": 80.0, "score_spo2": 45.0, "score_bp": 50.0, "score_temp": 60.0},
                "alerts": {
                    "hr_alert": {"label": "High", "probability": 0.5},
                    "spo2_alert": {"label": "Low", "probability": 0.5},
                    "bp_alert": {"label": "High", "probability": 0.5},
                    "temp_alert": {"label": "Abnormal", "probability": 0.5},
                    "hard_threshold_level": "warning",
                },
                "abnormal_tags": ["low_spo2", "hypertension", "fever"],
                "trigger_reasons": ["Sustained SpO2 below 89%"],
                "recommendation_code": "RISK_OBSERVE_AND_NOTIFY",
                "stability_mode": "robust_demo",
                "stabilized_vitals": {
                    "heart_rate": 92,
                    "spo2": 88,
                    "sbp": 128,
                    "dbp": 84,
                    "body_temp": 36.8,
                    "fall_detection": False,
                    "data_accuracy": 95,
                },
                "active_events": [
                    {
                        "event_type": "low_spo2",
                        "severity": "warning",
                        "status": "active",
                        "start_time": "2026-03-23T21:29:40+08:00",
                        "last_seen_time": "2026-03-23T21:30:00+08:00",
                        "peak_value": 88,
                        "latest_value": 88,
                        "sample_count": 3,
                        "sustained_seconds": 20,
                        "trigger_reason": "Sustained SpO2 below 89%",
                    }
                ],
                "score_adjustment_reason": "Score drop capped at 6.0 points for jitter suppression.",
            },
        },
    )
    assert explain_response.status_code == 200
    explain_body = explain_response.json()
    assert explain_body["code"] == "OK"
    assert "风险等级" in explain_body["data"]["summary"]
    assert "稳定化" in explain_body["data"]["severity_explanation"]
