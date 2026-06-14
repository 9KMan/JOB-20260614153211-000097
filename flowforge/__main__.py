"""Console entry-point so the app can run as ``python -m flowforge``."""

from __future__ import annotations

import uvicorn

from flowforge.core.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "flowforge.api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info",
    )


if __name__ == "__main__":
    main()
