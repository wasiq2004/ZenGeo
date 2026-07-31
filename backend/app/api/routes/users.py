"""Account settings: profile, email, GDPR-style data export and deletion."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.api.cookies import clear_auth_cookies
from app.api.deps import CurrentUser, DbSession
from app.core.logging import get_logger
from app.core.security import verify_password
from app.db.models.audit import Audit
from app.db.models.business import Business
from app.db.models.llm_key import LLMApiKey
from app.db.models.user import User
from app.schemas.auth import UserPublic
from app.schemas.common import Message
from app.schemas.user import AccountDeleteRequest, EmailChangeRequest, ProfileUpdate

router = APIRouter(prefix="/users", tags=["users"])
log = get_logger("users")

DELETE_CONFIRMATION = "DELETE"


@router.patch("/me", response_model=UserPublic, summary="Update your profile")
async def update_profile(
    payload: ProfileUpdate, user: CurrentUser, db: DbSession
) -> UserPublic:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await db.commit()
    return UserPublic.model_validate(user)


@router.post("/me/email", response_model=Message, summary="Change your email address")
async def change_email(
    payload: EmailChangeRequest, user: CurrentUser, db: DbSession
) -> Message:
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Password is incorrect"
        )

    new_email = str(payload.new_email)
    if new_email.lower() == user.email.lower():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That is already your email address",
        )

    taken = await db.scalar(select(User).where(User.email == new_email))
    if taken is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="That address is already in use"
        )

    # No confirmation step and no "this address changed" notice - there is no
    # mail transport to carry either. The current password checked above is the
    # only thing standing between a session and a new address on the account,
    # which is why that check is not optional.
    previous_email = user.email
    user.email = new_email
    await db.commit()

    log.info("email_changed", user_id=str(user.id), previous_email=previous_email)
    return Message(detail="Email updated.")


@router.get("/me/export", summary="Download everything we hold about you")
async def export_data(user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """GDPR-style portability export.

    Includes which providers have a key connected, but never the keys - they
    are not recoverable from ciphertext by this endpoint by design.
    """
    businesses = list(
        await db.scalars(select(Business).where(Business.user_id == user.id))
    )
    audits = list(await db.scalars(select(Audit).where(Audit.user_id == user.id)))
    keys = list(await db.scalars(select(LLMApiKey).where(LLMApiKey.user_id == user.id)))

    return {
        "exported_at": datetime.now(UTC).isoformat(),
        "account": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role.value,
            "is_email_verified": user.is_email_verified,
            "created_at": user.created_at.isoformat(),
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        },
        "llm_api_keys": [
            {
                "provider": key.provider.value,
                "label": key.label,
                "key_preview": key.key_preview,
                "model": key.model,
                "created_at": key.created_at.isoformat(),
                "note": "The key itself is encrypted at rest and is never exported.",
            }
            for key in keys
        ],
        "businesses": [
            {
                "id": str(b.id),
                "name": b.name,
                "industry": b.industry,
                "description": b.description,
                "target_audience": b.target_audience,
                "location": b.location,
                "competitors": b.competitors,
                "unique_selling_points": b.unique_selling_points,
                "website_url": b.website_url,
                "key_pages": b.key_pages,
                "cms_platform": b.cms_platform,
                "created_at": b.created_at.isoformat(),
            }
            for b in businesses
        ],
        "audits": [
            {
                "id": str(a.id),
                "business_id": str(a.business_id),
                "status": a.status.value,
                "geo_score": float(a.geo_score) if a.geo_score is not None else None,
                "score_band": a.score_band,
                "questionnaire_answers": a.questionnaire_answers,
                "pillar_scores": a.pillar_scores,
                "share_of_voice_results": a.share_of_voice_results,
                "recommendations": a.recommendations,
                "created_at": a.created_at.isoformat(),
                "completed_at": a.completed_at.isoformat() if a.completed_at else None,
            }
            for a in audits
        ],
    }


@router.post("/me/delete", response_model=Message, summary="Delete your account and all data")
async def delete_account(
    payload: AccountDeleteRequest, user: CurrentUser, response: Response, db: DbSession
) -> Message:
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Password is incorrect"
        )
    if payload.confirmation.strip() != DELETE_CONFIRMATION:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Type {DELETE_CONFIRMATION} exactly to confirm",
        )

    user_id = str(user.id)
    # Every child table cascades from users.id, so this removes businesses,
    # audits, events, sessions and encrypted API keys in one statement.
    await db.delete(user)
    await db.commit()
    clear_auth_cookies(response)
    log.info("account_deleted", user_id=user_id)
    return Message(detail="Your account and all associated data have been deleted.")
