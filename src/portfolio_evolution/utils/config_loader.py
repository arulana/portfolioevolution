"""YAML config loading with preset inheritance and Pydantic validation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Load a YAML file and return as dict."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        return {}
    return data


def deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base. Override wins on conflicts."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config_with_preset(
    config_path: str | Path,
    preset_name: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load master config, optionally merging a preset and CLI overrides.

    Layering order (later wins):
    1. Preset defaults (if preset_name provided)
    2. Master config values
    3. CLI overrides (if provided)
    """
    config = load_yaml(config_path)

    if preset_name:
        config_dir = Path(config_path).parent
        preset_path = config_dir / "presets" / f"{preset_name}.yaml"
        if not preset_path.exists():
            raise FileNotFoundError(
                f"Preset '{preset_name}' not found at {preset_path}. "
                f"Available presets: {list_presets(config_dir / 'presets')}"
            )
        preset = load_yaml(preset_path)
        config = deep_merge(preset, config)

    if overrides:
        config = deep_merge(config, overrides)

    return config


def list_presets(presets_dir: str | Path) -> list[str]:
    """List available preset names."""
    presets_dir = Path(presets_dir)
    if not presets_dir.exists():
        return []
    return [p.stem for p in presets_dir.glob("*.yaml")]


def load_lookup(path: str | Path) -> dict[str, str]:
    """Load a lookup crosswalk YAML and return the forward mapping."""
    data = load_yaml(path)
    return data.get("forward", {})
