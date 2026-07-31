"""Shared schema base classes and small reusable types."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    """Base for every request body.

    ``extra="forbid"`` rejects unknown fields outright, so a typo'd or injected
    property is a 422 rather than being silently ignored.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ORMModel(BaseModel):
    """Base for every response body built from an ORM object."""

    model_config = ConfigDict(from_attributes=True)


class Message(BaseModel):
    detail: str


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int

    @property
    def pages(self) -> int:
        return max(1, -(-self.total // self.page_size))


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1, le=10_000)
    page_size: int = Field(default=25, ge=1, le=100)

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size
