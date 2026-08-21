from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from backend.logger import get_logger


LOGGER = get_logger(__name__)

RAW_COLUMN_MAPPING: dict[str, str] = {
    "Patient Number": "patient_id",
    "Heart Rate (bpm)": "heart_rate",
    "SpO2 Level (%)": "spo2",
    "Systolic Blood Pressure (mmHg)": "sbp",
    "Diastolic Blood Pressure (mmHg)": "dbp",
    "Body Temperature (°C)": "body_temp",
    "Fall Detection": "fall_detection",
    "Predicted Disease": "predicted_disease",
    "Data Accuracy (%)": "data_accuracy",
    "Heart Rate Alert": "hr_alert",
    "SpO2 Level Alert": "spo2_alert",
    "Blood Pressure Alert": "bp_alert",
    "Temperature Alert": "temp_alert",
}

STANDARD_COLUMNS: tuple[str, ...] = tuple(RAW_COLUMN_MAPPING.values())
CORE_VITAL_COLUMNS: tuple[str, ...] = ("heart_rate", "spo2", "sbp", "dbp", "body_temp")
NUMERIC_COLUMNS: tuple[str, ...] = (*CORE_VITAL_COLUMNS, "data_accuracy")
ALERT_COLUMNS: tuple[str, ...] = ("hr_alert", "spo2_alert", "bp_alert", "temp_alert")

VALUE_RANGES: dict[str, tuple[float, float]] = {
    "heart_rate": (30.0, 220.0),
    "spo2": (50.0, 100.0),
    "sbp": (70.0, 250.0),
    "dbp": (40.0, 150.0),
    "body_temp": (34.0, 42.0),
    "data_accuracy": (0.0, 100.0),
}


class DataValidationError(ValueError):
    """Raised when realtime inference input is invalid."""


@dataclass(slots=True)
class PreprocessStats:
    total_rows: int
    valid_rows: int
    dropped_rows: int
    missing_core_rows: int
    out_of_range_rows: int
    label_distribution: dict[str, dict[str, int]]


def _normalize_yes_no(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(float(value) > 0)
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "fall", "detected"}:
        return 1
    if normalized in {"0", "false", "no", "n", "", "none", "normal"}:
        return 0
    return 1 if normalized else 0


def _normalize_alert_label(value: Any, positive_keywords: set[str]) -> int:
    if isinstance(value, (int, float)):
        return int(float(value) > 0)
    normalized = str(value).strip().lower()
    if normalized in {"0", "normal", "ok", "none", "false", ""}:
        return 0
    if normalized in {"1", "true"}:
        return 1
    return int(any(keyword in normalized for keyword in positive_keywords))


def load_health_excel(path: str | Path, sheet_name: str | int | None = None) -> pd.DataFrame:
    """Load raw Excel health data."""

    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"Excel data file not found: {source}")
    resolved_sheet: str | int = 0 if sheet_name in (None, "") else sheet_name
    return pd.read_excel(source, sheet_name=resolved_sheet)


def clean_health_dataframe(dataframe: pd.DataFrame) -> tuple[pd.DataFrame, PreprocessStats]:
    """Rename, validate and encode the Excel dataset for model training."""

    renamed = dataframe.rename(columns=RAW_COLUMN_MAPPING).copy()
    missing_columns = [column for column in STANDARD_COLUMNS if column not in renamed.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")

    cleaned = renamed.loc[:, STANDARD_COLUMNS].copy()
    cleaned["patient_id"] = cleaned["patient_id"].astype(str).str.strip()
    cleaned["predicted_disease"] = cleaned["predicted_disease"].fillna("unknown").astype(str).str.strip()
    cleaned["data_accuracy"] = cleaned["data_accuracy"].fillna(100.0)

    for column in NUMERIC_COLUMNS:
        cleaned[column] = pd.to_numeric(cleaned[column], errors="coerce")

    cleaned["fall_detection"] = cleaned["fall_detection"].apply(_normalize_yes_no)
    cleaned["hr_alert"] = cleaned["hr_alert"].apply(_normalize_alert_label, positive_keywords={"high", "abnormal", "alert", "warning", "tachy"})
    cleaned["spo2_alert"] = cleaned["spo2_alert"].apply(_normalize_alert_label, positive_keywords={"low", "abnormal", "alert", "warning", "critical"})
    cleaned["bp_alert"] = cleaned["bp_alert"].apply(_normalize_alert_label, positive_keywords={"high", "abnormal", "alert", "warning", "hyper"})
    cleaned["temp_alert"] = cleaned["temp_alert"].apply(_normalize_alert_label, positive_keywords={"abnormal", "high", "fever", "alert", "warning"})

    total_rows = len(cleaned)
    missing_core_mask = cleaned.loc[:, CORE_VITAL_COLUMNS].isna().any(axis=1)
    out_of_range_mask = pd.Series(False, index=cleaned.index)
    for column, (minimum, maximum) in VALUE_RANGES.items():
        column_mask = cleaned[column].notna() & ~cleaned[column].between(minimum, maximum)
        out_of_range_mask = out_of_range_mask | column_mask

    invalid_mask = missing_core_mask | out_of_range_mask
    valid = cleaned.loc[~invalid_mask].copy()

    label_distribution = {
        column: {str(key): int(value) for key, value in valid[column].value_counts(dropna=False).sort_index().items()}
        for column in ALERT_COLUMNS
    }
    stats = PreprocessStats(
        total_rows=total_rows,
        valid_rows=len(valid),
        dropped_rows=int(invalid_mask.sum()),
        missing_core_rows=int(missing_core_mask.sum()),
        out_of_range_rows=int(out_of_range_mask.sum()),
        label_distribution=label_distribution,
    )
    LOGGER.info(
        "Health dataset cleaned: total=%s valid=%s dropped=%s missing_core=%s out_of_range=%s",
        stats.total_rows,
        stats.valid_rows,
        stats.dropped_rows,
        stats.missing_core_rows,
        stats.out_of_range_rows,
    )
    for column, distribution in stats.label_distribution.items():
        LOGGER.info("Label distribution for %s: %s", column, distribution)

    return valid.reset_index(drop=True), stats


def validate_inference_record(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize a realtime inference record."""

    normalized = {
        "heart_rate": float(payload["heart_rate"]),
        "spo2": float(payload["spo2"]),
        "sbp": float(payload["sbp"]),
        "dbp": float(payload["dbp"]),
        "body_temp": float(payload["body_temp"]),
        "fall_detection": _normalize_yes_no(payload.get("fall_detection", 0)),
        "data_accuracy": float(payload.get("data_accuracy", 100.0) or 100.0),
    }
    for column, (minimum, maximum) in VALUE_RANGES.items():
        value = normalized[column]
        if value < minimum or value > maximum:
            raise DataValidationError(f"{column} is out of range [{minimum}, {maximum}]")
    return normalized
