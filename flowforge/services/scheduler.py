"""APScheduler-based scheduler for workflow cron triggers."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from flowforge.core.database import session_scope
from flowforge.models.run import Run, RunStatus
from flowforge.models.workflow import Workflow
from flowforge.services.workflow_engine import execute_run_sync

log = logging.getLogger("flowforge.scheduler")

_scheduler: BackgroundScheduler | None = None
_job_prefix = "flowforge:"


def get_scheduler() -> Optional[BackgroundScheduler]:
    return _scheduler


def init_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    scheduler = BackgroundScheduler(daemon=True, timezone="UTC")
    scheduler.start()
    _scheduler = scheduler
    log.info("scheduler started")
    return _scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def schedule_workflow(workflow: Workflow) -> Optional[str]:
    """Register (or re-register) a workflow's cron schedule. Returns
    the job id or None if no schedule.
    """
    sched = init_scheduler()
    if not workflow.is_active or not workflow.schedule:
        unschedule_workflow(workflow.id)
        return None
    job_id = _job_prefix + workflow.id
    try:
        sched.remove_job(job_id)
    except Exception:
        pass
    trigger = _parse_cron(workflow.schedule)
    sched.add_job(_run_workflow, trigger, id=job_id, args=[workflow.id], replace_existing=True)
    log.info("scheduled workflow %s with %r", workflow.id, workflow.schedule)
    return job_id


def unschedule_workflow(workflow_id: str) -> None:
    sched = _scheduler
    if sched is None:
        return
    try:
        sched.remove_job(_job_prefix + workflow_id)
    except Exception:
        pass


def list_schedules() -> Dict[str, Any]:
    sched = _scheduler
    if sched is None:
        return {"jobs": []}
    return {
        "jobs": [
            {
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
            }
            for job in sched.get_jobs()
        ]
    }


def schedule_all_active_workflows() -> int:
    """Re-register every active scheduled workflow from the DB. Returns
    the number of schedules registered.
    """
    from flowforge.core.database import session_scope
    from flowforge.models.workflow import Workflow

    count = 0
    with session_scope() as session:
        for wf in session.query(Workflow).filter(Workflow.is_active.is_(True), Workflow.trigger == "schedule").all():
            if wf.schedule:
                schedule_workflow(wf)
                count += 1
    return count


def _parse_cron(expr: str) -> CronTrigger:
    parts = expr.split()
    if len(parts) == 5:
        return CronTrigger.from_crontab(expr)
    if len(parts) == 6:
        return CronTrigger(
            second=parts[0],
            minute=parts[1],
            hour=parts[2],
            day=parts[3],
            month=parts[4],
            day_of_week=parts[5],
        )
    raise ValueError("schedule must be 5 or 6 cron fields")


def _run_workflow(workflow_id: str) -> None:
    """Scheduler callback. Opens its own session and runs the workflow."""
    log.info("cron firing for workflow %s", workflow_id)
    with session_scope() as session:
        workflow: Workflow | None = session.get(Workflow, workflow_id)
        if not workflow or not workflow.is_active:
            return
        run = Run(workflow_id=workflow.id, trigger="schedule")
        session.add(run)
        session.flush()
        try:
            execute_run_sync(session, run=run, workflow=workflow, trigger_payload={"scheduled": True})
        except Exception as exc:  # noqa: BLE001
            log.exception("cron run failed: %s", exc)
            run.status = RunStatus.FAILED
            run.error = str(exc)
            session.flush()
