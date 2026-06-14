"""Public webhook endpoint (no auth). Token in URL = workflow id.
Suitable for internal triggers where the URL itself acts as a shared
secret; swap for HMAC signing in production.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from flowforge.core.database import get_db
from flowforge.models.run import Run, RunStatus
from flowforge.models.workflow import Workflow
from flowforge.services.workflow_engine import execute_run_sync

router = APIRouter(prefix="/api/v1/public", tags=["public"])


@router.post("/webhook/{workflow_id}", status_code=202)
async def public_webhook(
    workflow_id: str,
    request: Request,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    workflow = db.get(Workflow, workflow_id)
    if not workflow or not workflow.is_active:
        raise HTTPException(status_code=404, detail="workflow not found or inactive")
    if workflow.trigger != "webhook":
        raise HTTPException(status_code=400, detail="workflow does not accept webhook triggers")
    try:
        payload = await request.json()
    except Exception:
        payload = {"raw": (await request.body()).decode("utf-8", errors="ignore")}
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
    return {
        "run_id": run.id,
        "status": run.status.value,
        "workflow_id": workflow.id,
    }
