"""Long-running worker process. The FastAPI app also runs the scheduler
in-process via APScheduler, so this script is primarily a placeholder
for moving execution to a dedicated worker (Celery / RQ / Dramatiq).

Usage: ``python -m flowforge.workers.runner``
"""

from __future__ import annotations

import logging
import signal
import time
from types import FrameType
from typing import Optional

from flowforge.core.config import get_settings
from flowforge.core.database import init_db
from flowforge.core.logging import configure_logging
from flowforge.services.scheduler import init_scheduler, schedule_all_active_workflows

log = logging.getLogger("flowforge.worker")
_running = True


def _shutdown(signum: int, _: Optional[FrameType]) -> None:
    global _running
    log.info("worker received signal %s — shutting down", signum)
    _running = False


def main() -> None:
    configure_logging()
    settings = get_settings()
    init_db()
    init_scheduler()
    count = schedule_all_active_workflows()
    log.info("worker ready (env=%s, schedules=%d)", settings.environment, count)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
    while _running:
        time.sleep(1)
    log.info("worker exited")


if __name__ == "__main__":
    main()
