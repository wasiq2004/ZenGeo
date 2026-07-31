"""Share of Voice: answer analysis and the pillar end to end.

Pillar 7 normally needs a real API key, so it is exercised here against a fake
provider - the one place its scoring, retry and aggregation logic can be pinned
down deterministically.
"""

from __future__ import annotations

import pytest

from app.audit.pillars.share_of_voice import ShareOfVoicePillar
from app.audit.sov_analysis import (
    analyse_answer,
    brand_aliases,
    domain_is_cited,
    find_brand,
    read_sentiment,
)
from app.llm.base import InvalidAPIKey, ProviderRateLimited, ProviderUnavailable
from tests.conftest import FakeProvider, make_context


class TestBrandMatching:
    def test_finds_a_simple_mention(self):
        result = find_brand("I would recommend Acme for this.", "Acme")
        assert result.mentioned
        assert result.mention_count == 1

    def test_is_case_insensitive(self):
        assert find_brand("ACME is popular.", "Acme").mentioned

    def test_does_not_match_inside_a_longer_word(self):
        # "Acme" must not match "Acmetric" - that would inflate every score.
        assert not find_brand("Acmetric is a different company.", "Acme").mentioned

    def test_tolerates_punctuation_and_spacing_differences(self):
        assert find_brand("Try Acme Corp for that.", "Acme Corp.").mentioned
        assert find_brand("Acme-Analytics is good.", "Acme Analytics").mentioned

    def test_counts_repeat_mentions(self):
        result = find_brand("Acme is good. Acme is fast. I like Acme.", "Acme")
        assert result.mention_count == 3

    def test_absent_brand_is_not_mentioned(self):
        assert not find_brand("Try Mixpanel or Amplitude.", "Acme").mentioned

    def test_very_short_names_are_ignored(self):
        # A one-character name would match almost anything.
        assert not find_brand("a lot of text", "a").mentioned


class TestBrandAliases:
    """An assistant that shortens the name is still mentioning the brand.

    Scoring "Acme" as invisible for "Acme Analytics" would be a false negative
    on the headline metric, so trailing descriptors are dropped - but only when
    a distinctive name survives.
    """

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("Acme Analytics", ["Acme Analytics", "Acme"]),
            ("Acme Inc", ["Acme Inc", "Acme"]),
            ("Northwind Software Ltd", ["Northwind Software Ltd", "Northwind Software", "Northwind"]),
            ("Stripe", ["Stripe"]),
        ],
    )
    def test_trailing_descriptors_are_stripped(self, name: str, expected: list[str]):
        assert brand_aliases(name) == expected

    def test_a_shortened_name_counts_as_a_mention(self):
        assert find_brand("I would suggest Acme for that.", "Acme Analytics").mentioned

    def test_the_full_name_still_matches(self):
        assert find_brand("Acme Analytics is solid.", "Acme Analytics").mentioned

    @pytest.mark.parametrize("name", ["General Motors", "Northern Trust", "American Express"])
    def test_meaningful_second_words_are_never_dropped(self, name: str):
        # Matching on "General" or "American" alone would be badly wrong.
        assert brand_aliases(name) == [name]

    def test_a_too_short_remainder_is_not_used_as_an_alias(self):
        # "IBM Solutions" -> "IBM" is 3 chars, below the alias floor, so the
        # full name is required rather than risking a noisy match.
        assert brand_aliases("Ltd Group") == ["Ltd Group"]

    def test_aliases_still_respect_word_boundaries(self):
        assert not find_brand("Acmetric is different.", "Acme Analytics").mentioned


class TestCitationDetection:
    def test_matches_the_exact_domain(self):
        assert domain_is_cited(["https://acme.test/pricing"], "https://acme.test")

    def test_matches_a_subdomain(self):
        assert domain_is_cited(["https://docs.acme.test/guide"], "https://acme.test")

    def test_ignores_www_prefix(self):
        assert domain_is_cited(["https://www.acme.test/"], "https://acme.test")

    def test_does_not_match_a_different_domain(self):
        assert not domain_is_cited(["https://competitor.test/"], "https://acme.test")

    def test_does_not_match_a_lookalike_suffix(self):
        # "notacme.test" ends with "acme.test" as a string but is a different host.
        assert not domain_is_cited(["https://notacme.test/"], "https://acme.test")


