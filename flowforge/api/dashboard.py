"""Scheduler + audit + dashboard endpoints."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from flowforge.api.deps import get_current_user
from flowforge.api.schemas import AuditOut
from flowforge.core.database import get_db
from flowforge.models.audit import AuditLog
from flowforge.models.run import Run, RunStatus
from flowforge.models.user import User
from flowforge.models.workflow import Workflow
from flowforge.services.scheduler import list_schedules

router = APIRouter(prefix="/api/v1", tags=["dashboard"])


@router.get("/schedules")
def schedules(current_user: User = Depends(get_current_user)):
    return list_schedules()


@router.get("/audit", response_model=List[AuditOut])
def list_audit(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    action: Optional[str] = None,
    target_type: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
) -> List[AuditLog]:
    q = db.query(AuditLog).filter(AuditLog.actor_id == current_user.id)
    if action:
        q = q.filter(AuditLog.action == action)
    if target_type:
        q = q.filter(AuditLog.target_type == target_type)
    return q.order_by(AuditLog.created_at.desc()).limit(limit).all()


@router.get("/dashboard")
def dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Aggregated metrics for the dashboard UI."""
    workflows_total = (
        db.query(func.count(Workflow.id)).filter(Workflow.owner_id == current_user.id).scalar() or 0
    )
    active_workflows = (
        db.query(func.count(Workflow.id))
        .filter(Workflow.owner_id == current_user.id, Workflow.is_active.is_(True))
        .scalar()
        or 0
    )
    runs_total = (
        db.query(func.count(Run.id)).join(Run.workflow).filter(Run.workflow.has(owner_id=current_user.id)).scalar() or 0
    )
    runs_succeeded = (
        db.query(func.count(Run.id))
        .join(Run.workflow)
        .filter(Run.workflow.has(owner_id=current_user.id), Run.status == RunStatus.SUCCEEDED)
        .scalar()
        or 0
    )
    runs_failed = (
        db.query(func.count(Run.id))
        .join(Run.workflow)
        .filter(Run.workflow.has(owner_id=current_user.id), Run.status == RunStatus.FAILED)
        .scalar()
        or 0
    )
    return {
        "workflows": {"total": workflows_total, "active": active_workflows},
        "runs": {
            "total": runs_total,
            "succeeded": runs_succeeded,
            "failed": runs_failed,
            "success_rate": round((runs_succeeded / runs_total * 100) if runs_total else 0.0, 2),
        },
        "schedules": list_schedules(),
    }
