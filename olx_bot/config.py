import os

import yaml


def _deep_merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: str) -> dict:
    """Loads local secrets from `path` (gitignored -- just Gmail
    credentials, plus any local overrides) and merges them over
    settings.yaml (tracked in git, alongside `path`) if one exists, so
    every non-secret tuning knob (prices, models, URLs) ships via a
    normal `git pull` instead of a manual edit on the deployment
    machine. Values in `path` win on conflict.
    """
    with open(path, "r", encoding="utf-8") as f:
        secrets = yaml.safe_load(f) or {}

    settings_path = os.path.join(os.path.dirname(path) or ".", "settings.yaml")
    if os.path.exists(settings_path):
        with open(settings_path, "r", encoding="utf-8") as f:
            settings = yaml.safe_load(f) or {}
        return _deep_merge(settings, secrets)

    return secrets
