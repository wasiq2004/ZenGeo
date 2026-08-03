"""Password hashing, JWT issuing/verification, and opaque token helpers."""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from argon2.low_level import Type

from app.core.config import settings

# Argon2id. Parameters follow OWASP's password-storage guidance with headroom:
# 64 MiB of memory per hash makes GPU/ASIC cracking expensive, while staying
# affordable on a modest VPS given login rate limiting.
_hasher = PasswordHasher(
    time_cost=2,
    memory_cost=65536,  # 64 MiB
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,  # Argon2id - the hybrid variant, resistant to both attack classes
)

ALGORITHM = "HS256"
TokenType = Literal["access"]


# --------------------------------------------------------------------------- #
# Passwords
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    """True when the stored hash used weaker parameters than we now require."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except (InvalidHashError, ValueError):
        return True


#: Hashed once at import so `dummy_verify` costs exactly what a real verify costs.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(32))


def dummy_verify() -> None:
    """Burn the same CPU time a real password check would.

    Without this, "unknown email" returns measurably faster than "wrong
    password", which leaks whether an account exists.
    """
    # The verify always fails - burning the CPU cycles is the entire point.
    with contextlib.suppress(Exception):
        _hasher.verify(_DUMMY_HASH, "not-the-password")


# --------------------------------------------------------------------------- #
# Access tokens (JWT, short-lived, sent in the Authorization header)
# --------------------------------------------------------------------------- #
def create_access_token(
    *,
    user_id: uuid.UUID | str,
    role: str,
    email_verified: bool,
    expires_delta: timedelta | None = None,
    impersonated_by: uuid.UUID | str | None = None,
) -> tuple[str, int]:
    """Return ``(jwt, expires_in_seconds)``.

    ``impersonated_by`` marks the token as an admin acting *as* someone else.
    The subject stays the target user - so authorisation, ownership checks and
    row filtering all behave exactly as they do for that user, with no parallel
    code path to keep in step - and the extra claim is what lets the API refuse
    destructive account actions and the UI show the "viewing as" banner.
    """
    now = datetime.now(UTC)
    ttl = expires_delta or timedelta(minutes=settings.access_token_ttl_minutes)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "email_verified": email_verified,
        "type": "access",
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
        "jti": secrets.token_urlsafe(12),
    }
    if impersonated_by is not None:
        payload["act"] = str(impersonated_by)
    token = jwt.encode(payload, settings.jwt_secret_key.get_secret_value(), algorithm=ALGORITHM)
    return token, int(ttl.total_seconds())


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate an access token. Raises ``jwt.PyJWTError`` on failure."""
    payload: dict[str, Any] = jwt.decode(
        token,
        settings.jwt_secret_key.get_secret_value(),
        algorithms=[ALGORITHM],  # pinned: never trust the token's own `alg`
        options={"require": ["exp", "sub", "type"]},
    )
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Wrong token type")
    return payload


# --------------------------------------------------------------------------- #
# Opaque tokens (refresh cookies, email verification, password reset)
# --------------------------------------------------------------------------- #
def generate_opaque_token(nbytes: int = 32) -> str:
    """A high-entropy, URL-safe secret. The raw value is shown to the user once."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """SHA-256 of a token. Only the hash is stored, so a database leak alone
    cannot be replayed. SHA-256 (not Argon2) is right here: these tokens are
    already 256 bits of entropy, so there is nothing to brute-force."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def expiry(*, minutes: int = 0, hours: int = 0, days: int = 0) -> datetime:
    return datetime.now(UTC) + timedelta(minutes=minutes, hours=hours, days=days)
