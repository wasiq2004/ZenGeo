"""BYOK LLM API key endpoints.

Design rule for this whole module: a stored key can never leave the server.
Responses carry `key_preview` only, and there is no read-one endpoint that
returns anything more.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, DbSession
from app.core.rate_limit import RateLimit
from app.llm import LLMError, provider_catalog
from app.schemas.common import Message
from app.schemas.llm_key import (
    LLMKeyCreate,
    LLMKeyCreateResponse,
    LLMKeyPublic,
    LLMKeyUpdate,
    LLMKeyValidationResult,
    ProviderInfo,
)
from app.services import llm_keys as key_service

router = APIRouter(prefix="/llm-keys", tags=["llm-keys"])

# Validation makes an outbound call to a third party; keep it modest.
validate_limit = RateLimit("30/hour", scope="llm-key-validate")


@router.get("/providers", response_model=list[ProviderInfo], summary="Supported AI providers")
async def list_providers(_: CurrentUser) -> list[ProviderInfo]:
    """Read straight from the adapter registry, so a newly added provider shows
    up in the UI without touching this endpoint."""
    return [ProviderInfo.model_validate(entry) for entry in provider_catalog()]


@router.get("", response_model=list[LLMKeyPublic], summary="List your connected keys")
async def list_keys(user: CurrentUser, db: DbSession) -> list[LLMKeyPublic]:
    records = await key_service.list_keys(db, user.id)
    return [LLMKeyPublic.model_validate(record) for record in records]


@router.post(
    "",
    response_model=LLMKeyCreateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(validate_limit)],
    summary="Connect an API key",
)
async def create_key(
    payload: LLMKeyCreate, user: CurrentUser, db: DbSession
) -> LLMKeyCreateResponse:
    validation: LLMKeyValidationResult | None = None

    if payload.validate_before_save:
        try:
            provider = key_service.build_provider(
                provider_name=payload.provider.value,
                api_key=payload.api_key,
                model=payload.model,
                use_web_search=payload.use_web_search,
            )
            result = await provider.validate()
        except LLMError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc

        validation = LLMKeyValidationResult(
            ok=result.ok, message=result.message, available_models=result.available_models
        )
        if not result.ok:
            # Refuse to persist a key we already know does not work.
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.message)

    try:
        record = await key_service.create_key(
            db,
            user_id=user.id,
            provider=payload.provider,
            api_key=payload.api_key,
            label=payload.label,
            model=payload.model,
            use_web_search=payload.use_web_search,
            validated=validation is not None and validation.ok,
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"You already have a {payload.provider.value} key labelled "
                f"'{payload.label}'. Use a different label or remove the old one."
            ),
        ) from None

    return LLMKeyCreateResponse(key=LLMKeyPublic.model_validate(record), validation=validation)


@router.post(
    "/{key_id}/validate",
    response_model=LLMKeyValidationResult,
    dependencies=[Depends(validate_limit)],
    summary="Re-check a stored key",
)
async def validate_key(
    key_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> LLMKeyValidationResult:
    try:
        record = await key_service.get_key(db, user_id=user.id, key_id=key_id)
    except key_service.KeyNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found") from None

    try:
        provider = key_service.provider_from_record(record)
        result = await provider.validate()
    except LLMError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    if result.ok:
        record.last_validated_at = datetime.now(UTC)
        await db.commit()

    return LLMKeyValidationResult(
        ok=result.ok, message=result.message, available_models=result.available_models
    )


@router.patch("/{key_id}", response_model=LLMKeyPublic, summary="Update a key's settings")
async def update_key(
    key_id: uuid.UUID, payload: LLMKeyUpdate, user: CurrentUser, db: DbSession
) -> LLMKeyPublic:
    """Label, model, web-search and active flag are editable. The secret is not
    - replacing a key means deleting it and adding the new one."""
    try:
        record = await key_service.get_key(db, user_id=user.id, key_id=key_id)
    except key_service.KeyNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found") from None

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(record, field, value)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Another key for this provider already uses that label.",
        ) from None

    return LLMKeyPublic.model_validate(record)


@router.delete("/{key_id}", response_model=Message, summary="Remove a key permanently")
async def delete_key(key_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Message:
    try:
        await key_service.delete_key(db, user_id=user.id, key_id=key_id)
    except key_service.KeyNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found") from None
    await db.commit()
    return Message(detail="Key deleted. It is gone from the database entirely.")
