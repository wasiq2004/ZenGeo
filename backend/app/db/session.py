"""Async SQLAlchemy engine and session factory.

The engine is created lazily rather than at import, because asyncpg connections
are bound to the event loop that opened them. The API runs one long-lived loop
and reuses one engine happily; a Celery worker calls `asyncio.run()` per task,
creating a fresh loop each time. A module-level engine built on the first
task's loop hands the second task a connection whose loop is already closed,
which surfaces as "got Future attached to a different loop".

So: build the engine on first use, and let the worker call `dispose_engine()`
when a task ends so the next one starts clean.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            echo=False,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
            pool_recycle=1800,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(), class_=AsyncSession, expire_on_commit=False, autoflush=False
        )
    return _session_factory


def SessionLocal() -> AsyncSession:  # noqa: N802 - reads as a factory at call sites
    """A new session on the engine bound to the current loop."""
    return get_session_factory()()


async def dispose_engine() -> None:
    """Close every pooled connection and drop the engine.

    Call this at the end of a worker task, before its event loop closes.
    """
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: one session per request, rolled back on error."""
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Standalone session for workers and CLI scripts."""
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
