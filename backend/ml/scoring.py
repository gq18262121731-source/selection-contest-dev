from __future__ import annotations


def clamp_score(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    """Clamp score to an inclusive range."""

    return max(minimum, min(maximum, float(value)))


def risk_raw_to_health_score(risk_score_raw: float) -> float:
    """Convert model risk raw score into a 0-100 health score."""

    return clamp_score(100.0 * (1.0 - float(risk_score_raw)))


def fuse_health_scores(
    rule_health_score: float,
    model_health_score: float,
    rule_weight: float = 0.6,
    model_weight: float = 0.4,
) -> float:
    """Fuse rule and model health scores."""

    return clamp_score((rule_weight * float(rule_health_score)) + (model_weight * float(model_health_score)))
