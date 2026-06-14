"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from functools import lru_cache
from typing import List


def _env(name: str, default: str | None = None) -> str | None:
    val = os.environ.get(name)
    if val is None or val == "":
        return default
    return val


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_list(name: str, default: List[str]) -> List[str]:
    raw = _env(name)
    if raw is None:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    app_name: str = field(default_factory=lambda: _env("APP_NAME", "FlowForge") or "FlowForge")
    environment: str = field(default_factory=lambda: _env("ENV", "development") or "development")
    debug: bool = field(default_factory=lambda: _env_bool("DEBUG", True))
    host: str = field(default_factory=lambda: _env("HOST", "0.0.0.0") or "0.0.0.0")
    port: int = field(default_factory=lambda: _env_int("PORT", 8000))

    database_url: str = field(
        default_factory=lambda: _env("DATABASE_URL", "sqlite:///./flowforge.db") or "sqlite:///./flowforge.db"
    )

    jwt_secret: str = field(
        default_factory=lambda: _env("JWT_SECRET", "dev-secret-change-me-please-use-32-bytes-min") or "dev-secret-change-me-please-use-32-bytes-min"
    )
    jwt_algorithm: str = field(default_factory=lambda: _env("JWT_ALGORITHM", "HS256") or "HS256")
    jwt_expiration_minutes: int = field(default_factory=lambda: _env_int("JWT_EXPIRATION_MINUTES", 60 * 8))

    cors_origins: List[str] = field(
        default_factory=lambda: _env_list("CORS_ORIGINS", ["http://localhost:3000", "http://localhost:8000"])
    )

    # LLM provider config. Stub is the safe default; the LLM service is
    # pluggable so OpenAI / Anthropic / local can be wired in via env.
    llm_provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "stub") or "stub")
    llm_api_key: str = field(default_factory=lambda: _env("LLM_API_KEY", "") or "")
    llm_default_model: str = field(default_factory=lambda: _env("LLM_DEFAULT_MODEL", "stub-1") or "stub-1")
    llm_openai_model: str = field(default_factory=lambda: _env("LLM_OPENAI_MODEL", "gpt-4o-mini") or "gpt-4o-mini")
    llm_anthropic_model: str = field(
        default_factory=lambda: _env("LLM_ANTHROPIC_MODEL", "claude-3-5-sonnet-20240620") or "claude-3-5-sonnet-20240620"
    )

    # Workflow engine settings
    max_concurrent_runs: int = field(default_factory=lambda: _env_int("MAX_CONCURRENT_RUNS", 4))
    step_timeout_seconds: int = field(default_factory=lambda: _env_int("STEP_TIMEOUT_SECONDS", 60))

    # Integrations
    smtp_host: str = field(default_factory=lambda: _env("SMTP_HOST", "") or "")
    smtp_port: int = field(default_factory=lambda: _env_int("SMTP_PORT", 587))
    smtp_user: str = field(default_factory=lambda: _env("SMTP_USER", "") or "")
    smtp_password: str = field(default_factory=lambda: _env("SMTP_PASSWORD", "") or "")
    smtp_from: str = field(default_factory=lambda: _env("SMTP_FROM", "[email protected]") or "[email protected]")

    slack_webhook_url: str = field(default_factory=lambda: _env("SLACK_WEBHOOK_URL", "") or "")

    audit_log_retention_days: int = field(default_factory=lambda: _env_int("AUDIT_LOG_RETENTION_DAYS", 90))

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    def rotate_jwt_secret(self) -> str:
        return secrets.token_urlsafe(48)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
