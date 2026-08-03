"""Shared FastAPI dependencies: authentication, roles, pagination."""

from __future__ import annotations

import uuid
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

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
    # Carried on the request so downstream guards and the audit trail can see
    # that this session is an admin acting as someone else.
    request.state.impersonated_by = payload.get("act")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def forbid_impersonation(request: Request, _: CurrentUser) -> None:
    """Block an impersonating session from touching the account itself.

    An admin acting as a user is there to see what the user sees and to
    reproduce a problem - not to change the credentials that would lock the
    real owner out. Password, email and account deletion are refused outright
    rather than merely hidden in the UI, because the UI is not the boundary.

    The unused `CurrentUser` parameter is load-bearing: it forces
    `get_current_user` to resolve FIRST, which is what populates
    `request.state.impersonated_by`. Without it FastAPI is free to run this
    guard before the token has been decoded, `getattr` returns None, and the
    check silently passes - which is exactly what happened before this
    parameter existed, letting an impersonating session change the account's
    password.
    """
    if getattr(request.state, "impersonated_by", None):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Not available while viewing as another user. End the "
                "impersonation session and sign in as yourself to do this."
            ),
        )


NoImpersonation = Annotated[None, Depends(forbid_impersonation)]


#: Previously an email-verification gate on actions that spend real resources.
#: This deployment sends no mail, so there is no verification step to gate on
#: and every authenticated user may run an audit. Kept as an alias rather than
#: deleted so the intent stays visible at the call sites in audits.py - if a
#: mail transport is ever added, the gate goes back here and nothing else has
#: to change.
VerifiedUser = CurrentUser


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
