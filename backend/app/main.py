"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from app.core.redis_client import close_redis
from app.db.session import dispose_engine

configure_logging(settings.log_level, settings.log_format)
log = get_logger("startup")


@asynccontextmanager
async def lifespan(_app: FastAPI):  # type: ignore[no-untyped-def]
    problems = settings.validate_for_production()
    if problems:
        # Refuse to boot a production deployment with placeholder secrets.
        for problem in problems:
            log.error("insecure_production_config", problem=problem)
        raise RuntimeError(
            "Refusing to start in production with insecure configuration: "
            + "; ".join(problems)
        )
    await _check_database_reachable()

    log.info(
        "application_start",
        environment=settings.environment,
        database_host=settings.postgres_host,
    )
    yield
    await close_redis()
    await dispose_engine()
    log.info("application_stop")


#: How long to wait for the database on boot. The database is on another host
#: now, so "unreachable" is a normal-ish network event rather than an
#: impossibility - but it should surface in seconds, not hang the boot.
_STARTUP_DB_TIMEOUT_SECONDS = 10.0


async def _check_database_reachable() -> None:
    """Fail fast, and loudly, if the database is not there.

    Without this the app boots happily and every request 500s instead, which
    reads as an application bug rather than a network or firewall problem. The
    process exits so the container restart policy handles the retry loop, and
    the reason lands in the logs exactly once per attempt.
    """
    import asyncio

    from sqlalchemy import text

    from app.db.session import SessionLocal

    try:
        async with asyncio.timeout(_STARTUP_DB_TIMEOUT_SECONDS):
            async with SessionLocal() as session:
                await session.execute(text("SELECT 1"))
    except TimeoutError as exc:
        log.error(
            "database_unreachable_on_startup",
            host=settings.postgres_host,
            port=settings.postgres_port,
            sslmode=settings.postgres_sslmode,
            timeout_seconds=_STARTUP_DB_TIMEOUT_SECONDS,
            hint=(
                "No response within the timeout. Usually a firewall dropping the "
                "connection, or listen_addresses not covering this host."
            ),
        )
        raise RuntimeError(
            f"Database at {settings.postgres_host}:{settings.postgres_port} did not "
            f"respond within {_STARTUP_DB_TIMEOUT_SECONDS:.0f}s"
        ) from exc
    except Exception as exc:
        log.error(
            "database_unreachable_on_startup",
            host=settings.postgres_host,
            port=settings.postgres_port,
            sslmode=settings.postgres_sslmode,
            error=f"{type(exc).__name__}: {exc}",
            hint=(
                "Check pg_hba.conf allows this host over hostssl, that the server "
                "has ssl=on, and that the runtime role's password is current."
            ),
        )
        raise RuntimeError(
            f"Cannot reach the database at {settings.postgres_host}:"
            f"{settings.postgres_port}: {type(exc).__name__}: {exc}"
        ) from exc

    log.info(
        "database_reachable",
        host=settings.postgres_host,
        port=settings.postgres_port,
        sslmode=settings.postgres_sslmode,
    )


def create_app() -> FastAPI:
    docs_url = None if settings.is_production else "/docs"
    app = FastAPI(
        title="CheckGEO.ai API",
        version="1.0.0",
        description=(
            "Audits how visible and citable a business is inside AI-generated "
            "answers, and scores it 0-100 across seven weighted pillars."
        ),
        lifespan=lifespan,
        docs_url=docs_url,
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
    )

    # Order matters: the outermost middleware is added last.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,  # explicit allow-list, never "*"
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )
    app.add_middleware(RequestContextMiddleware)

    app.include_router(api_router)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Never leak a stack trace or internal message to a client."""
        log.exception("unhandled_exception", path=request.url.path, error=type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "request_id": getattr(request.state, "request_id", None),
            },
        )

    return app


app = create_app()
