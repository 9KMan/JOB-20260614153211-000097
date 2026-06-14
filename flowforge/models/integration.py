"""Integration credentials and connection metadata.

Integrations are named, reusable connection records. Workflow steps
reference them by name rather than embedding secrets.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from flowforge.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IntegrationKind(str, enum.Enum):
    HTTP = "http"
    EMAIL = "email"
    SLACK = "slack"
    DATABASE = "database"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    FILE = "file"


class Integration(Base):
    __tablename__ = "integrations"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_integration_owner_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    kind: Mapped[IntegrationKind] = mapped_column(String(32), nullable=False, index=True)
    # Non-secret config. Secrets live under `secret` and are
    # stored as-is for the PoC. In production, encrypt at rest.
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    secret: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
