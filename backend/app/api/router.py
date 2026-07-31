"""Aggregates every versioned API router."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    admin,
    audits,
    auth,
    businesses,
    dashboard,
    health,
    llm_keys,
    reports,
    users,
)
from app.core.config import settings

api_router = APIRouter()

# Health lives outside the version prefix so orchestrators can hit /health.
api_router.include_router(health.router)

v1 = APIRouter(prefix=settings.api_prefix)
v1.include_router(auth.router)
v1.include_router(users.router)
v1.include_router(llm_keys.router)
v1.include_router(businesses.router)
v1.include_router(audits.router)
v1.include_router(reports.router)
v1.include_router(dashboard.router)
v1.include_router(admin.router)

api_router.include_router(v1)
