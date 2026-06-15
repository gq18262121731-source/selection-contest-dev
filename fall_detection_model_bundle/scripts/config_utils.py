from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: str | Path) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    if not config_path.exists():
        return {}
    return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}


def resolve_project_path(path_value: str | None) -> Path | None:
    if not path_value:
        return None
    path = Path(path_value)
    if path.is_absolute():
        return path
    return ROOT / path


def existing_model_path(entry: dict[str, Any]) -> Path | None:
    primary = resolve_project_path(entry.get("path"))
    if primary is not None and primary.exists():
        return primary
    fallback = resolve_project_path(entry.get("fallback_path"))
    if fallback is not None and fallback.exists():
        return fallback
    if primary is not None and not primary.is_absolute() and entry.get("path"):
        return Path(str(entry["path"]))
    return primary


def get_profile(registry: dict[str, Any], profile_name: str | None) -> dict[str, Any]:
    profiles = registry.get("profiles", {})
    name = profile_name or registry.get("default_profile")
    if name in profiles:
        return profiles[name]
    if profiles:
        return next(iter(profiles.values()))
    return {}
