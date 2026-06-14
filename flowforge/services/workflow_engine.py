"""Workflow execution engine.

The engine takes a Workflow and a Run, walks its steps, persists
per-step state, and returns a final Run status. It does not run
asynchronously itself; the caller decides whether to run inline
(API request) or schedule it via the worker.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from flowforge.core.config import get_settings
from flowforge.models.run import Run, RunStatus, StepRun, StepStatus
from flowforge.models.workflow import Workflow
from flowforge.services import audit
from flowforge.services.step_runner import HANDLERS, StepContext

log = logging.getLogger("flowforge.engine")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def _resolve_step_index(steps: list, step_id: str) -> Optional[int]:
    for idx, step in enumerate(steps):
        if step.get("id") == step_id:
            return idx
    return None


def execute_run_sync(
    session: Session,
    *,
    run: Run,
    workflow: Workflow,
    trigger_payload: Optional[Dict[str, Any]] = None,
) -> Run:
    """Run a workflow to completion synchronously. Safe to call from
    FastAPI request handlers for small workflows; large workflows
    should be dispatched to the worker.
    """
    settings = get_settings()
    steps = workflow.step_list()

    run.status = RunStatus.RUNNING
    run.started_at = _now()
    run.context = trigger_payload or run.context or {}
    session.flush()

    state: Dict[str, Any] = {
        "input": run.context or {},
        "trigger": run.context or {},
        "workflow": {"id": workflow.id, "name": workflow.name},
        "steps": {},
    }

    ctx = StepContext(
        session=session,
        run_id=run.id,
        workflow_id=workflow.id,
        owner_id=workflow.owner_id,
        trigger_payload=run.context or {},
    )

    audit.record(
        session,
        action="run.start",
        actor_id=workflow.owner_id,
        target_type="run",
        target_id=run.id,
        payload={"workflow_id": workflow.id, "trigger": run.trigger},
    )

    failed = False
    error: Optional[str] = None
    for index, step in enumerate(steps):
        step_id = str(step.get("id") or f"step-{index}")
        name = step.get("name") or step_id
        step_type = (step.get("type") or "").lower()
        handler = HANDLERS.get(step_type)
        step_run = StepRun(
            run_id=run.id,
            position=index,
            step_id=step_id,
            name=name,
            type=step_type,
            status=StepStatus.RUNNING,
            started_at=_now(),
        )
        session.add(step_run)
        session.flush()
        if not handler:
            step_run.status = StepStatus.FAILED
            step_run.error = f"unknown step type: {step_type!r}"
            step_run.finished_at = _now()
            step_run.duration_ms = int((step_run.finished_at - step_run.started_at).total_seconds() * 1000)
            failed = True
            error = f"step {step_id}: unknown type {step_type!r}"
            break

        if step_type == "condition":
            branch = step.get("config", {}).get("branch")
        else:
            branch = False

        try:
            output = asyncio.run(_invoke_with_timeout(handler(step, state, ctx), settings.step_timeout_seconds))
            if step_type == "condition" and branch and output.get("skipped"):
                step_run.status = StepStatus.SKIPPED
                step_run.output = output
                step_run.finished_at = _now()
                step_run.duration_ms = int((step_run.finished_at - step_run.started_at).total_seconds() * 1000)
                state["steps"][step_id] = output
                log.info("run %s step %s condition false — branching", run.id, step_id)
                break
            if step_type == "condition" and not output.get("result"):
                step_run.status = StepStatus.SKIPPED
                step_run.output = output
                step_run.finished_at = _now()
                step_run.duration_ms = int((step_run.finished_at - step_run.started_at).total_seconds() * 1000)
                state["steps"][step_id] = output
                log.info("run %s step %s condition false — stopping", run.id, step_id)
                break
            step_run.status = StepStatus.SUCCEEDED
            step_run.output = output
            state["steps"][step_id] = output
        except asyncio.TimeoutError:
            step_run.status = StepStatus.FAILED
            step_run.error = f"step timed out after {settings.step_timeout_seconds}s"
            failed = True
            error = step_run.error
        except Exception as exc:  # noqa: BLE001
            step_run.status = StepStatus.FAILED
            step_run.error = f"{type(exc).__name__}: {exc}"
            failed = True
            error = step_run.error
        finally:
            step_run.finished_at = _now()
            if step_run.started_at:
                step_run.duration_ms = int((step_run.finished_at - step_run.started_at).total_seconds() * 1000)
            session.flush()

        if failed:
            break

    run.finished_at = _now()
    if run.started_at:
        run.duration_ms = int((run.finished_at - run.started_at).total_seconds() * 1000)
    run.outputs = state.get("steps", {})
    run.status = RunStatus.FAILED if failed else RunStatus.SUCCEEDED
    if error:
        run.error = error

    audit.record(
        session,
        action="run.end",
        actor_id=workflow.owner_id,
        target_type="run",
        target_id=run.id,
        payload={"status": run.status.value, "duration_ms": run.duration_ms},
    )
    session.flush()
    return run


async def _invoke_with_timeout(awaitable, timeout: float):  # type: ignore[no-untyped-def]
    return await asyncio.wait_for(awaitable, timeout=timeout)
