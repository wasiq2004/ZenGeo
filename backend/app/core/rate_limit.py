"""Redis-backed fixed-window rate limiting.

Used as a FastAPI dependency so a limit is declared next to the route it
protects::

    @router.post("/login", dependencies=[Depends(RateLimit(settings.rate_limit_login))])

Fails **open** if Redis is unreachable: a limiter outage should degrade
protection, not take authentication offline. The outage is logged loudly.
"""

# NOTE: deliberately no `from __future__ import annotations` in this module.
# `RateLimit` is used as a class-based dependency, and FastAPI resolves a
# callable *instance*'s annotations against `call.__globals__` - which an
# instance does not have. With postponed annotations, `request: Request` would
# stay an unresolved string and get misread as a query parameter.
from fastapi import Depends, HTTPException, Request, status

from app.core.config import parse_rate_limit, settings
from app.core.logging import get_logger
from app.core.redis_client import get_redis

log = get_logger("rate_limit")


def client_ip(request: Request) -> str:
    """Best-effort client IP.

    Trusts ``X-Forwarded-For`` only because the app is always deployed behind
    our own reverse proxy (Caddy), which overwrites the header. Exposing the
    backend port directly to the internet would make this spoofable - the
    compose files keep it on the internal network.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _hit(key: str, limit: int, window: int) -> tuple[bool, int]:
    """Increment the counter for ``key``; return (allowed, seconds_until_reset)."""
    redis = get_redis()
    try:
        pipe = redis.pipeline()
        pipe.incr(key)
        pipe.ttl(key)
        count, ttl = await pipe.execute()
        if ttl is None or ttl < 0:
            await redis.expire(key, window)
            ttl = window
        return count <= limit, int(ttl)
    except Exception as exc:  # pragma: no cover - infrastructure failure path
        log.error("rate_limit_backend_unavailable", error=str(exc), key=key)
        return True, 0


class RateLimit:
    """Dependency factory. ``scope`` separates counters for different routes."""

    def __init__(self, spec: str, scope: str = "", per_user: bool = False) -> None:
        self.limit, self.window = parse_rate_limit(spec)
        self.scope = scope
        self.per_user = per_user

    async def __call__(self, request: Request) -> None:
        scope = self.scope or request.url.path
        identity = client_ip(request)
        if self.per_user:
            user = getattr(request.state, "user_id", None)
            if user:
                identity = f"user:{user}"
        key = f"rl:{scope}:{identity}"
        allowed, retry_after = await _hit(key, self.limit, self.window)
        if not allowed:
            log.warning("rate_limited", scope=scope, identity=identity)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please slow down and try again shortly.",
                headers={"Retry-After": str(retry_after or self.window)},
            )


async def consume_identifier_budget(scope: str, identifier: str, spec: str) -> bool:
    """Rate-limit by a value from the request body (e.g. the email being probed).

    Complements the per-IP limiter: a distributed credential-stuffing attack
    rotates IPs but still hammers the same account.
    """
    limit, window = parse_rate_limit(spec)
    allowed, _ = await _hit(f"rl:{scope}:id:{identifier.lower()}", limit, window)
    return allowed


DefaultRateLimit = Depends(RateLimit(settings.rate_limit_default, scope="default"))
