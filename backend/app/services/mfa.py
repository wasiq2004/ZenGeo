"""Optional TOTP second factor.

Recommended for admin accounts. The shared secret is stored Fernet-encrypted
using the same key that protects users' LLM API keys.
"""

from __future__ import annotations

import pyotp

from app.core.crypto import decrypt_secret, encrypt_secret
from app.db.models.user import User

ISSUER = "CheckGEO.ai"


def generate_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(*, secret: str, email: str) -> str:
    """otpauth:// URI for an authenticator app QR code."""
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=ISSUER)


def encrypt_mfa_secret(secret: str) -> str:
    return encrypt_secret(secret).decode("utf-8")


def verify_code(secret: str, code: str) -> bool:
    # valid_window=1 tolerates one 30-second step of clock drift either way.
    return pyotp.TOTP(secret).verify(code.strip().replace(" ", ""), valid_window=1)


def verify_totp(user: User, code: str) -> bool:
    if not user.mfa_secret:
        return False
    try:
        secret = decrypt_secret(user.mfa_secret.encode("utf-8"))
    except Exception:
        return False
    return verify_code(secret, code)
