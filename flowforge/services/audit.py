"""Audit log helper. Every mutation in the system should call into here."""

from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from flowforge.models.audit import AuditLog


def record(
    session: Session,
    *,
    action: str,
    actor_id: Optional[str] = None,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> AuditLog:
    entry = AuditLog(
        action=action,
        actor_id=actor_id,
        target_type=target_type,
        target_id=target_id,
        payload=payload or {},
    )
    session.add(entry)
    session.flush()
    return entry
