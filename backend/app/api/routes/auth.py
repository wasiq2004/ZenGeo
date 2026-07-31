"""Authentication endpoints.

One login page, one credential set: the response carries the user's ``role`` and
the SPA routes to /app or /admin accordingly. Authorisation is still enforced
per-request on the server - the role in the token is not a client-side decision.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select

from app.api.cookies import (
    clear_auth_cookies,
    get_refresh_token,
    require_csrf,
    set_auth_cookies,
)
from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.crypto import decrypt_secret
from app.core.logging import get_logger
from app.core.rate_limit import RateLimit, client_ip, consume_identifier_budget
from app.core.security import create_access_token, verify_password
from app.db.models.user import TokenPurpose, User
from app.schemas.auth import (
    ChangePasswordRequest,
    EmailVerificationRequest,
    LoginRequest,
    MFAActivateRequest,
    MFADisableRequest,
    MFASetupResponse,
    PasswordResetConfirm,
    PasswordResetRequest,
    ResendVerificationRequest,
    SignupRequest,
    TokenResponse,
    UserPublic,
)
from app.schemas.common import Message
from app.services import auth_service, mfa
from app.services import email as email_service
from app.services.auth_service import AuthError

router = APIRouter(prefix="/auth", tags=["auth"])
log = get_logger("auth.routes")

login_limit = RateLimit(settings.rate_limit_login, scope="login")
signup_limit = RateLimit(settings.rate_limit_signup, scope="signup")
reset_limit = RateLimit(settings.rate_limit_password_reset, scope="password-reset")

#: Deliberately identical whether or not the address exists, so the endpoint
#: cannot be used to discover who has an account.
GENERIC_RESET_RESPONSE = Message(
    detail="If an account exists for that address, a reset link is on its way."
)


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

    # No verification step means no token and no message: the account is already
    # usable, and sending a link that confirms something nothing checks would
    # only fail loudly in the log on a deployment with no mail transport.
    token = (
        await auth_service.create_user_token(
            db, user=user, purpose=TokenPurpose.email_verification
        )
        if settings.require_email_verification
        else None
    )
    session = await _issue_session(db, response, request, user)
    await db.commit()

    # Sent after commit so a mail failure cannot roll back the new account.
    if token is not None:
        await email_service.send_verification_email(
            to=user.email, name=user.full_name, token=token
        )
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


@router.get("/me", response_model=UserPublic, summary="Current account")
async def me(user: CurrentUser) -> UserPublic:
    return UserPublic.model_validate(user)


# --------------------------------------------------------------------------- #
# Email verification
# --------------------------------------------------------------------------- #
@router.post("/verify-email", response_model=UserPublic, summary="Confirm an email address")
async def verify_email(payload: EmailVerificationRequest, db: DbSession) -> UserPublic:
    try:
        user = await auth_service.consume_user_token(
            db, raw_token=payload.token, purpose=TokenPurpose.email_verification
        )
    except AuthError as exc:
        raise _http_error(exc) from exc

    user.is_email_verified = True
    await db.commit()
    log.info("email_verified", user_id=str(user.id))
    return UserPublic.model_validate(user)


@router.post(
    "/resend-verification",
    response_model=Message,
    dependencies=[Depends(reset_limit)],
    summary="Send a new confirmation link",
)
async def resend_verification(payload: ResendVerificationRequest, db: DbSession) -> Message:
    user = await db.scalar(select(User).where(User.email == str(payload.email)))
    if user and not user.is_email_verified and user.is_active:
        token = await auth_service.create_user_token(
            db, user=user, purpose=TokenPurpose.email_verification
        )
        await db.commit()
        await email_service.send_verification_email(
            to=user.email, name=user.full_name, token=token
        )
    # Same response either way - no account enumeration.
    return Message(detail="If that address needs confirming, a new link is on its way.")


# --------------------------------------------------------------------------- #
# Password reset
# --------------------------------------------------------------------------- #
@router.post(
    "/password-reset/request",
    response_model=Message,
    dependencies=[Depends(reset_limit)],
    summary="Request a password reset link",
)
async def request_password_reset(payload: PasswordResetRequest, db: DbSession) -> Message:
    user = await db.scalar(select(User).where(User.email == str(payload.email)))
    if user and user.is_active:
        token = await auth_service.create_user_token(
            db, user=user, purpose=TokenPurpose.password_reset
        )
        await db.commit()
        await email_service.send_password_reset_email(
            to=user.email, name=user.full_name, token=token
        )
    return GENERIC_RESET_RESPONSE


@router.post(
    "/password-reset/confirm",
    response_model=Message,
    dependencies=[Depends(reset_limit)],
    summary="Set a new password using a reset token",
)
async def confirm_password_reset(payload: PasswordResetConfirm, db: DbSession) -> Message:
    try:
        user = await auth_service.consume_user_token(
            db, raw_token=payload.token, purpose=TokenPurpose.password_reset
        )
    except AuthError as exc:
        raise _http_error(exc) from exc

    await auth_service.set_password(db, user=user, new_password=payload.new_password)
    await db.commit()
    return Message(detail="Password updated. You can now sign in.")


@router.post("/change-password", response_model=Message, summary="Change your password")
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
@router.post("/mfa/setup", response_model=MFASetupResponse, summary="Begin TOTP enrolment")
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


@router.post("/mfa/activate", response_model=Message, summary="Confirm TOTP enrolment")
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


@router.post("/mfa/disable", response_model=Message, summary="Turn TOTP off")
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
