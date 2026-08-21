from __future__ import annotations

from typing import Mapping

import pandas as pd


FEATURE_COLUMNS: list[str] = [
    "heart_rate",
    "spo2",
    "sbp",
    "dbp",
    "body_temp",
    "fall_detection",
    "data_accuracy",
    "pulse_pressure",
    "map_pressure",
    "hr_spo2_ratio",
    "temp_hr_interaction",
    "bp_level_score",
    "low_spo2_flag",
    "high_hr_flag",
    "fever_flag",
    "hypertension_flag",
    "fall_flag",
    "quality_weight",
]


def build_feature_frame(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Build feature matrix for training or inference."""

    frame = dataframe.copy()
    frame["pulse_pressure"] = frame["sbp"] - frame["dbp"]
    frame["map_pressure"] = frame["dbp"] + (frame["pulse_pressure"] / 3.0)
    frame["hr_spo2_ratio"] = frame["heart_rate"] / frame["spo2"].clip(lower=1.0)
    frame["temp_hr_interaction"] = frame["body_temp"] * frame["heart_rate"]
    frame["bp_level_score"] = 0.6 * frame["sbp"] + 0.4 * frame["dbp"]
    frame["low_spo2_flag"] = (frame["spo2"] < 90).astype(float)
    frame["high_hr_flag"] = (frame["heart_rate"] > 100).astype(float)
    frame["fever_flag"] = (frame["body_temp"] >= 37.3).astype(float)
    frame["hypertension_flag"] = ((frame["sbp"] >= 140) | (frame["dbp"] >= 90)).astype(float)
    frame["fall_flag"] = frame["fall_detection"].astype(float)
    frame["quality_weight"] = frame["data_accuracy"] / 100.0
    return frame.loc[:, FEATURE_COLUMNS].astype(float)


def build_single_feature_frame(record: Mapping[str, float | int]) -> pd.DataFrame:
    """Build a single-row feature frame for realtime inference."""

    return build_feature_frame(pd.DataFrame([record]))
