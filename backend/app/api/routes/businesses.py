"""Business profile CRUD. Every query is scoped to the requesting user."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.db.models.audit import Audit
from app.db.models.business import Business
from app.schemas.business import BusinessCreate, BusinessPublic, BusinessUpdate
from app.schemas.common import Message

router = APIRouter(prefix="/businesses", tags=["businesses"])

MAX_BUSINESSES_PER_USER = 50


async def _owned_business(db: DbSession, user_id: uuid.UUID, business_id: uuid.UUID) -> Business:
    business = await db.scalar(
        select(Business).where(Business.id == business_id, Business.user_id == user_id)
    )
    if business is None:
        # Scoped by user_id, so someone else's id is indistinguishable from a
        # nonexistent one - no cross-tenant existence leak.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")
    return business


@router.get("", response_model=list[BusinessPublic], summary="List your businesses")
async def list_businesses(user: CurrentUser, db: DbSession) -> list[BusinessPublic]:
    records = await db.scalars(
        select(Business)
        .where(Business.user_id == user.id)
        .order_by(Business.updated_at.desc())
    )
    return [BusinessPublic.model_validate(record) for record in records]


@router.post(
    "",
    response_model=BusinessPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Add a business",
)
async def create_business(
    payload: BusinessCreate, user: CurrentUser, db: DbSession
) -> BusinessPublic:
    count = await db.scalar(
        select(func.count()).select_from(Business).where(Business.user_id == user.id)
    )
    if (count or 0) >= MAX_BUSINESSES_PER_USER:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"You can store up to {MAX_BUSINESSES_PER_USER} businesses.",
        )

    business = Business(user_id=user.id, **payload.model_dump())
    db.add(business)
    await db.commit()
    return BusinessPublic.model_validate(business)


@router.get("/{business_id}", response_model=BusinessPublic, summary="Get one business")
async def get_business(
    business_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> BusinessPublic:
    return BusinessPublic.model_validate(await _owned_business(db, user.id, business_id))


@router.patch("/{business_id}", response_model=BusinessPublic, summary="Update a business")
async def update_business(
    business_id: uuid.UUID, payload: BusinessUpdate, user: CurrentUser, db: DbSession
) -> BusinessPublic:
    business = await _owned_business(db, user.id, business_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(business, field, value)
    await db.commit()
    return BusinessPublic.model_validate(business)


@router.delete("/{business_id}", response_model=Message, summary="Delete a business")
async def delete_business(
    business_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> Message:
    business = await _owned_business(db, user.id, business_id)
    audit_count = await db.scalar(
        select(func.count()).select_from(Audit).where(Audit.business_id == business_id)
    )
    await db.delete(business)
    await db.commit()

    if audit_count:
        return Message(
            detail=f"Business deleted, along with {audit_count} audit(s) and their reports."
        )
    return Message(detail="Business deleted.")
