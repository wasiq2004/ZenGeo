"""Shared FastAPI dependencies: authentication, roles, pagination."""

from __future__ import annotations

import uuid
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import decode_access_token
from app.db.models.user import User, UserRole
from app.db.session import get_db
from app.schemas.common import PaginationParams

log = get_logger("deps")

# auto_error=False so we can return a consistent JSON error shape ourselves.
_bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[AsyncSession, Depends(get_db)]

CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    request: Request,
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise CREDENTIALS_EXCEPTION

    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token expired",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        ) from None
    except jwt.PyJWTError:
        raise CREDENTIALS_EXCEPTION from None

    try:
        user_id = uuid.UUID(str(payload["sub"]))
    except (KeyError, ValueError):
        raise CREDENTIALS_EXCEPTION from None

    # Always re-read the user: a token minted before an admin disabled the
    # account, or before a role change, must not keep working.
    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account is not active"
        )

    request.state.user_id = str(user.id)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_verified_user(user: CurrentUser) -> User:
    """Gate for actions that consume real resources (running audits)."""
    if settings.require_email_verification and not user.is_email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Confirm your email address before running an audit. "
                "Check your inbox or request a new link from Settings."
            ),
        )
    return user


VerifiedUser = Annotated[User, Depends(get_verified_user)]


async def get_admin_user(user: CurrentUser) -> User:
    if user.role is not UserRole.admin:
        # Logged so repeated probing of admin routes is visible.
        log.warning("admin_access_denied", user_id=str(user.id), role=user.role.value)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required"
        )
    return user


AdminUser = Annotated[User, Depends(get_admin_user)]

Pagination = Annotated[PaginationParams, Depends()]
