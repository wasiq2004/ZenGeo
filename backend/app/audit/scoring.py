"""Composite GEO score: weighted pillars, with redistribution for skipped ones.

Spec section 2: the composite is the sum of each pillar's 0-100 score times its
weight. When a pillar is skipped - Share of Voice with no API key connected -
its weight is redistributed proportionally across the rest, so the score stays
on the same 0-100 scale rather than being silently capped at 85.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.audit.pillars.base import PillarResult

#: Spec section 2 band boundaries.
BANDS: tuple[tuple[float, str], ...] = (
    (80.0, "Excellent"),
    (60.0, "Good"),
    (40.0, "Needs Work"),
    (0.0, "Poor"),
)


def band_for(score: float) -> str:
    for threshold, label in BANDS:
        if score >= threshold:
            return label
    return "Poor"


@dataclass(slots=True)
class CompositeScore:
    score: float
    band: str
    #: True when at least one pillar was skipped and weights were redistributed.
    redistributed: bool
    skipped_pillars: list[str]


def compute_composite(results: list[PillarResult]) -> CompositeScore:
    """Combine pillar scores, mutating each result's `effective_weight`."""
    scored = [result for result in results if not result.skipped]
    skipped = [result for result in results if result.skipped]

    for result in skipped:
        result.effective_weight = 0.0

    if not scored:
        return CompositeScore(
            score=0.0,
            band="Poor",
            redistributed=bool(skipped),
            skipped_pillars=[result.key for result in skipped],
        )

    remaining_weight = sum(result.weight for result in scored)
    if remaining_weight <= 0:
        return CompositeScore(0.0, "Poor", bool(skipped), [r.key for r in skipped])

    total = 0.0
    for result in scored:
        # Proportional redistribution: each surviving pillar keeps its share of
        # the weight that is actually in play.
        result.effective_weight = result.weight / remaining_weight
        total += result.score * result.effective_weight

    score = round(max(0.0, min(100.0, total)), 1)
    return CompositeScore(
        score=score,
        band=band_for(score),
        redistributed=bool(skipped),
        skipped_pillars=[result.key for result in skipped],
    )


def prioritise_recommendations(results: list[PillarResult]) -> list[dict[str, object]]:
    """Order fixes by what actually moves the score.

    Ranked by impact first, then by how cheap the fix is, then by how much
    weighted score the pillar is currently leaving on the table - so a
    high-impact quick win on a heavy, low-scoring pillar rises to the top.
    """
    impact_rank = {"high": 0, "medium": 1, "low": 2}
    effort_rank = {"quick_win": 0, "medium": 1, "strategic": 2}

    headroom = {
        result.key: (100 - result.score) * (result.effective_weight or result.weight)
        for result in results
    }

    entries: list[dict[str, object]] = []
    for result in results:
        for rec in result.recommendations:
            entries.append(rec.to_dict())

    entries.sort(
        key=lambda rec: (
            impact_rank.get(str(rec["impact"]), 3),
            effort_rank.get(str(rec["effort"]), 3),
            -headroom.get(str(rec["pillar"]), 0.0),
        )
    )
    return entries
