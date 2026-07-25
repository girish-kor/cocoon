"""Config resolution. Authoritative source: DOCUMENT.md §8.1, §16, §18.

Precedence (lowest → highest): schema defaults < config/base.yaml <
config/profiles/<profile>.yaml < COCOON_* environment variables. The CLI
layer applies per-invocation flag overrides (e.g. --log-level) after
`resolve()` returns, which keeps this module free of any typer dependency.

Secrets must never live in config files (§8.1: credentials come from the
environment only). File-backed sources are scanned for secret-like key
names before merging and resolution fails with exit 11 if one is found —
env-sourced values are exempt because the environment IS the sanctioned
secret channel.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from cocoon.core.config.schema import ConfigModel
from cocoon.core.errors.exceptions import (
    ConfigValidationError,
    SecretInConfigFileError,
)

ENV_PREFIX = "COCOON_"
ENV_NESTED_DELIMITER = "__"

_SECRET_KEY_MARKERS = (
    "password",
    "passwd",
    "secret",
    "api_key",
    "apikey",
    "token",
    "private_key",
)


@dataclass(frozen=True)
class ConfigSource:
    """One layer of the precedence chain. `origin` names where the data
    came from (file path, "env", "defaults") for error context; only
    file-backed sources are secret-scanned."""

    origin: str
    data: dict[str, Any] = field(default_factory=dict)
    from_file: bool = False


def _load_yaml_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigValidationError(
            "Config file is not valid YAML",
            context={"path": str(path), "error": str(exc)},
        ) from exc
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ConfigValidationError(
            "Config file must contain a mapping at the top level",
            context={"path": str(path), "found": type(raw).__name__},
        )
    return raw


def _coerce_env_value(raw: str) -> Any:
    try:
        return yaml.safe_load(raw)
    except yaml.YAMLError:
        return raw


def _env_overrides(environ: dict[str, str]) -> dict[str, Any]:
    """COCOON_RISK__MAX_DAILY_LOSS_PCT=1.0 → {"risk": {"max_daily_loss_pct": 1.0}}."""
    data: dict[str, Any] = {}
    for key, raw in environ.items():
        if not key.startswith(ENV_PREFIX):
            continue
        dot_path = key[len(ENV_PREFIX):].lower()
        parts = [p for p in dot_path.split(ENV_NESTED_DELIMITER) if p]
        if not parts:
            continue
        cursor = data
        for part in parts[:-1]:
            nxt = cursor.setdefault(part, {})
            if not isinstance(nxt, dict):
                nxt = {}
                cursor[part] = nxt
            cursor = nxt
        cursor[parts[-1]] = _coerce_env_value(raw)
    return data


def _scan_for_secrets(data: Any, origin: str, path: str = "") -> None:
    if isinstance(data, dict):
        for key, value in data.items():
            key_path = f"{path}.{key}" if path else str(key)
            lowered = str(key).lower()
            if any(marker in lowered for marker in _SECRET_KEY_MARKERS):
                raise SecretInConfigFileError(
                    "Config file contains a secret-like key; credentials must "
                    "come from environment variables, never config files",
                    context={"key": key_path, "file": origin},
                )
            _scan_for_secrets(value, origin, key_path)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            _scan_for_secrets(item, origin, f"{path}[{i}]")


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def default_sources(
    *,
    profile: str = "default",
    config_dir: str = "./config",
    environ: dict[str, str] | None = None,
) -> list[ConfigSource]:
    root = Path(config_dir)
    base_path = root / "base.yaml"
    profile_path = root / "profiles" / f"{profile}.yaml"
    env = environ if environ is not None else dict(os.environ)
    return [
        ConfigSource(origin="defaults"),
        ConfigSource(
            origin=str(base_path), data=_load_yaml_file(base_path), from_file=True
        ),
        ConfigSource(
            origin=str(profile_path),
            data=_load_yaml_file(profile_path),
            from_file=True,
        ),
        ConfigSource(origin="env", data=_env_overrides(env)),
    ]


def resolve(sources: list[ConfigSource]) -> ConfigModel:
    merged: dict[str, Any] = {}
    for source in sources:
        if source.from_file:
            _scan_for_secrets(source.data, source.origin)
        merged = _deep_merge(merged, source.data)
    try:
        return ConfigModel.model_validate(merged)
    except ValidationError as exc:
        raise ConfigValidationError(
            "Config failed schema validation",
            context={
                "sources": [s.origin for s in sources],
                "errors": [
                    {
                        "loc": ".".join(str(p) for p in err["loc"]),
                        "msg": err["msg"],
                    }
                    for err in exc.errors()
                ],
            },
        ) from exc
