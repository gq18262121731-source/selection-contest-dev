from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.config import get_settings


def _write_test_artifacts(base_dir: Path) -> tuple[str, str, str]:
    import joblib
    import numpy as np
    import pandas as pd
    import torch
    from sklearn.preprocessing import StandardScaler

    from backend.ml.feature_engineering import FEATURE_COLUMNS
    from backend.models.static_health_model import StaticHealthMultiTaskModel

    artifact_dir = base_dir / "artifacts" / "static_health"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    scaler = StandardScaler()
    scaler.fit(
        pd.DataFrame(
            np.vstack([np.zeros(len(FEATURE_COLUMNS)), np.ones(len(FEATURE_COLUMNS))]),
            columns=FEATURE_COLUMNS,
        )
    )
    scaler_path = artifact_dir / "feature_scaler.joblib"
    joblib.dump(scaler, scaler_path)

    feature_columns_path = artifact_dir / "feature_columns.json"
    feature_columns_path.write_text(json.dumps(FEATURE_COLUMNS, ensure_ascii=False, indent=2), encoding="utf-8")

    model = StaticHealthMultiTaskModel(input_dim=len(FEATURE_COLUMNS))
    for parameter in model.parameters():
        parameter.data.zero_()
    model_path = artifact_dir / "static_health_model.pt"
    model.save(model_path)
    return str(model_path), str(scaler_path), str(feature_columns_path)


@pytest.fixture()
def test_services(tmp_path: Path) -> dict[str, object]:
    from backend.ml.inference import HealthInferenceEngine
    from backend.repositories.score_repo import ScoreRepository
    from backend.repositories.warning_repo import WarningRepository
    from backend.repositories.wearable_repo import WearableRepository
    from backend.services.explanation_service import ExplanationService
    from backend.services.health_score_service import HealthScoreService
    from backend.services.health_stability_service import HealthStabilityService
    from backend.services.warning_service import WarningService

    model_path, scaler_path, feature_columns_path = _write_test_artifacts(tmp_path)
    settings = get_settings().model_copy(
        update={
            "database_url": f"sqlite+aiosqlite:///{(tmp_path / 'test.db').as_posix()}",
            "static_model_dir": str(tmp_path / "artifacts" / "static_health"),
            "static_model_path": model_path,
            "static_scaler_path": scaler_path,
            "static_feature_columns_path": feature_columns_path,
            "allow_rule_only_fallback": False,
        }
    )
    inference = HealthInferenceEngine(settings=settings)
    wearable_repo = WearableRepository(database_url=settings.database_url)
    score_repo = ScoreRepository(database_url=settings.database_url)
    warning_repo = WarningRepository(database_url=settings.database_url)
    stability_service = HealthStabilityService(settings=settings)
    score_service = HealthScoreService(
        inference_engine=inference,
        wearable_repo=wearable_repo,
        score_repo=score_repo,
        warning_repo=warning_repo,
        stability_service=stability_service,
    )
    warning_service = WarningService(health_score_service=score_service)
    explanation_service = ExplanationService()
    return {
        "settings": settings,
        "inference": inference,
        "score_service": score_service,
        "warning_service": warning_service,
        "explanation_service": explanation_service,
    }
