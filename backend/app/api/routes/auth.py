"""Authentication endpoints.

One login page, one credential set: the response carries the user's ``role`` and
the SPA routes to /app or /admin accordingly. Authorisation is still enforced
per-request on the server - the role in the token is not a client-side decision.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.cookies import (
    clear_auth_cookies,
    get_refresh_token,
    require_csrf,
    set_auth_cookies,
)
from app.api.deps import CurrentUser, DbSession, forbid_impersonation
from app.core.config import settings
from app.core.crypto import decrypt_secret
from app.core.logging import get_logger
from app.core.rate_limit import RateLimit, client_ip, consume_identifier_budget
from app.core.security import create_access_token, verify_password
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    MFAActivateRequest,
    MFADisableRequest,
    MFASetupResponse,
    SessionState,
    SignupRequest,
    TokenResponse,
    UserPublic,
)
from app.schemas.common import Message
from app.services import auth_service, mfa
from app.services.auth_service import AuthError

router = APIRouter(prefix="/auth", tags=["auth"])
log = get_logger("auth.routes")

login_limit = RateLimit(settings.rate_limit_login, scope="login")
signup_limit = RateLimit(settings.rate_limit_signup, scope="signup")


def _http_error(exc: AuthError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


async def _issue_session(
    db: DbSession, response: Response, request: Request, user
) -> TokenResponse:
    """Mint an access token and set the rotating refresh cookie."""
    raw_refresh = await auth_service.issue_refresh_token(
        db,
        user=user,
        user_agent=request.headers.get("user-agent"),
        ip_address=client_ip(request),
    )
    set_auth_cookies(response, refresh_token=raw_refresh)
    access_token, expires_in = create_access_token(
        user_id=user.id, role=user.role.value, email_verified=user.is_email_verified
    )
    return TokenResponse(
        access_token=access_token,
        expires_in=expires_in,
        user=UserPublic.model_validate(user),
    )


@router.post(
    "/signup",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(signup_limit)],
    summary="Create an account",
)
async def signup(
    payload: SignupRequest, request: Request, response: Response, db: DbSession
) -> TokenResponse:
    try:
        user = await auth_service.create_user(
            db,
            email=str(payload.email),
            password=payload.password,
            full_name=payload.full_name,
        )
    except AuthError as exc:
        raise _http_error(exc) from exc

    # Straight into a session. There is no verification step to complete, so the
    # account is usable from this response onwards.
    session = await _issue_session(db, response, request, user)
    await db.commit()
    log.info("signup_success", user_id=str(user.id))
    return session


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(login_limit)],
    summary="Sign in",
)
async def login(
    payload: LoginRequest, request: Request, response: Response, db: DbSession
) -> TokenResponse:
    # Second limiter keyed on the email: a botnet rotating IPs still cannot
    # grind a single account.
    if not await consume_identifier_budget(
        "login", str(payload.email), settings.rate_limit_login
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many sign-in attempts for this account. Try again later.",
        )

    try:
        user = await auth_service.authenticate(
            db,
            email=str(payload.email),
            password=payload.password,
            totp_code=payload.totp_code,
        )
    except AuthError as exc:
        await db.commit()  # persist the failed-attempt counter / lockout
        raise _http_error(exc) from exc

    session = await _issue_session(db, response, request, user)
    await db.commit()
    log.info("login_success", user_id=str(user.id), role=user.role.value)
    return session


@router.post(
    "/refresh",
    response_model=TokenResponse,
    dependencies=[Depends(require_csrf)],
    summary="Exchange the refresh cookie for a new access token",
)
async def refresh(request: Request, response: Response, db: DbSession) -> TokenResponse:
    raw_token = get_refresh_token(request)
    try:
        user, new_raw = await auth_service.rotate_refresh_token(
            db,
            raw_token=raw_token,
            user_agent=request.headers.get("user-agent"),
            ip_address=client_ip(request),
        )
    except AuthError as exc:
        await db.commit()  # a detected reuse revokes the family - persist it
        clear_auth_cookies(response)
        raise _http_error(exc) from exc

    set_auth_cookies(response, refresh_token=new_raw)
    access_token, expires_in = create_access_token(
        user_id=user.id, role=user.role.value, email_verified=user.is_email_verified
    )
    await db.commit()
    return TokenResponse(
        access_token=access_token,
        expires_in=expires_in,
        user=UserPublic.model_validate(user),
    )


@router.post(
    "/logout",
    response_model=Message,
    dependencies=[Depends(require_csrf)],
    summary="Sign out of this device",
)
async def logout(request: Request, response: Response, db: DbSession) -> Message:
    token = request.cookies.get("geo_refresh")
    if token:
        await auth_service.revoke_refresh_token(db, token)
        await db.commit()
    clear_auth_cookies(response)
    return Message(detail="Signed out")


@router.post("/logout-all", response_model=Message, summary="Sign out everywhere")
async def logout_all(user: CurrentUser, response: Response, db: DbSession) -> Message:
    count = await auth_service.revoke_all_sessions(db, user.id)
    await db.commit()
    clear_auth_cookies(response)
    return Message(detail=f"Signed out of {count} session(s)")


@router.get("/me", response_model=SessionState, summary="Current session")
async def me(user: CurrentUser, request: Request) -> SessionState:
    """Who this token authenticates as, and whether an admin is behind it.

    The SPA reads `impersonated_by` to decide whether to show the "viewing as"
    banner. It comes from the token's `act` claim, so it cannot be spoofed by
    the client or drift from the credential actually presented.
    """
    actor = getattr(request.state, "impersonated_by", None)
    return SessionState(
        user=UserPublic.model_validate(user),
        impersonated_by=uuid.UUID(actor) if actor else None,
    )


# --------------------------------------------------------------------------- #
# Password
# --------------------------------------------------------------------------- #
# There is no email verification and no self-service password reset: this
# deployment sends no mail, so a link-based flow would have nowhere to deliver
# to. Changing your own password below still works because it is authenticated
# by the current password rather than by a token. A user who is locked out is
# recovered by an administrator - see admin.reset_user_password.
@router.post(
    "/change-password",
    response_model=Message,
    dependencies=[Depends(forbid_impersonation)],
    summary="Change your password",
)
async def change_password(
    payload: ChangePasswordRequest, user: CurrentUser, response: Response, db: DbSession
) -> Message:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect"
        )
    await auth_service.set_password(db, user=user, new_password=payload.new_password)
    await db.commit()
    clear_auth_cookies(response)
    return Message(detail="Password changed. Please sign in again on your other devices.")


# --------------------------------------------------------------------------- #
# Two-factor authentication (optional; recommended for admins)
# --------------------------------------------------------------------------- #
@router.post(
    "/mfa/setup",
    response_model=MFASetupResponse,
    dependencies=[Depends(forbid_impersonation)],
    summary="Begin TOTP enrolment",
)
async def mfa_setup(user: CurrentUser, db: DbSession) -> MFASetupResponse:
    if user.mfa_enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Two-factor authentication is already enabled",
        )
    secret = mfa.generate_secret()
    # Stored but not yet active: enrolment completes only after a valid code.
    user.mfa_secret = mfa.encrypt_mfa_secret(secret)
    await db.commit()
    return MFASetupResponse(
        secret=secret, otpauth_uri=mfa.provisioning_uri(secret=secret, email=user.email)
    )


@router.post(
    "/mfa/activate",
    response_model=Message,
    dependencies=[Depends(forbid_impersonation)],
    summary="Confirm TOTP enrolment",
)
async def mfa_activate(
    payload: MFAActivateRequest, user: CurrentUser, db: DbSession
) -> Message:
    if not user.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Start setup first"
        )
    secret = decrypt_secret(user.mfa_secret.encode("utf-8"))
    if not mfa.verify_code(secret, payload.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="That code is not valid"
        )
    user.mfa_enabled = True
    await db.commit()
    log.info("mfa_enabled", user_id=str(user.id))
    return Message(detail="Two-factor authentication is on")


@router.post(
    "/mfa/disable",
    response_model=Message,
    dependencies=[Depends(forbid_impersonation)],
    summary="Turn TOTP off",
)
async def mfa_disable(
    payload: MFADisableRequest, user: CurrentUser, db: DbSession
) -> Message:
    # Re-authenticate: a hijacked session must not be able to strip the factor.
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Password is incorrect"
        )
    user.mfa_enabled = False
    user.mfa_secret = None
    await db.commit()
    log.info("mfa_disabled", user_id=str(user.id))
    return Message(detail="Two-factor authentication is off")
