"""Liveness and readiness probes.

Three, deliberately:

* ``/health``       - the process is up. Docker's healthcheck uses this.
* ``/healthz``      - the database is reachable *from here*. This is the one to
  point uptime monitoring at: the database is on a separate host, so the link
  between the two boxes is a thing that can fail on its own while the app
  itself is perfectly healthy.
* ``/health/ready`` - everything an incoming request needs, database and Redis.
"""

from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis_client import get_redis
from app.db.session import SessionLocal

router = APIRouter(tags=["health"])
log = get_logger("health")

#: Bounded so a hung network link fails the probe instead of holding the
#: connection open until the monitoring system's own timeout.
_DB_PROBE_TIMEOUT_SECONDS = 5.0


@router.get("/health", summary="Liveness probe")
async def health() -> dict[str, str]:
    """Cheap check: the process is up and serving. Used by Docker healthchecks."""
    return {"status": "ok"}


@router.get("/healthz", summary="Database connectivity probe")
async def healthz(response: Response) -> dict[str, object]:
    """503 when the database cannot be reached, with the latency when it can.

    Returns the round-trip time because a link that is up but degrading is the
    warning you want before it goes down entirely.
    """
    started = time.perf_counter()
    try:
        async with asyncio.timeout(_DB_PROBE_TIMEOUT_SECONDS):
            async with SessionLocal() as session:
                await session.execute(text("SELECT 1"))
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        # Logged at error level so a dropped link between the app and database
        # hosts shows up in the log pipeline, not only on the monitoring side.
        log.error(
            "healthz_database_unreachable",
            host=settings.postgres_host,
            port=settings.postgres_port,
            error=f"{type(exc).__name__}: {exc}",
            elapsed_ms=elapsed_ms,
        )
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "unhealthy",
            "database": "unreachable",
            # Type name only - the driver's message can carry the DSN.
            "error": type(exc).__name__,
            "elapsed_ms": elapsed_ms,
        }

    return {
        "status": "ok",
        "database": "reachable",
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
    }


@router.get("/health/ready", summary="Readiness probe")
async def readiness(response: Response) -> dict[str, object]:
    """Verifies the dependencies an incoming request actually needs."""
    checks: dict[str, str] = {}

    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {type(exc).__name__}"

    try:
        await get_redis().ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {type(exc).__name__}"

    healthy = all(value == "ok" for value in checks.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ready" if healthy else "degraded", "checks": checks}
