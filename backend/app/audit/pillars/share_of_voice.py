"""Pillar 7 - AI Share of Voice (spec 2.7, weight 15%).

The live-testing pillar. The user's own target prompts are sent to the AI
assistants they connected, using their own API keys, and each answer is checked
for whether the brand appears at all, whether it is cited, how prominently, and
which competitors showed up instead.

There is deliberately **no cap** on prompt count or provider count: the spend
lands on the user's own key, so it is their decision. The only limit here is a
per-provider concurrency semaphore, which exists so one large audit cannot
hammer a provider's rate limit - a stability safeguard, not a usage limit.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.audit.context import AuditContext
from app.audit.pillars.base import Pillar, PillarResult, Recommendation, ScoreBuilder
from app.audit.sov_analysis import analyse_answer
from app.core.config import settings
from app.core.logging import get_logger
from app.llm import (
    InvalidAPIKey,
    LLMProvider,
    ProviderRateLimited,
    ProviderUnavailable,
)

log = get_logger("audit.sov")

#: Roughly a full assistant answer. Long enough to be representative, bounded so
#: a runaway generation cannot burn the user's budget.
ANSWER_MAX_TOKENS = 900


class ShareOfVoicePillar(Pillar):
    key = "share_of_voice"
    name = "AI Share of Voice"
    weight = 0.15
    description = "Whether assistants actually mention and cite you when asked."

    def __init__(self, providers: list[tuple[str, LLMProvider]]) -> None:
        #: (label, adapter) pairs, one per active key the user connected.
        self.providers = providers

    async def run(self, ctx: AuditContext) -> PillarResult:
        prompts: list[str] = list(ctx.questionnaire.get("target_prompts") or [])

        if not self.providers:
            return self.skipped_result(
                "AI Share of Voice not tested - connect an API key to unlock this pillar. "
                "Its weight has been redistributed across the other six pillars."
            )
        if not prompts:
            return self.skipped_result(
                "AI Share of Voice not tested - no target prompts were supplied. "
                "Its weight has been redistributed across the other six pillars."
            )

        total_calls = len(prompts) * len(self.providers)
        await ctx.emit(
            self.key,
            f"Testing {len(prompts)} prompt(s) against {len(self.providers)} provider(s) "
            f"- {total_calls} call(s) on your own API keys.",
            "info",
        )

        results = await self._run_all(ctx, prompts)
        return self._score(ctx, prompts, results)

    async def _run_all(
        self, ctx: AuditContext, prompts: list[str]
    ) -> list[dict[str, Any]]:
        """Run every prompt against every provider, bounded per provider."""
        # One semaphore per provider: providers rate-limit independently, so
        # limiting them independently keeps the slowest from throttling the rest.
        semaphores = {
            label: asyncio.Semaphore(max(1, settings.sov_provider_concurrency))
            for label, _ in self.providers
        }
        completed = 0
        total = len(prompts) * len(self.providers)
        lock = asyncio.Lock()

        async def one_call(prompt: str, label: str, provider: LLMProvider) -> dict[str, Any]:
            nonlocal completed
            async with semaphores[label]:
                record = await self._ask_with_retries(ctx, prompt, label, provider)
            async with lock:
                completed += 1
                if completed % 5 == 0 or completed == total:
                    await ctx.emit(
                        self.key, f"Share of Voice: {completed}/{total} calls complete.", "info"
                    )
            return record

        tasks = [
            one_call(prompt, label, provider)
            for prompt in prompts
            for label, provider in self.providers
        ]
        return list(await asyncio.gather(*tasks))

    async def _ask_with_retries(
        self, ctx: AuditContext, prompt: str, label: str, provider: LLMProvider
    ) -> dict[str, Any]:
        """One prompt against one provider, with backoff on transient failures."""
        base: dict[str, Any] = {
            "prompt": prompt,
            "provider": label,
            "model": provider.model,
            "mentioned": False,
            "cited": False,
            "position": None,
            "prominence": None,
            "sentiment": None,
            "competitors_mentioned": [],
            "citations": [],
            "grounded": False,
            "excerpt": "",
            "error": None,
        }

        attempts = max(1, settings.sov_max_retries + 1)
        for attempt in range(attempts):
            try:
                response = await provider.ask(prompt, max_tokens=ANSWER_MAX_TOKENS)
            except InvalidAPIKey as exc:
                # Never retry: the key is wrong and will stay wrong.
                base["error"] = str(exc)
                return base
            except ProviderRateLimited as exc:
                if attempt == attempts - 1:
                    base["error"] = f"Rate limited: {exc}"
                    return base
                await asyncio.sleep(2**attempt * 2)
                continue
            except ProviderUnavailable as exc:
                if attempt == attempts - 1:
                    base["error"] = str(exc)
                    return base
                await asyncio.sleep(2**attempt)
                continue
            except Exception as exc:
                log.error("sov_call_failed", provider=label, error=type(exc).__name__)
                base["error"] = f"Unexpected error: {type(exc).__name__}"
                return base

            analysis = analyse_answer(
                text=response.text,
                brand=ctx.business_name,
                website_url=ctx.website_url,
                competitors=ctx.competitors,
                citations=response.all_citations(),
            )
            base.update(
                {
                    "model": response.model,
                    "mentioned": analysis.mentioned,
                    "cited": analysis.cited,
                    "position": analysis.position,
                    "prominence": analysis.prominence,
                    "sentiment": analysis.sentiment,
                    "competitors_mentioned": analysis.competitors_mentioned,
                    "citations": analysis.citations[:10],
                    "grounded": response.grounded,
                    "excerpt": analysis.excerpt,
                }
            )
            return base

        return base

    def _score(
        self, ctx: AuditContext, prompts: list[str], results: list[dict[str, Any]]
    ) -> PillarResult:
        builder = ScoreBuilder()
        recommendations: list[Recommendation] = []

        successful = [r for r in results if not r["error"]]
        failed = [r for r in results if r["error"]]

        if not successful:
            reasons = sorted({str(r["error"]) for r in failed})
            return self.failed(
                "Every Share of Voice call failed. " + " ".join(reasons[:3])
            )

        mentions = [r for r in successful if r["mentioned"]]
        citations = [r for r in successful if r["cited"]]
        mention_rate = len(mentions) / len(successful)
        citation_rate = len(citations) / len(successful)

        # Prominence is only meaningful where the brand was mentioned at all.
        positions = [r["position"] for r in mentions if r["position"]]
        average_position = sum(positions) / len(positions) if positions else None

        sentiment_counts = {"positive": 0, "neutral": 0, "negative": 0}
        for record in mentions:
            if record["sentiment"] in sentiment_counts:
                sentiment_counts[record["sentiment"]] += 1

        competitor_counts: dict[str, int] = {}
        for record in successful:
            for name in record["competitors_mentioned"]:
                competitor_counts[name] = competitor_counts.get(name, 0) + 1

        # --- Scoring ------------------------------------------------------
        builder.add(
            "Mentioned in AI answers",
            mention_rate >= 0.5,
            f"Mentioned in {len(mentions)} of {len(successful)} answer(s) ({mention_rate:.0%}).",
            points=round(45 * mention_rate, 2),
            max_points=45,
        )
        builder.add(
            "Cited as a source",
            citation_rate >= 0.3,
            f"Your domain was cited in {len(citations)} of {len(successful)} answer(s) ({citation_rate:.0%}).",
            points=round(25 * citation_rate, 2),
            max_points=25,
        )

        if average_position is not None:
            # First place scores full marks; the value decays with each rank.
            position_score = max(0.0, 1 - (average_position - 1) / 5)
            builder.add(
                "Named early in the answer",
                average_position <= 2,
                f"Average position among brands named: {average_position:.1f}.",
                points=round(15 * position_score, 2),
                max_points=15,
            )
        else:
            builder.add(
                "Named early in the answer",
                False,
                "Never named, so there is no position to measure.",
                points=0,
                max_points=15,
            )

        positive_share = (
            sentiment_counts["positive"] / len(mentions) if mentions else 0.0
        )
        negative_share = sentiment_counts["negative"] / len(mentions) if mentions else 0.0
        builder.add(
            "Described favourably",
            positive_share >= 0.5,
            (
                f"Of {len(mentions)} mention(s): {sentiment_counts['positive']} positive, "
                f"{sentiment_counts['neutral']} neutral, {sentiment_counts['negative']} negative "
                "(keyword heuristic)."
            ),
            points=round(15 * max(0.0, positive_share - negative_share * 0.5), 2),
            max_points=15,
        )

        if competitor_counts:
            leader = max(competitor_counts.items(), key=lambda item: item[1])
            builder.note(
                "Competitors appearing instead",
                f"{leader[0]} appeared in {leader[1]} of {len(successful)} answer(s). "
                + ", ".join(f"{name}: {count}" for name, count in sorted(competitor_counts.items())),
            )

        if failed:
            builder.note(
                "Calls that did not complete",
                f"{len(failed)} of {len(results)} call(s) failed and were excluded from the rates above.",
            )

        # --- Recommendations -----------------------------------------------
        if mention_rate < 0.5:
            recommendations.append(
                Recommendation(
                    id="improve-ai-mentions",
                    title=f"You appear in only {mention_rate:.0%} of answers to your own target prompts",
                    detail=(
                        "Assistants answer these questions without you. The fastest lever is "
                        "publishing a page that answers each target prompt directly, in its own "
                        "words, with a specific and citable claim near the top. Work through the "
                        "prompts you scored lowest on first."
                    ),
                    pillar=self.key,
                    effort="strategic",
                    impact="high",
                )
            )
        if citation_rate < 0.3 and mention_rate > 0:
            recommendations.append(
                Recommendation(
                    id="earn-citations",
                    title="You get mentioned but rarely cited",
                    detail=(
                        "Assistants know of you but link elsewhere. Citations follow content that "
                        "is uniquely worth pointing at: original data, a definitive reference page, "
                        "or a comparison only you can make. Make sure that page is crawlable and "
                        "carries clear structured data."
                    ),
                    pillar=self.key,
                    effort="strategic",
                    impact="high",
                )
            )
        if competitor_counts:
            top = sorted(competitor_counts.items(), key=lambda item: -item[1])[:3]
            beating_you = [name for name, count in top if count > len(mentions)]
            if beating_you:
                recommendations.append(
                    Recommendation(
                        id="close-competitor-gap",
                        title=f"{', '.join(beating_you)} appear more often than you do",
                        detail=(
                            "For each of these competitors, look at what an assistant says about "
                            "them and where it sourced that from. The gap is usually a specific "
                            "page or a third-party listing you do not have, rather than anything "
                            "about the product itself."
                        ),
                        pillar=self.key,
                        effort="medium",
                        impact="high",
                    )
                )
        if negative_share > 0.2:
            recommendations.append(
                Recommendation(
                    id="address-negative-framing",
                    title="Some answers describe you unfavourably",
                    detail=(
                        "Read the excerpts in the Share of Voice table. Negative framing usually "
                        "traces back to an outdated review or a limitation you have since fixed. "
                        "Publish a current, dated page addressing it directly."
                    ),
                    pillar=self.key,
                    effort="medium",
                    impact="medium",
                )
            )

        summary = (
            f"Mentioned in {mention_rate:.0%} and cited in {citation_rate:.0%} of "
            f"{len(successful)} AI answer(s)."
        )

        findings = {
            "tested": True,
            "skip_reason": None,
            "prompts_tested": len(prompts),
            "providers_tested": sorted({r["provider"] for r in results}),
            "total_calls": len(results),
            "failed_calls": len(failed),
            "mention_rate": round(mention_rate, 4),
            "citation_rate": round(citation_rate, 4),
            "average_position": round(average_position, 2) if average_position else None,
            "sentiment_breakdown": sentiment_counts,
            "competitor_share": competitor_counts,
            "results": results,
        }

        return self.result(
            builder, summary=summary, findings=findings, recommendations=recommendations
        )
