"""Workflow CRUD + run + webhook endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from flowforge.api.deps import get_current_user
from flowforge.api.schemas import (
    RunOut,
    RunTriggerRequest,
    WorkflowCreate,
    WorkflowOut,
    WorkflowUpdate,
)
from flowforge.core.database import get_db
from flowforge.models.run import Run, RunStatus
from flowforge.models.user import User
from flowforge.models.workflow import Workflow
from flowforge.services import audit
from flowforge.services.scheduler import schedule_workflow, unschedule_workflow
from flowforge.services.workflow_engine import execute_run_sync

router = APIRouter(prefix="/api/v1/workflows", tags=["workflows"])


def _validate_definition(definition: Any) -> Dict[str, Any]:
    if not isinstance(definition, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="definition must be an object")
    steps = definition.get("steps")
    if not isinstance(steps, list):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="definition.steps must be a list")
    seen: set[str] = set()
    for step in steps:
        if not isinstance(step, dict):
            raise HTTPException(status_code=400, detail="each step must be an object")
        sid = step.get("id")
        if not sid or not isinstance(sid, str):
            raise HTTPException(status_code=400, detail="step.id is required (string)")
        if sid in seen:
            raise HTTPException(status_code=400, detail=f"duplicate step id: {sid}")
        seen.add(sid)
        if not step.get("type"):
            raise HTTPException(status_code=400, detail=f"step {sid}: type is required")
    return definition


@router.post("", response_model=WorkflowOut, status_code=status.HTTP_201_CREATED)
def create_workflow(
    payload: WorkflowCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Workflow:
    definition = _validate_definition(payload.definition.model_dump())
    workflow = Workflow(
        name=payload.name,
        description=payload.description,
        trigger=payload.trigger,
        schedule=payload.schedule,
        definition=definition,
        owner_id=current_user.id,
    )
    db.add(workflow)
    db.flush()
    audit.record(
        db,
        action="workflow.create",
        actor_id=current_user.id,
        target_type="workflow",
        target_id=workflow.id,
        payload={"name": workflow.name, "trigger": workflow.trigger, "steps": len(definition.get("steps", []))},
    )
    db.commit()
    db.refresh(workflow)
    if workflow.trigger == "schedule" and workflow.schedule:
        schedule_workflow(workflow)
    return workflow


@router.get("", response_model=List[WorkflowOut])
def list_workflows(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    trigger: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> List[Workflow]:
    q = db.query(Workflow).filter(Workflow.owner_id == current_user.id)
    if trigger:
        q = q.filter(Workflow.trigger == trigger)
    if is_active is not None:
        q = q.filter(Workflow.is_active == is_active)
    return q.order_by(Workflow.created_at.desc()).offset(offset).limit(limit).all()


@router.get("/{workflow_id}", response_model=WorkflowOut)
def get_workflow(
    workflow_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Workflow:
    workflow = db.get(Workflow, workflow_id)
    if not workflow or workflow.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="workflow not found")
    return workflow


@router.patch("/{workflow_id}", response_model=WorkflowOut)
def update_workflow(
    workflow_id: str,
    payload: WorkflowUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Workflow:
    workflow = db.get(Workflow, workflow_id)
    if not workflow or workflow.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="workflow not found")
    if payload.name is not None:
        workflow.name = payload.name
    if payload.description is not None:
        workflow.description = payload.description
    if payload.trigger is not None:
        workflow.trigger = payload.trigger
    if payload.schedule is not None:
        workflow.schedule = payload.schedule
    if payload.is_active is not None:
        workflow.is_active = payload.is_active
    if payload.definition is not None:
        workflow.definition = _validate_definition(payload.definition.model_dump())
    db.flush()
    audit.record(
        db,
        action="workflow.update",
        actor_id=current_user.id,
        target_type="workflow",
        target_id=workflow.id,
        payload={"is_active": workflow.is_active, "trigger": workflow.trigger},
    )
    db.commit()
    db.refresh(workflow)
    if workflow.trigger == "schedule":
        if workflow.is_active and workflow.schedule:
            schedule_workflow(workflow)
        else:
            unschedule_workflow(workflow.id)
    return workflow


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workflow(
    workflow_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    workflow = db.get(Workflow, workflow_id)
    if not workflow or workflow.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="workflow not found")
    unschedule_workflow(workflow.id)
    audit.record(
        db,
        action="workflow.delete",
        actor_id=current_user.id,
        target_type="workflow",
        target_id=workflow.id,
    )
    db.delete(workflow)
    db.commit()


# ---------- Runs ----------


@router.post("/{workflow_id}/run", response_model=RunOut, status_code=status.HTTP_201_CREATED)
def trigger_run(
    workflow_id: str,
    payload: RunTriggerRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Run:
    workflow = db.get(Workflow, workflow_id)
    if not workflow or workflow.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="workflow not found")
    if not workflow.is_active:
        raise HTTPException(status_code=400, detail="workflow is inactive")
    run = Run(workflow_id=workflow.id, trigger="manual", context=payload.payload or {})
    db.add(run)
    db.flush()
    try:
        execute_run_sync(db, run=run, workflow=workflow, trigger_payload=payload.payload or {})
    except Exception as exc:  # noqa: BLE001
        run.status = RunStatus.FAILED
        run.error = str(exc)
    db.commit()
    db.refresh(run)
    return run


@router.get("/{workflow_id}/runs", response_model=List[RunOut])
def list_runs(
    workflow_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> List[Run]:
    workflow = db.get(Workflow, workflow_id)
    if not workflow or workflow.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="workflow not found")
    return (
        db.query(Run)
        .filter(Run.workflow_id == workflow.id)
        .order_by(Run.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.post("/{workflow_id}/webhook", response_model=RunOut, status_code=status.HTTP_201_CREATED)
def webhook_trigger(
    workflow_id: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Run:
    """Authenticated webhook receiver. For public webhooks, see
    /api/v1/public/webhook/{token} — token is the workflow id (not secret;
    swap for a signed token in production).
    """
    workflow = db.get(Workflow, workflow_id)
    if not workflow or workflow.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="workflow not found")
    if workflow.trigger != "webhook":
        raise HTTPException(status_code=400, detail="workflow trigger is not 'webhook'")
    run = Run(workflow_id=workflow.id, trigger="webhook", context=payload or {})
    db.add(run)
    db.flush()
    try:
        execute_run_sync(db, run=run, workflow=workflow, trigger_payload=payload or {})
    except Exception as exc:  # noqa: BLE001
        run.status = RunStatus.FAILED
        run.error = str(exc)
    db.commit()
    db.refresh(run)
    return run
