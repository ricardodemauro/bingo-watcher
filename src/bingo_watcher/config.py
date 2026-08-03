"""Typed settings loaded from the YAML config file and .env secrets."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import dotenv_values
from pydantic import BaseModel, ValidationError, field_validator

DEFAULT_CONFIG_PATH = Path("config.yaml")
DEFAULT_ENV_PATH = Path(".env")

_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_SECRET_KEYS = (
    "alpaca_api_key",
    "alpaca_secret_key",
    "telegram_bot_token",
    "telegram_chat_id",
)


class ConfigError(Exception):
    """Missing or invalid configuration. Message is safe to show the user directly."""


class Settings(BaseModel):
    watchlist: list[str]
    multiplier: float
    evaluation_interval_seconds: int = 300
    log_level: str = "INFO"
    database_path: Path = Path("data/bingo_watcher.sqlite3")

    alpaca_api_key: str
    alpaca_secret_key: str
    telegram_bot_token: str
    telegram_chat_id: str

    @field_validator("watchlist")
    @classmethod
    def _normalize_watchlist(cls, value: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(t.strip().upper() for t in value if t and t.strip()))
        if not cleaned:
            raise ValueError("must contain at least one ticker")
        return cleaned

    @field_validator("multiplier")
    @classmethod
    def _positive_multiplier(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("must be a positive number")
        return value

    @field_validator("evaluation_interval_seconds")
    @classmethod
    def _positive_interval(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("must be a positive number of seconds")
        return value

    @field_validator("log_level")
    @classmethod
    def _known_log_level(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in _VALID_LOG_LEVELS:
            raise ValueError(f"must be one of {sorted(_VALID_LOG_LEVELS)}")
        return normalized


def load_settings(
    config_path: Path = DEFAULT_CONFIG_PATH,
    env_path: Path = DEFAULT_ENV_PATH,
) -> Settings:
    """Load and validate settings from `config_path` (YAML) and `env_path` (.env secrets).

    Real environment variables take precedence over values in `env_path`, so
    secrets can also be injected without a file (e.g. in a container).
    """
    if not config_path.exists():
        raise ConfigError(
            f"Config file not found: {config_path}. "
            f"Copy config.example.yaml to {config_path.name} and fill it in."
        )
    try:
        yaml_data = yaml.safe_load(config_path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"Config file {config_path} is not valid YAML: {exc}") from exc
    if not isinstance(yaml_data, dict):
        raise ConfigError(f"Config file {config_path} must contain a YAML mapping at the top level")

    secrets = _load_secrets(env_path)

    try:
        return Settings(**yaml_data, **secrets)
    except ValidationError as exc:
        raise ConfigError(_format_validation_error(config_path, env_path, exc)) from exc


def _load_secrets(env_path: Path) -> dict[str, str]:
    file_values = dotenv_values(env_path) if env_path.exists() else {}
    secrets: dict[str, str] = {}
    for key in _SECRET_KEYS:
        value = os.environ.get(key.upper(), file_values.get(key.upper()))
        if value:
            secrets[key] = value
    return secrets


def _format_validation_error(config_path: Path, env_path: Path, exc: ValidationError) -> str:
    problems = "; ".join(
        f"{'.'.join(str(part) for part in err['loc'])}: {err['msg']}" for err in exc.errors()
    )
    return (
        f"Invalid configuration (checked {config_path} and {env_path}): {problems}"
    )
