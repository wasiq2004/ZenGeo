"""Business / brand profile schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from urllib.parse import urlparse, urlunparse

from pydantic import Field, field_validator

from app.schemas.common import ORMModel, StrictModel

MAX_KEY_PAGES = 25
MAX_COMPETITORS = 20


def normalise_url(raw: str) -> str:
    """Accept what a person would type and return a canonical absolute URL.

    Only the shape is checked here. Whether the host is safe to fetch is decided
    at request time by the SSRF guard, because DNS can change between the two.
    """
    value = raw.strip()
    if not value:
        raise ValueError("Enter a website address")
    if "://" not in value:
        value = f"https://{value}"

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http:// and https:// addresses can be audited")
    if not parsed.hostname:
        raise ValueError("That address has no hostname")
    if "." not in parsed.hostname and parsed.hostname != "localhost":
        raise ValueError("That does not look like a full domain name")
    if len(value) > 2000:
        raise ValueError("That address is too long")

    # Drop fragments; they never reach the server and only create duplicates.
    return urlunparse(parsed._replace(fragment=""))


class BusinessBase(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    website_url: str = Field(max_length=2000)
    industry: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    target_audience: str | None = Field(default=None, max_length=2000)
    location: str | None = Field(default=None, max_length=300)
    competitors: list[str] = Field(default_factory=list, max_length=MAX_COMPETITORS)
    unique_selling_points: str | None = Field(default=None, max_length=2000)
    key_pages: list[str] = Field(default_factory=list, max_length=MAX_KEY_PAGES)
    cms_platform: str | None = Field(default=None, max_length=120)

    @field_validator("website_url")
    @classmethod
    def _clean_website(cls, value: str) -> str:
        return normalise_url(value)

    @field_validator("key_pages")
    @classmethod
    def _clean_pages(cls, value: list[str]) -> list[str]:
        seen: list[str] = []
        for entry in value:
            if not entry.strip():
                continue
            url = normalise_url(entry)
            if url not in seen:
                seen.append(url)
        return seen

    @field_validator("competitors")
    @classmethod
    def _clean_competitors(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for entry in value:
            name = entry.strip()
            if name and name not in cleaned:
                cleaned.append(name[:200])
        return cleaned


class BusinessCreate(BusinessBase):
    pass


class BusinessUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    website_url: str | None = Field(default=None, max_length=2000)
    industry: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    target_audience: str | None = Field(default=None, max_length=2000)
    location: str | None = Field(default=None, max_length=300)
    competitors: list[str] | None = Field(default=None, max_length=MAX_COMPETITORS)
    unique_selling_points: str | None = Field(default=None, max_length=2000)
    key_pages: list[str] | None = Field(default=None, max_length=MAX_KEY_PAGES)
    cms_platform: str | None = Field(default=None, max_length=120)

    @field_validator("website_url")
    @classmethod
    def _clean_website(cls, value: str | None) -> str | None:
        return normalise_url(value) if value else None

    @field_validator("key_pages")
    @classmethod
    def _clean_pages(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return BusinessBase._clean_pages(value)


class BusinessPublic(ORMModel):
    id: uuid.UUID
    name: str
    website_url: str
    industry: str | None
    description: str | None
    target_audience: str | None
    location: str | None
    competitors: list[str]
    unique_selling_points: str | None
    key_pages: list[str]
    cms_platform: str | None
    created_at: datetime
    updated_at: datetime
