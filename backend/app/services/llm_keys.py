"""BYOK key storage and provider instantiation.

This module is the only place a plaintext API key exists, and only ever as a
local variable. Callers receive either a configured provider adapter or a
masked view - never the secret.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.crypto import decrypt_secret, encrypt_secret, mask_secret
from app.core.logging import get_logger
from app.db.models.llm_key import LLMApiKey, LLMProviderName
from app.llm import LLMProvider, get_provider_class

log = get_logger("llm_keys")


class KeyNotFound(Exception):
    pass


async def list_keys(db: AsyncSession, user_id: uuid.UUID) -> list[LLMApiKey]:
    result = await db.scalars(
        select(LLMApiKey)
        .where(LLMApiKey.user_id == user_id)
        .order_by(LLMApiKey.provider, LLMApiKey.created_at)
    )
    return list(result)


async def get_key(db: AsyncSession, *, user_id: uuid.UUID, key_id: uuid.UUID) -> LLMApiKey:
    key = await db.scalar(
        select(LLMApiKey).where(LLMApiKey.id == key_id, LLMApiKey.user_id == user_id)
    )
    if key is None:
        # Scoped by user_id, so another user's key id is indistinguishable from
        # one that does not exist.
        raise KeyNotFound(str(key_id))
    return key


def build_provider(
    *, provider_name: str, api_key: str, model: str | None, use_web_search: bool = True
) -> LLMProvider:
    provider_cls = get_provider_class(provider_name)
    return provider_cls(
        api_key,
        model=model,
        timeout=settings.sov_request_timeout_seconds,
        use_web_search=use_web_search,
    )


def provider_from_record(record: LLMApiKey) -> LLMProvider:
    """Decrypt a stored key and return a ready-to-use adapter.

    The plaintext lives only inside the returned adapter instance, which is
    discarded when the audit call completes.
    """
    return build_provider(
        provider_name=record.provider.value,
        api_key=decrypt_secret(record.encrypted_key),
        model=record.model,
        use_web_search=record.use_web_search,
    )


async def create_key(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    provider: LLMProviderName,
    api_key: str,
    label: str,
    model: str | None,
    use_web_search: bool,
    validated: bool,
) -> LLMApiKey:
    record = LLMApiKey(
        user_id=user_id,
        provider=provider,
        encrypted_key=encrypt_secret(api_key),
        key_preview=mask_secret(api_key),
        label=label,
        model=model,
        use_web_search=use_web_search,
        last_validated_at=datetime.now(UTC) if validated else None,
    )
    db.add(record)
    await db.flush()
    # Note the absence of the key itself, and of anything derived from it.
    log.info(
        "llm_key_added",
        user_id=str(user_id),
        provider=provider.value,
        validated=validated,
    )
    return record


async def delete_key(db: AsyncSession, *, user_id: uuid.UUID, key_id: uuid.UUID) -> None:
    """Hard delete - a revoked secret should leave no row behind."""
    record = await get_key(db, user_id=user_id, key_id=key_id)
    await db.delete(record)
    await db.flush()
    log.info("llm_key_deleted", user_id=str(user_id), provider=record.provider.value)


async def active_providers_for_user(
    db: AsyncSession, user_id: uuid.UUID
) -> list[tuple[LLMApiKey, LLMProvider]]:
    """Every usable adapter for a user, one per active key.

    A key whose ciphertext cannot be decrypted (ENCRYPTION_KEY rotated without
    the old key in the fallback list) is skipped with a warning rather than
    failing the whole audit.
    """
    pairs: list[tuple[LLMApiKey, LLMProvider]] = []
    for record in await list_keys(db, user_id):
        if not record.is_active:
            continue
        try:
            pairs.append((record, provider_from_record(record)))
        except Exception as exc:
            log.error(
                "llm_key_unusable",
                key_id=str(record.id),
                provider=record.provider.value,
                error=type(exc).__name__,
            )
    return pairs