class TestSentiment:
    def test_positive_wording_near_the_brand(self):
        assert read_sentiment("Acme is an excellent and reliable choice.", "Acme") == "positive"

    def test_negative_wording_near_the_brand(self):
        assert read_sentiment("Acme is expensive and its UI is clunky.", "Acme") == "negative"

    def test_neutral_when_nothing_is_signalled(self):
        assert read_sentiment("Acme is a product analytics tool.", "Acme") == "neutral"

    def test_only_reads_sentences_that_name_the_brand(self):
        # The praise belongs to Mixpanel; Acme's own sentence is neutral.
        text = "Mixpanel is excellent and powerful. Acme is a product analytics tool."
        assert read_sentiment(text, "Acme") == "neutral"

    def test_returns_none_when_the_brand_is_absent(self):
        assert read_sentiment("Mixpanel is great.", "Acme") is None


class TestAnswerAnalysis:
    def test_position_ranks_by_first_appearance(self):
        text = "Mixpanel is the leader. Amplitude is also strong. Acme is a newer option."
        analysis = analyse_answer(
            text=text,
            brand="Acme",
            website_url="https://acme.test",
            competitors=["Mixpanel", "Amplitude"],
            citations=[],
        )
        assert analysis.mentioned
        assert analysis.position == 3
        assert analysis.competitors_mentioned == ["Mixpanel", "Amplitude"]

    def test_leading_the_answer_is_position_one(self):
        analysis = analyse_answer(
            text="Acme is the best option. Mixpanel is an alternative.",
            brand="Acme",
            website_url="https://acme.test",
            competitors=["Mixpanel"],
            citations=[],
        )
        assert analysis.position == 1
        assert analysis.prominence is not None and analysis.prominence > 0.9

    def test_citation_from_a_structured_list(self):
        analysis = analyse_answer(
            text="Acme is worth a look.",
            brand="Acme",
            website_url="https://acme.test",
            competitors=[],
            citations=["https://acme.test/pricing"],
        )
        assert analysis.cited

    def test_citation_from_a_url_written_into_the_prose(self):
        """Providers differ on where URLs land; the user's visibility does not."""
        analysis = analyse_answer(
            text="See acme.test for details.",
            brand="Acme",
            website_url="https://acme.test",
            competitors=[],
            citations=[],
        )
        assert analysis.cited

    def test_not_mentioned_yields_no_position_or_sentiment(self):
        analysis = analyse_answer(
            text="Mixpanel and Amplitude are the main options.",
            brand="Acme",
            website_url="https://acme.test",
            competitors=["Mixpanel"],
            citations=[],
        )
        assert not analysis.mentioned
        assert analysis.position is None
        assert analysis.sentiment is None
        assert analysis.competitors_mentioned == ["Mixpanel"]

    def test_excerpt_is_the_sentence_that_names_the_brand(self):
        analysis = analyse_answer(
            text="Lots of preamble here. Acme does per-commit attribution. More text.",
            brand="Acme",
            website_url="https://acme.test",
            competitors=[],
            citations=[],
        )
        assert "per-commit attribution" in analysis.excerpt


