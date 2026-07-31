"""Audit intake, progress and result schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator

from app.db.models.audit import AuditStatus
from app.schemas.business import BusinessCreate
from app.schemas.common import ORMModel, StrictModel

UpdateFrequency = Literal["weekly", "monthly", "quarterly", "rarely"]
YesNoUnsure = Literal["yes", "no", "unsure"]
AuditGoal = Literal[
    "increase_visibility",
    "competitor_comparison",
    "health_check",
    "launch_preparation",
]


class AiPresenceAnswers(StrictModel):
    """Section C - self-reported context the crawler cannot determine on its own."""

    checked_ai_mentions: bool = False
    has_wikipedia_or_wikidata: YesNoUnsure = "unsure"
    publishes_original_research: bool = False
    content_update_frequency: UpdateFrequency = "rarely"
    #: Section 2.6 asks for third-party mentions the user knows about but that
    #: are not automatable to discover.
    known_third_party_mentions: str | None = Field(default=None, max_length=2000)


class Questionnaire(StrictModel):
    """Sections C, D and E of the GEO audit questionnaire."""

    ai_presence: AiPresenceAnswers = Field(default_factory=AiPresenceAnswers)

    #: Section D. Deliberately unbounded: the spec forbids a platform cap on
    #: prompt count because every call is billed to the user's own key. System
    #: stability is protected by per-provider worker concurrency instead.
    target_prompts: list[str] = Field(default_factory=list)

    goal: AuditGoal = "health_check"
    goal_detail: str | None = Field(default=None, max_length=1000)

    #: Section B - decides whether "add /llms.txt" is actionable advice for them.
    controls_site_root: bool = True

    @field_validator("target_prompts")
    @classmethod
    def _clean_prompts(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for entry in value:
            prompt = " ".join(entry.split())
            if not prompt:
                continue
            if len(prompt) > 500:
                raise ValueError("Each target prompt must be under 500 characters")
            if prompt not in cleaned:
                cleaned.append(prompt)
        return cleaned


class AuditCreate(StrictModel):
    """Start an audit.

    Either reference a saved business or supply one inline; the wizard sends it
    inline so a first-time user does not need a separate setup step.
    """

    business_id: uuid.UUID | None = None
    business: BusinessCreate | None = None
    questionnaire: Questionnaire = Field(default_factory=Questionnaire)

    @field_validator("business")
    @classmethod
    def _need_one_source(cls, value: BusinessCreate | None, info: Any) -> BusinessCreate | None:
        if value is None and not info.data.get("business_id"):
            raise ValueError("Provide either business_id or a business object")
        return value


class AuditEventPublic(ORMModel):
    id: uuid.UUID
    stage: str
    level: str
    message: str
    created_at: datetime


class AuditSummary(ORMModel):
    id: uuid.UUID
    business_id: uuid.UUID
    status: AuditStatus
    geo_score: float | None
    score_band: str | None
    progress: float
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    # Flattened for list views so the UI does not need a second request.
    business_name: str = ""
    website_url: str = ""
    has_report: bool = False


class AuditDetail(AuditSummary):
    questionnaire_answers: dict[str, Any]
    pillar_scores: dict[str, Any] | None
    share_of_voice_results: dict[str, Any] | None
    recommendations: list[dict[str, Any]] | None
    raw_findings: dict[str, Any] | None
    error_message: str | None
    events: list[AuditEventPublic] = Field(default_factory=list)


class AuditStartResponse(StrictModel):
    audit: AuditSummary
    #: How many LLM calls the Share of Voice pillar will make on the user's own
    #: keys, so the cost is visible before anything is spent.
    planned_llm_calls: int
    providers: list[str]
    message: str
