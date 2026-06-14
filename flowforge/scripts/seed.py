"""Seed the database with a demo user, integrations, and a workflow."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# allow running as `python -m flowforge.scripts.seed`
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy.orm import Session  # noqa: E402

from flowforge.core.database import get_session_factory, init_db  # noqa: E402
from flowforge.core.security import hash_password  # noqa: E402
from flowforge.models.agent import Agent  # noqa: E402
from flowforge.models.integration import Integration, IntegrationKind  # noqa: E402
from flowforge.models.user import User  # noqa: E402
from flowforge.models.workflow import Workflow  # noqa: E402


DEMO_USER_EMAIL = os.environ.get("SEED_EMAIL") or "demo" + chr(64) + "flowforge.example"
DEMO_USER_PASSWORD = os.environ.get("SEED_PASSWORD", "flowforge-demo")


def seed() -> None:
    init_db()
    factory = get_session_factory()
    session: Session = factory()
    try:
        user = session.query(User).filter(User.email == DEMO_USER_EMAIL).first()
        if not user:
            user = User(
                email=DEMO_USER_EMAIL,
                full_name="FlowForge Demo",
                role="admin",
                hashed_password=hash_password(DEMO_USER_PASSWORD),
            )
            session.add(user)
            session.flush()
            print(f"created user: {user.email}")

        # Integrations
        existing_names = {i.name for i in session.query(Integration).filter(Integration.owner_id == user.id).all()}
        demo_integrations = [
            Integration(
                name="default",
                kind=IntegrationKind.EMAIL,
                config={"host": "smtp.example.com", "port": 587, "from": "noreply" + chr(64) + "flowforge.example"},
                secret={"user": "demo", "password": "demo"},
                owner_id=user.id,
            ),
            Integration(
                name="slack-default",
                kind=IntegrationKind.SLACK,
                config={},
                secret={"webhook_url": ""},
                owner_id=user.id,
            ),
            Integration(
                name="crm-api",
                kind=IntegrationKind.HTTP,
                config={"base_url": "https://api.example.com/v1"},
                secret={"headers": {"Authorization": "Bearer DEMO"}},
                owner_id=user.id,
            ),
        ]
        for integ in demo_integrations:
            if integ.name not in existing_names:
                session.add(integ)
                print(f"created integration: {integ.name}")

        # Agent
        if not session.query(Agent).filter(Agent.owner_id == user.id).first():
            session.add(
                Agent(
                    name="research-assistant",
                    description="General-purpose research agent",
                    provider="stub",
                    model="stub-1",
                    system_prompt="You are a precise research assistant. Answer concisely.",
                    temperature=0.2,
                    owner_id=user.id,
                )
            )
            print("created agent: research-assistant")

        # Demo workflows
        if not session.query(Workflow).filter(Workflow.owner_id == user.id).first():
            demo_wf = Workflow(
                name="Daily Lead Enrichment",
                description="Fetch new leads, enrich via AI, notify Slack.",
                trigger="manual",
                schedule=None,
                owner_id=user.id,
                definition={
                    "steps": [
                        {
                            "id": "fetch",
                            "name": "Fetch leads from CRM",
                            "type": "http",
                            "config": {
                                "method": "GET",
                                "url": "https://jsonplaceholder.typicode.com/users",
                                "integration": "crm-api",
                            },
                        },
                        {
                            "id": "summarize",
                            "name": "Summarize with AI",
                            "type": "ai",
                            "config": {
                                "prompt": "Summarize this dataset: ${{ steps.fetch.json }}",
                                "system": "You are a precise data summarizer.",
                                "temperature": 0.1,
                            },
                        },
                        {
                            "id": "notify",
                            "name": "Post summary to Slack",
                            "type": "slack",
                            "config": {
                                "text": "Daily summary: ${{ steps.summarize.text | default('(no summary)') }}",
                                "integration": "slack-default",
                            },
                        },
                    ]
                },
            )
            session.add(demo_wf)
            print("created workflow: Daily Lead Enrichment")

            schedule_wf = Workflow(
                name="Weekly Status Report",
                description="Generate a weekly report every Monday at 09:00 UTC.",
                trigger="schedule",
                schedule="0 9 * * 1",
                owner_id=user.id,
                definition={
                    "steps": [
                        {
                            "id": "compose",
                            "name": "Compose weekly summary",
                            "type": "ai",
                            "config": {
                                "prompt": "Compose a 3-bullet weekly status update for a holding-company leadership team.",
                                "system": "Tone: clear, professional, plain prose.",
                            },
                        },
                        {
                            "id": "log",
                            "name": "Log the output",
                            "type": "log",
                            "config": {"message": "Weekly summary: ${{ steps.compose.text }}", "level": "info"},
                        },
                    ]
                },
            )
            session.add(schedule_wf)
            print("created workflow: Weekly Status Report (cron)")

        session.commit()
        print(json.dumps({"ok": True, "user": user.email}, indent=2))
    finally:
        session.close()


if __name__ == "__main__":
    seed()
