"""Workflow definition model.

A workflow is an ordered list of steps, each of which is executed by a
pluggable step runner. Steps reference integrations by name and pass
JSON-shaped config that the runner knows how to interpret.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from flowforge.core.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Trigger: "manual" | "schedule" | "webhook" | "etl"
    trigger: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    # Optional cron-like schedule string (5-field or 6-field).
    schedule: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    # Steps: list of {id, name, type, config, next?}
    definition: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    owner = relationship("User", back_populates="workflows")
    runs = relationship("Run", back_populates="workflow", cascade="all, delete-orphan")

    def step_list(self) -> List[Dict[str, Any]]:
        steps = self.definition.get("steps", []) if isinstance(self.definition, dict) else []
        if not isinstance(steps, list):
            return []
        return steps
