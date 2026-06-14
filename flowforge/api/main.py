"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from flowforge.api import agents, auth, dashboard, etl, integrations, public, runs, workflows
from flowforge.core.config import get_settings
from flowforge.core.database import init_db
from flowforge.core.logging import configure_logging
from flowforge.services.scheduler import init_scheduler, schedule_all_active_workflows


log = logging.getLogger("flowforge")


@asynccontextmanager
async def _lifespan(_: FastAPI):
    init_db()
    init_scheduler()
    try:
        schedule_all_active_workflows()
    except Exception as exc:  # pragma: no cover
        log.warning("could not hydrate schedules on startup: %s", exc)
    log.info(
        "FlowForge ready (env=%s, port=%s)",
        get_settings().environment,
        get_settings().port,
    )
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(logging.INFO)
    app = FastAPI(
        title=f"{settings.app_name} — AI Workflow Automation",
        version="0.1.0",
        description=(
            "FlowForge is a workflow automation platform for holding companies: "
            "REST + webhook + cron triggers, pluggable step runners (HTTP, AI, "
            "email, Slack, transforms), append-only audit log, and a flat-design "
            "dashboard."
        ),
        lifespan=_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(auth.router)
    app.include_router(workflows.router)
    app.include_router(runs.router)
    app.include_router(integrations.router)
    app.include_router(agents.router)
    app.include_router(etl.router)
    app.include_router(dashboard.router)
    app.include_router(public.router)

    # Static frontend
    frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
    static_dir = frontend_dir / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        index_html = frontend_dir / "index.html"
        if index_html.exists():
            return FileResponse(str(index_html))
        return FileResponse(str(frontend_dir / "index.html"))  # type: ignore[arg-type]

    @app.get("/healthz", tags=["health"])
    def healthz() -> dict:
        return {"status": "ok", "app": settings.app_name, "version": "0.1.0"}

    @app.get("/api/v1/catalog/step-types", tags=["catalog"])
    def step_types() -> dict:
        from flowforge.services.step_runner import list_step_types

        return list_step_types()

    @app.exception_handler(Exception)
    def unhandled_exception(_, exc):  # type: ignore[no-untyped-def]
        log.exception("unhandled error: %s", exc)
        return JSONResponse(status_code=500, content={"detail": "internal server error"})

    return app


app = create_app()
