"""Cookie handling for the refresh-token flow, plus CSRF double-submit.

Why cookies at all: keeping the long-lived refresh token in an httpOnly cookie
means JavaScript (and therefore any XSS payload) cannot read it. The short-lived
access token is held in memory by the SPA and sent in the Authorization header,
which is immune to CSRF.

The one CSRF-exposed surface is the cookie-authenticated ``/auth/refresh`` and
``/auth/logout``. Those are protected by SameSite=Strict *and* a double-submit
token, so neither mechanism is a single point of failure.
"""

from __future__ import annotations

import secrets

from fastapi import HTTPException, Request, Response, status

from app.core.config import settings
from app.core.security import constant_time_equals

REFRESH_COOKIE = "geo_refresh"
CSRF_COOKIE = "geo_csrf"
CSRF_HEADER = "X-CSRF-Token"

#: Scoping the cookie to the refresh endpoints means it is not attached to every
#: API call, shrinking the window in which it can be captured.
REFRESH_COOKIE_PATH = "/api/v1/auth"


def set_auth_cookies(response: Response, *, refresh_token: str) -> str:
    """Set the refresh + CSRF cookies. Returns the CSRF token for the body."""
    max_age = settings.refresh_token_ttl_days * 86_400
    secure = settings.is_production  # plain HTTP is only allowed in local dev

    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=max_age,
        httponly=True,
        secure=secure,
        samesite="strict",
        path=REFRESH_COOKIE_PATH,
    )

    csrf_token = secrets.token_urlsafe(24)
    # Readable by JS on purpose: the SPA echoes it back in the CSRF header.
    response.set_cookie(
        CSRF_COOKIE,
        csrf_token,
        max_age=max_age,
        httponly=False,
        secure=secure,
        samesite="strict",
        path="/",
    )
    return csrf_token


def clear_auth_cookies(response: Response) -> None:
    secure = settings.is_production
    response.delete_cookie(
        REFRESH_COOKIE, path=REFRESH_COOKIE_PATH, httponly=True, secure=secure, samesite="strict"
    )
    response.delete_cookie(
        CSRF_COOKIE, path="/", httponly=False, secure=secure, samesite="strict"
    )


def get_refresh_token(request: Request) -> str:
    token = request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="No active session"
        )
    return token


def require_csrf(request: Request) -> None:
    """Double-submit check: the header must match the non-httpOnly cookie.

    A cross-site attacker can make the browser send the cookie, but same-origin
    policy stops them from reading its value to populate the header.
    """
    cookie_token = request.cookies.get(CSRF_COOKIE)
    header_token = request.headers.get(CSRF_HEADER)
    if not cookie_token or not header_token or not constant_time_equals(
        cookie_token, header_token
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed"
        )
