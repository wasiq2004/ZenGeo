"""Pillar contract: one scored dimension of the GEO score.

Every pillar produces a 0-100 score built from individual checks, so a user can
always trace a number back to the specific thing that was measured. Pillars
never raise: a failure becomes a zero-scored result with an explanation,
because one unreachable page must not lose the other six pillars' work.
"""

from __future__ import annotations

import abc
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar, Literal

if TYPE_CHECKING:
    from app.audit.context import AuditContext

Effort = Literal["quick_win", "medium", "strategic"]
Impact = Literal["high", "medium", "low"]


@dataclass(slots=True)
class PillarCheck:
    """One observable thing that was measured."""

    label: str
    #: True/False for pass/fail; None for informational checks that do not score.
    passed: bool | None
    detail: str
    points: float
    max_points: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Recommendation:
    id: str
    title: str
    detail: str
    pillar: str
    effort: Effort
    impact: Impact
    #: False when the user said they cannot change the site root, so we still
    #: show the advice but flag that someone else has to action it.
    actionable: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PillarResult:
    key: str
    name: str
    score: float
    weight: float
    summary: str
    checks: list[PillarCheck] = field(default_factory=list)
    recommendations: list[Recommendation] = field(default_factory=list)
    #: Everything observed, for the PDF appendix and for debugging.
    findings: dict[str, Any] = field(default_factory=dict)
    skipped: bool = False
    skip_reason: str | None = None
    #: Filled in by the scorer once redistribution is known.
    effective_weight: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "score": round(self.score, 1),
            "weight": self.weight,
            "effective_weight": round(self.effective_weight, 4),
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "summary": self.summary,
            "checks": [check.to_dict() for check in self.checks],
        }


class ScoreBuilder:
    """Accumulates checks and turns them into a 0-100 pillar score."""

    def __init__(self) -> None:
        self.checks: list[PillarCheck] = []

    def add(
        self,
        label: str,
        passed: bool | None,
        detail: str,
        *,
        points: float,
        max_points: float,
    ) -> None:
        self.checks.append(
            PillarCheck(
                label=label,
                passed=passed,
                detail=detail,
                points=round(points, 2),
                max_points=max_points,
            )
        )

    def award(self, label: str, condition: bool, *, weight: float, yes: str, no: str) -> bool:
        """Shorthand for a binary check. Returns the condition for chaining."""
        self.add(
            label,
            condition,
            yes if condition else no,
            points=weight if condition else 0.0,
            max_points=weight,
        )
        return condition

    def note(self, label: str, detail: str) -> None:
        """Record an observation that does not affect the score."""
        self.add(label, None, detail, points=0.0, max_points=0.0)

    @property
    def score(self) -> float:
        total = sum(check.max_points for check in self.checks)
        if total <= 0:
            return 0.0
        earned = sum(check.points for check in self.checks)
        return max(0.0, min(100.0, earned / total * 100))


class Pillar(abc.ABC):
    """One weighted dimension of the composite GEO score."""

    key: ClassVar[str]
    name: ClassVar[str]
    weight: ClassVar[float]
    description: ClassVar[str] = ""

    @abc.abstractmethod
    async def run(self, ctx: AuditContext) -> PillarResult:
        """Measure this dimension. Must not raise - see `failed()`."""

    def result(
        self,
        builder: ScoreBuilder,
        *,
        summary: str,
        findings: dict[str, Any] | None = None,
        recommendations: list[Recommendation] | None = None,
    ) -> PillarResult:
        return PillarResult(
            key=self.key,
            name=self.name,
            score=builder.score,
            weight=self.weight,
            summary=summary,
            checks=builder.checks,
            recommendations=recommendations or [],
            findings=findings or {},
        )

    def failed(self, reason: str) -> PillarResult:
        """A zero score with an explanation, used when the site is unreachable."""
        return PillarResult(
            key=self.key,
            name=self.name,
            score=0.0,
            weight=self.weight,
            summary=reason,
            checks=[PillarCheck(label="Could not evaluate", passed=False, detail=reason, points=0, max_points=1)],
        )

    def skipped_result(self, reason: str) -> PillarResult:
        """Excluded from scoring entirely; its weight is redistributed."""
        return PillarResult(
            key=self.key,
            name=self.name,
            score=0.0,
            weight=self.weight,
            summary=reason,
            skipped=True,
            skip_reason=reason,
        )
