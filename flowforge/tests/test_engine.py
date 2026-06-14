"""Workflow engine + step runner tests."""

from __future__ import annotations

from sqlalchemy.orm import Session

from flowforge.core.database import get_session_factory, init_db
from flowforge.core.security import hash_password
from flowforge.models.run import Run, RunStatus
from flowforge.models.user import User
from flowforge.models.workflow import Workflow
from flowforge.services.workflow_engine import execute_run_sync


def _make_user(session: Session) -> User:
    user = session.query(User).filter(User.email == "engine@flowforge.example").first()
    if not user:
        user = User(
            email="engine@flowforge.example",
            hashed_password=hash_password("engine-test"),
            role="admin",
        )
        session.add(user)
        session.commit()
        session.refresh(user)
    return user


def test_run_log_step():
    init_db()
    factory = get_session_factory()
    session = factory()
    try:
        user = _make_user(session)
        wf = Workflow(
            name="Log test",
            owner_id=user.id,
            trigger="manual",
            definition={"steps": [
                {"id": "log1", "name": "say", "type": "log",
                 "config": {"message": "hello ${{ trigger.who | default('world') }}", "level": "info"}},
            ]},
        )
        session.add(wf)
        session.commit()
        session.refresh(wf)
        run = Run(workflow_id=wf.id, trigger="manual", context={"who": "team"})
        session.add(run)
        session.commit()
        session.refresh(run)
        result = execute_run_sync(session, run=run, workflow=wf, trigger_payload={"who": "team"})
        session.commit()
        assert result.status == RunStatus.SUCCEEDED
        assert result.step_runs[0].output["message"] == "hello team"
    finally:
        session.close()


def test_run_unknown_step_fails():
    init_db()
    factory = get_session_factory()
    session = factory()
    try:
        user = _make_user(session)
        wf = Workflow(
            name="Bad step",
            owner_id=user.id,
            trigger="manual",
            definition={"steps": [
                {"id": "weird", "name": "weird", "type": "this-does-not-exist", "config": {}},
            ]},
        )
        session.add(wf)
        session.commit()
        session.refresh(wf)
        run = Run(workflow_id=wf.id, trigger="manual", context={})
        session.add(run)
        session.commit()
        session.refresh(run)
        result = execute_run_sync(session, run=run, workflow=wf, trigger_payload={})
        session.commit()
        assert result.status == RunStatus.FAILED
        assert "unknown" in (result.error or "").lower()
    finally:
        session.close()


def test_run_condition_branch():
    init_db()
    factory = get_session_factory()
    session = factory()
    try:
        user = _make_user(session)
        wf = Workflow(
            name="Condition test",
            owner_id=user.id,
            trigger="manual",
            definition={"steps": [
                {"id": "c", "name": "check", "type": "condition",
                 "config": {"left": "${{ trigger.value }}", "op": ">", "right": "10", "branch": False}},
                {"id": "log_ok", "name": "log", "type": "log",
                 "config": {"message": "value is high"}},
            ]},
        )
        session.add(wf)
        session.commit()
        session.refresh(wf)
        run = Run(workflow_id=wf.id, trigger="manual", context={"value": 20})
        session.add(run)
        session.commit()
        session.refresh(run)
        result = execute_run_sync(session, run=run, workflow=wf, trigger_payload={"value": 20})
        session.commit()
        assert result.status == RunStatus.SUCCEEDED
        assert result.step_runs[0].status.value == "succeeded"
        # Next step ran (log_ok)
        assert len(result.step_runs) == 2
    finally:
        session.close()


def test_run_ai_step_with_stub():
    init_db()
    factory = get_session_factory()
    session = factory()
    try:
        user = _make_user(session)
        wf = Workflow(
            name="AI test",
            owner_id=user.id,
            trigger="manual",
            definition={"steps": [
                {"id": "ai", "name": "ask", "type": "ai",
                 "config": {"prompt": "hello", "system": "be brief", "provider": "stub"}},
            ]},
        )
        session.add(wf)
        session.commit()
        session.refresh(wf)
        run = Run(workflow_id=wf.id, trigger="manual", context={})
        session.add(run)
        session.commit()
        session.refresh(run)
        result = execute_run_sync(session, run=run, workflow=wf, trigger_payload={})
        session.commit()
        assert result.status == RunStatus.SUCCEEDED
        out = result.step_runs[0].output
        assert out["provider"] == "stub"
        assert "stub:" in out["text"]
    finally:
        session.close()