class TestShareOfVoicePillar:
    @pytest.mark.asyncio
    async def test_skipped_without_any_provider(self):
        ctx = make_context(questionnaire={"target_prompts": ["best analytics tool"]})
        result = await ShareOfVoicePillar([]).run(ctx)

        assert result.skipped
        assert "connect an api key" in (result.skip_reason or "").lower()
        # A skipped pillar must not drag the composite down.
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_skipped_without_any_prompts(self):
        ctx = make_context(questionnaire={"target_prompts": []})
        result = await ShareOfVoicePillar([("fake", FakeProvider())]).run(ctx)

        assert result.skipped
        assert "no target prompts" in (result.skip_reason or "").lower()

    @pytest.mark.asyncio
    async def test_full_visibility_scores_highly(self):
        provider = FakeProvider(
            "Acme is the best choice for small teams. See acme.test for pricing.",
            citations=["https://acme.test/pricing"],
            grounded=True,
        )
        ctx = make_context(
            competitors=["Mixpanel"],
            questionnaire={"target_prompts": ["best analytics tool", "acme alternatives"]},
        )

        result = await ShareOfVoicePillar([("fake", provider)]).run(ctx)

        assert not result.skipped
        assert result.score > 80
        assert result.findings["mention_rate"] == 1.0
        assert result.findings["citation_rate"] == 1.0
        assert result.findings["total_calls"] == 2
        assert len(provider.calls) == 2

    @pytest.mark.asyncio
    async def test_invisible_brand_scores_zero(self):
        provider = FakeProvider("Mixpanel and Amplitude are the leading tools.")
        ctx = make_context(
            competitors=["Mixpanel", "Amplitude"],
            questionnaire={"target_prompts": ["best analytics tool"]},
        )

        result = await ShareOfVoicePillar([("fake", provider)]).run(ctx)

        assert result.score == 0.0
        assert result.findings["mention_rate"] == 0.0
        assert result.findings["competitor_share"] == {"Mixpanel": 1, "Amplitude": 1}

    @pytest.mark.asyncio
    async def test_every_prompt_runs_against_every_provider(self):
        """No cap: the call count is exactly prompts x providers."""
        a, b, c = FakeProvider("Acme"), FakeProvider("Acme"), FakeProvider("Acme")
        prompts = [f"prompt {index}" for index in range(7)]
        ctx = make_context(questionnaire={"target_prompts": prompts})

        result = await ShareOfVoicePillar(
            [("openai", a), ("anthropic", b), ("perplexity", c)]
        ).run(ctx)

        assert result.findings["total_calls"] == 21
        assert len(a.calls) == 7
        assert len(b.calls) == 7
        assert len(c.calls) == 7

    @pytest.mark.asyncio
    async def test_an_invalid_key_is_not_retried(self):
        provider = FakeProvider(raises=InvalidAPIKey("bad key"))
        ctx = make_context(questionnaire={"target_prompts": ["one"]})

        result = await ShareOfVoicePillar([("fake", provider)]).run(ctx)

        # Exactly one attempt: retrying a rejected key just wastes time.
        assert len(provider.calls) == 1
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_transient_failures_are_retried(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "sov_max_retries", 2)
        provider = FakeProvider(raises=ProviderUnavailable("502"))
        ctx = make_context(questionnaire={"target_prompts": ["one"]})

        await ShareOfVoicePillar([("fake", provider)]).run(ctx)

        assert len(provider.calls) == 3  # initial attempt plus two retries

    @pytest.mark.asyncio
    async def test_failed_calls_are_excluded_from_the_rates(self):
        good = FakeProvider("Acme is great.")
        bad = FakeProvider(raises=ProviderRateLimited("429"))
        ctx = make_context(questionnaire={"target_prompts": ["one"]})

        result = await ShareOfVoicePillar([("good", good), ("bad", bad)]).run(ctx)

        # One succeeded, one failed: the mention rate is 1/1, not 1/2.
        assert result.findings["mention_rate"] == 1.0
        assert result.findings["failed_calls"] == 1
        assert result.findings["total_calls"] == 2

    @pytest.mark.asyncio
    async def test_all_calls_failing_is_a_failure_not_a_zero_score(self):
        provider = FakeProvider(raises=InvalidAPIKey("bad key"))
        ctx = make_context(questionnaire={"target_prompts": ["one", "two"]})

        result = await ShareOfVoicePillar([("fake", provider)]).run(ctx)

        assert not result.skipped
        assert "failed" in result.summary.lower()

    @pytest.mark.asyncio
    async def test_recommends_closing_the_gap_when_competitors_win(self):
        provider = FakeProvider("Mixpanel is the clear leader here.")
        ctx = make_context(
            competitors=["Mixpanel"],
            questionnaire={"target_prompts": ["a", "b", "c"]},
        )

        result = await ShareOfVoicePillar([("fake", provider)]).run(ctx)

        ids = {rec.id for rec in result.recommendations}
        assert "improve-ai-mentions" in ids
        assert "close-competitor-gap" in ids

    @pytest.mark.asyncio
    async def test_mentioned_but_never_cited_gets_the_citation_advice(self):
        provider = FakeProvider("Acme is a solid option in this space.")
        ctx = make_context(questionnaire={"target_prompts": ["a", "b"]})

        result = await ShareOfVoicePillar([("fake", provider)]).run(ctx)

        assert result.findings["mention_rate"] == 1.0
        assert result.findings["citation_rate"] == 0.0
        assert "earn-citations" in {rec.id for rec in result.recommendations}
