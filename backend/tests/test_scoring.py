"""Composite scoring: weights, bands and redistribution.

This is the number the whole product is judged on, so it gets the most
arithmetic scrutiny.
"""

from __future__ import annotations

import pytest

from app.audit.pillars import PILLAR_WEIGHTS
from app.audit.pillars.base import PillarResult, Recommendation
from app.audit.scoring import band_for, compute_composite, prioritise_recommendations


def pillar(key: str, score: float, weight: float, *, skipped: bool = False) -> PillarResult:
    return PillarResult(
        key=key,
        name=key.replace("_", " ").title(),
        score=score,
        weight=weight,
        summary="",
        skipped=skipped,
    )


class TestWeights:
    def test_weights_sum_to_one(self):
        # A drifted weight silently rescales every user's score.
        assert sum(PILLAR_WEIGHTS.values()) == pytest.approx(1.0)

    def test_weights_match_the_specification(self):
        assert PILLAR_WEIGHTS == {
            "crawlability": 0.15,
            "llms_txt": 0.10,
            "structured_data": 0.15,
            "extractability": 0.20,
            "evidence": 0.15,
            "entity_authority": 0.10,
            "share_of_voice": 0.15,
        }


class TestBands:
    @pytest.mark.parametrize(
        ("score", "expected"),
        [
            (0, "Poor"),
            (39.9, "Poor"),
            (40, "Needs Work"),
            (59.9, "Needs Work"),
            (60, "Good"),
            (79.9, "Good"),
            (80, "Excellent"),
            (100, "Excellent"),
        ],
    )
    def test_band_boundaries(self, score: float, expected: str):
        assert band_for(score) == expected


class TestComposite:
    def test_all_pillars_perfect_scores_one_hundred(self):
        results = [pillar(key, 100, weight) for key, weight in PILLAR_WEIGHTS.items()]
        composite = compute_composite(results)
        assert composite.score == 100.0
        assert composite.band == "Excellent"
        assert composite.redistributed is False

    def test_all_pillars_zero_scores_zero(self):
        results = [pillar(key, 0, weight) for key, weight in PILLAR_WEIGHTS.items()]
        assert compute_composite(results).score == 0.0

    def test_weighted_average_is_correct(self):
        results = [
            pillar("crawlability", 100, 0.15),
            pillar("llms_txt", 0, 0.10),
            pillar("structured_data", 50, 0.15),
            pillar("extractability", 80, 0.20),
            pillar("evidence", 40, 0.15),
            pillar("entity_authority", 20, 0.10),
            pillar("share_of_voice", 60, 0.15),
        ]
        expected = 100 * 0.15 + 0 * 0.10 + 50 * 0.15 + 80 * 0.20 + 40 * 0.15 + 20 * 0.10 + 60 * 0.15
        assert compute_composite(results).score == pytest.approx(expected, abs=0.05)

    def test_skipped_pillar_weight_is_redistributed_proportionally(self):
        """The headline guarantee: skipping a pillar must not cap the score."""
        results = [pillar(key, 100, weight) for key, weight in PILLAR_WEIGHTS.items()]
        results[-1] = pillar("share_of_voice", 0, 0.15, skipped=True)

        composite = compute_composite(results)

        # Six perfect pillars must still score 100, not 85.
        assert composite.score == 100.0
        assert composite.redistributed is True
        assert composite.skipped_pillars == ["share_of_voice"]

    def test_effective_weights_sum_to_one_after_redistribution(self):
        results = [pillar(key, 50, weight) for key, weight in PILLAR_WEIGHTS.items()]
        results[-1] = pillar("share_of_voice", 0, 0.15, skipped=True)

        compute_composite(results)

        assert sum(r.effective_weight for r in results) == pytest.approx(1.0)
        assert results[-1].effective_weight == 0.0

    def test_redistribution_preserves_relative_weight(self):
        results = [pillar(key, 50, weight) for key, weight in PILLAR_WEIGHTS.items()]
        results[-1] = pillar("share_of_voice", 0, 0.15, skipped=True)
        compute_composite(results)

        crawl = next(r for r in results if r.key == "crawlability")
        extract = next(r for r in results if r.key == "extractability")

        # 0.15 / 0.85 and 0.20 / 0.85 - the ratio between them is unchanged.
        assert crawl.effective_weight == pytest.approx(0.15 / 0.85)
        assert extract.effective_weight == pytest.approx(0.20 / 0.85)
        assert extract.effective_weight / crawl.effective_weight == pytest.approx(0.20 / 0.15)

    def test_multiple_skipped_pillars(self):
        results = [
            pillar("crawlability", 90, 0.15),
            pillar("llms_txt", 0, 0.10, skipped=True),
            pillar("structured_data", 90, 0.15),
            pillar("extractability", 90, 0.20),
            pillar("evidence", 90, 0.15),
            pillar("entity_authority", 0, 0.10, skipped=True),
            pillar("share_of_voice", 0, 0.15, skipped=True),
        ]
        composite = compute_composite(results)
        assert composite.score == 90.0
        assert len(composite.skipped_pillars) == 3

    def test_every_pillar_skipped_does_not_divide_by_zero(self):
        results = [pillar(key, 0, weight, skipped=True) for key, weight in PILLAR_WEIGHTS.items()]
        composite = compute_composite(results)
        assert composite.score == 0.0
        assert composite.band == "Poor"

    def test_score_is_clamped_to_range(self):
        results = [pillar("crawlability", 150, 1.0)]
        assert compute_composite(results).score == 100.0

        results = [pillar("crawlability", -20, 1.0)]
        assert compute_composite(results).score == 0.0


class TestRecommendationPriority:
    def test_high_impact_quick_wins_come_first(self):
        low = PillarResult(
            key="evidence",
            name="Evidence",
            score=50,
            weight=0.15,
            summary="",
            recommendations=[
                Recommendation("a", "Strategic low", "", "evidence", "strategic", "low")
            ],
        )
        high = PillarResult(
            key="crawlability",
            name="Crawlability",
            score=10,
            weight=0.15,
            summary="",
            recommendations=[
                Recommendation("b", "Quick high", "", "crawlability", "quick_win", "high")
            ],
        )
        compute_composite([low, high])

        ordered = prioritise_recommendations([low, high])
        assert [rec["id"] for rec in ordered] == ["b", "a"]

    def test_ties_break_towards_the_pillar_with_more_headroom(self):
        """Two identical fixes: the one on the weaker heavy pillar ranks first."""
        strong = PillarResult(
            key="llms_txt",
            name="llms.txt",
            score=90,
            weight=0.10,
            summary="",
            recommendations=[Recommendation("x", "X", "", "llms_txt", "quick_win", "high")],
        )
        weak = PillarResult(
            key="extractability",
            name="Extractability",
            score=10,
            weight=0.20,
            summary="",
            recommendations=[Recommendation("y", "Y", "", "extractability", "quick_win", "high")],
        )
        compute_composite([strong, weak])

        ordered = prioritise_recommendations([strong, weak])
        assert [rec["id"] for rec in ordered] == ["y", "x"]
