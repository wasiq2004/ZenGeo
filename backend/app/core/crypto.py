"""Symmetric encryption for secrets held at rest (users' BYOK LLM API keys).

Fernet = AES-128-CBC + HMAC-SHA256, with the key derived from ``ENCRYPTION_KEY``.
It is authenticated encryption, so a tampered ciphertext fails to decrypt rather
than yielding garbage.

Key rotation: set ``ENCRYPTION_KEY`` to the new key and list previous keys in
``ENCRYPTION_KEY_FALLBACKS`` (comma-separated). MultiFernet decrypts with any of
them and always encrypts with the first, so re-saving a record re-wraps it.
"""

from __future__ import annotations

import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import settings


class EncryptionError(RuntimeError):
    """Raised when a secret cannot be encrypted or decrypted."""


@lru_cache
def _cipher() -> MultiFernet:
    primary = settings.encryption_key.get_secret_value().strip()
    if not primary:
        raise EncryptionError(
            "ENCRYPTION_KEY is not set. Generate one with:\n"
            '  python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        )
    raw_keys = [primary]
    fallbacks = os.getenv("ENCRYPTION_KEY_FALLBACKS", "")
    raw_keys.extend(k.strip() for k in fallbacks.split(",") if k.strip())

    try:
        return MultiFernet([Fernet(k.encode()) for k in raw_keys])
    except (ValueError, TypeError) as exc:
        raise EncryptionError(
            "ENCRYPTION_KEY is not a valid Fernet key (32 url-safe base64 bytes)."
        ) from exc


def encrypt_secret(plaintext: str) -> bytes:
    """Encrypt a secret for storage. Returns ciphertext bytes."""
    if not plaintext:
        raise EncryptionError("Refusing to encrypt an empty secret")
    return _cipher().encrypt(plaintext.encode("utf-8"))


def decrypt_secret(ciphertext: bytes) -> str:
    """Decrypt a stored secret. The plaintext must never be logged or returned
    to a client - callers hold it only long enough to make one API call."""
    try:
        return _cipher().decrypt(ciphertext).decode("utf-8")
    except InvalidToken as exc:
        raise EncryptionError(
            "Stored secret could not be decrypted. ENCRYPTION_KEY has most likely "
            "changed; the affected key must be re-entered by its owner."
        ) from exc


def mask_secret(plaintext: str) -> str:
    """Build the display-safe preview kept alongside the ciphertext.

    ``sk-proj-abcdefghijklmnop`` -> ``sk-proj...mnop``. Enough for a user to tell
    two of their own keys apart, useless to anyone else.
    """
    cleaned = plaintext.strip()
    if len(cleaned) <= 8:
        return "•" * len(cleaned)
    prefix = cleaned[:7] if len(cleaned) > 14 else cleaned[:3]
    return f"{prefix}...{cleaned[-4:]}"
