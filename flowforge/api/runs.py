"""Run history endpoints (read-only)."""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from flowforge.api.deps import get_current_user
from flowforge.api.schemas import RunOut
from flowforge.core.database import get_db
from flowforge.models.run import Run
from flowforge.models.user import User

router = APIRouter(prefix="/api/v1/runs", tags=["runs"])


@router.get("", response_model=List[RunOut])
def list_runs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    status: Optional[str] = None,
    workflow_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> List[Run]:
    q = db.query(Run).join(Run.workflow).filter(Run.workflow.has(owner_id=current_user.id))
    if status:
        q = q.filter(Run.status == status)
    if workflow_id:
        q = q.filter(Run.workflow_id == workflow_id)
    return q.order_by(Run.created_at.desc()).offset(offset).limit(limit).all()


@router.get("/{run_id}", response_model=RunOut)
def get_run(
    run_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Run:
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    if run.workflow.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="run not found")
    return run
