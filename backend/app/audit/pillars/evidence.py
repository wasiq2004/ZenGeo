"""Pillar 5 - Evidence density & E-E-A-T signals (spec 2.5, weight 15%).

Whether your claims are safe for a model to repeat. A model that repeats an
unsourced superlative inherits the risk of being wrong; one that repeats a
dated, attributed statistic does not.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from bs4 import Tag

from app.audit.context import AuditContext, PageSnapshot, attr_text
from app.audit.pillars.base import Pillar, PillarResult, Recommendation, ScoreBuilder

#: Claims that sound impressive and mean nothing. A model cannot verify these,
#: so they are dead weight at best and a credibility signal against you at worst.
VAGUE_SUPERLATIVES = re.compile(
    r"\b(industry[- ]leading|best[- ]in[- ]class|world[- ]class|cutting[- ]edge|"
    r"state[- ]of[- ]the[- ]art|market[- ]leading|revolutionary|game[- ]chang(?:ing|er)|"
    r"unparalleled|second to none|premier|top[- ]tier|leading provider|one[- ]stop shop)\b",
    re.IGNORECASE,
)

#: A statistic: a percentage, a multiplier, a money figure or a big round number.
STATISTIC = re.compile(
    r"(\d+(?:\.\d+)?\s?%|\b\d+(?:\.\d+)?x\b|[$£€]\s?\d[\d,.]*\s?(?:[kmb]|million|billion)?\b"
    r"|\b\d{1,3}(?:,\d{3})+\b)",
    re.IGNORECASE,
)

BYLINE = re.compile(r"\b(by|author|written by|reviewed by)\s+[A-Z][a-z]+", re.IGNORECASE)

ISO_DATE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
LONG_DATE = re.compile(
    r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+(20\d{2})\b",
    re.IGNORECASE,
)

#: Domains that count as external corroboration rather than self-reference.
CITATION_HINTS = (".gov", ".edu", ".org", "doi.org", "arxiv", "pubmed", "who.int", "oecd.org")


def _outbound_citations(page: PageSnapshot, own_host: str) -> list[str]:
    """External links that look like evidence rather than social or nav links."""
    if page.soup is None:
        return []
    social = ("facebook.", "twitter.", "x.com", "instagram.", "linkedin.", "youtube.", "tiktok.", "pinterest.")
    found: list[str] = []
    for anchor in page.soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        href = attr_text(anchor, "href")
        if not href.startswith("http"):
            continue
        host = (urlparse(href).hostname or "").lower()
        if not host or host.endswith(own_host) or own_host.endswith(host):
            continue
        if any(token in host for token in social):
            continue
        if href not in found:
            found.append(href)
    return found


def _latest_date(page: PageSnapshot) -> datetime | None:
    """Most recent publish/update date visible on the page or in its metadata."""
    candidates: list[datetime] = []

    if page.soup is not None:
        for tag in page.soup.find_all("time"):
            if not isinstance(tag, Tag):
                continue
            value = attr_text(tag, "datetime") or tag.get_text(strip=True)
            candidates.extend(_parse_dates(value))
        for prop in ("article:published_time", "article:modified_time", "og:updated_time"):
            meta = page.soup.find("meta", attrs={"property": prop})
            if isinstance(meta, Tag):
                candidates.extend(_parse_dates(attr_text(meta, "content")))

    candidates.extend(_parse_dates(page.visible_text[:6000]))
    now = datetime.now(UTC)
    # Ignore dates in the future - they are almost always parsing noise.
    valid = [d for d in candidates if d <= now]
    return max(valid) if valid else None


def _parse_dates(text: str) -> list[datetime]:
    found: list[datetime] = []
    for year, month, day in ISO_DATE.findall(text or ""):
        try:
            found.append(datetime(int(year), int(month), int(day), tzinfo=UTC))
        except ValueError:
            continue
    for month_name, year in LONG_DATE.findall(text or ""):
        months = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }
        month = months.get(month_name[:3].lower())
        if month:
            found.append(datetime(int(year), month, 1, tzinfo=UTC))
    return found


class EvidencePillar(Pillar):
    key = "evidence"
    name = "Evidence & E-E-A-T"
    weight = 0.15
    description = "Citations, statistics, authorship and freshness — what makes a claim repeatable."

    async def run(self, ctx: AuditContext) -> PillarResult:
        builder = ScoreBuilder()
        recommendations: list[Recommendation] = []
        findings: dict[str, Any] = {}

        pages = [page for page in await ctx.content_pages() if page.soup is not None]
        if not pages:
            return self.failed("Could not load any readable pages to analyse.")

        own_host = ctx.hostname
        combined_text = " ".join(page.visible_text for page in pages)

        # --- Statistics -----------------------------------------------------
        stats = STATISTIC.findall(combined_text)
        per_page_stats = len(stats) / len(pages)
        findings["statistic_count"] = len(stats)
        findings["statistic_examples"] = list(dict.fromkeys(stats))[:8]

        builder.add(
            "Backs claims with statistics",
            per_page_stats >= 3,
            f"Found {len(stats)} statistic(s) across {len(pages)} page(s) ({per_page_stats:.1f} per page).",
            points=round(20 * min(1.0, per_page_stats / 3), 2),
            max_points=20,
        )

        # --- Vague superlatives ------------------------------------------------
        vague = VAGUE_SUPERLATIVES.findall(combined_text)
        unique_vague = list(dict.fromkeys(v.lower() for v in vague))
        findings["vague_superlative_count"] = len(vague)
        findings["vague_superlatives"] = unique_vague[:10]

        # Scored relative to how much real evidence sits alongside them: a
        # superlative next to three statistics reads very differently from one
        # standing alone.
        vague_ratio = len(vague) / max(1, len(stats) + len(vague))
        builder.add(
            "Avoids unverifiable superlatives",
            vague_ratio < 0.3,
            (
                f"Found {len(vague)} vague superlative(s)"
                + (f" ({', '.join(unique_vague[:4])})" if unique_vague else "")
                + f" against {len(stats)} concrete statistic(s)."
            ),
            points=round(15 * max(0.0, 1 - vague_ratio / 0.5), 2),
            max_points=15,
        )
        if vague and vague_ratio >= 0.3:
            recommendations.append(
                Recommendation(
                    id="replace-superlatives",
                    title="Replace vague superlatives with evidence",
                    detail=(
                        f"Phrases like {', '.join(unique_vague[:3])} cannot be verified, so a "
                        "model has no reason to repeat them. Swap each for a specific claim you "
                        "can support: a number, a named customer, a third-party result."
                    ),
                    pillar=self.key,
                    effort="medium",
                    impact="high",
                )
            )

        # --- Outbound citations --------------------------------------------------
        citations: list[str] = []
        for page in pages:
            citations.extend(_outbound_citations(page, own_host))
        unique_citations = list(dict.fromkeys(citations))
        authoritative = [c for c in unique_citations if any(h in c.lower() for h in CITATION_HINTS)]

        findings["outbound_citation_count"] = len(unique_citations)
        findings["authoritative_citation_count"] = len(authoritative)
        findings["citation_examples"] = unique_citations[:8]

        per_page_citations = len(unique_citations) / len(pages)
        builder.add(
            "Cites external sources",
            per_page_citations >= 2,
            (
                f"Found {len(unique_citations)} external source link(s), "
                f"{len(authoritative)} to authoritative domains."
            ),
            points=round(20 * min(1.0, per_page_citations / 2), 2),
            max_points=20,
        )
        if per_page_citations < 2:
            recommendations.append(
                Recommendation(
                    id="cite-sources",
                    title="Cite the sources behind your claims",
                    detail=(
                        "Link out to the research, data or standards your claims rest on. "
                        "Citing sources does not send visitors away — it signals that your page "
                        "is a reliable node in a network of evidence, which is exactly what a "
                        "model is looking for when it decides who to trust."
                    ),
                    pillar=self.key,
                    effort="medium",
                    impact="medium",
                )
            )

        # --- Quotes and attribution -------------------------------------------
        quote_blocks = sum(
            len(page.soup.find_all(["blockquote", "q"])) for page in pages if page.soup
        )
        findings["quote_block_count"] = quote_blocks
        builder.award(
            "Includes quotes or expert attribution",
            quote_blocks > 0,
            weight=10,
            yes=f"Found {quote_blocks} quotation block(s).",
            no="No quotations or attributed expert commentary found.",
        )

        # --- Byline / authorship ------------------------------------------------
        has_byline = bool(BYLINE.search(combined_text))
        schema_author = any(
            page.soup is not None and "author" in str(page.soup.find_all("script", attrs={"type": "application/ld+json"}))
            for page in pages
        )
        authored = has_byline or schema_author
        findings["byline_found"] = authored
        builder.award(
            "Shows who wrote the content",
            authored,
            weight=15,
            yes="Found author attribution on the content pages.",
            no="No author attribution found. Anonymous content is harder for a model to vouch for.",
        )
        if not authored:
            recommendations.append(
                Recommendation(
                    id="add-bylines",
                    title="Attribute your content to a named person",
                    detail=(
                        "Add a byline with the author's name and role, and mark it up with "
                        "Article schema including the `author` property. Expertise is one of the "
                        "E-E-A-T signals, and it cannot be assessed on anonymous content."
                    ),
                    pillar=self.key,
                    effort="quick_win",
                    impact="medium",
                )
            )

        # --- Freshness ----------------------------------------------------------
        dates = [d for d in (_latest_date(page) for page in pages) if d is not None]
        now = datetime.now(UTC)
        if dates:
            newest = max(dates)
            age_days = (now - newest).days
            findings["most_recent_content_date"] = newest.date().isoformat()
            findings["content_age_days"] = age_days

            fresh = age_days <= 365
            builder.add(
                "Content is current",
                fresh,
                (
                    f"Most recent date found is {newest.date().isoformat()} "
                    f"({age_days} days ago)."
                ),
                points=20 if fresh else round(20 * max(0.0, 1 - (age_days - 365) / 730), 2),
                max_points=20,
            )
            if not fresh:
                recommendations.append(
                    Recommendation(
                        id="refresh-content",
                        title="Refresh and re-date your key pages",
                        detail=(
                            f"The newest date found is {newest.date().isoformat()}. Models "
                            "de-prioritise content that looks stale. Review your key pages, update "
                            "what has changed, and publish a visible 'last updated' date backed by "
                            "`dateModified` in your schema."
                        ),
                        pillar=self.key,
                        effort="medium",
                        impact="medium",
                    )
                )
        else:
            findings["most_recent_content_date"] = None
            builder.add(
                "Content is current",
                False,
                "No publish or update dates found on the pages checked.",
                points=0,
                max_points=20,
            )
            recommendations.append(
                Recommendation(
                    id="add-dates",
                    title="Publish visible dates on your content",
                    detail=(
                        "None of the pages checked show a publish or update date. Add a visible "
                        "date and back it with `datePublished` and `dateModified` in Article "
                        "schema, so a model can tell how current the information is."
                    ),
                    pillar=self.key,
                    effort="quick_win",
                    impact="medium",
                )
            )

        # Self-reported context from the questionnaire.
        answers = ctx.questionnaire.get("ai_presence") or {}
        if answers.get("publishes_original_research"):
            builder.note(
                "Original research (self-reported)",
                "You reported publishing original research or data — the strongest evidence signal there is.",
            )
        else:
            recommendations.append(
                Recommendation(
                    id="publish-original-data",
                    title="Publish something only you can publish",
                    detail=(
                        "Original data — a survey, a benchmark, an analysis of your own usage "
                        "numbers — is the most durable way to get cited. It gives assistants a "
                        "reason to name you specifically rather than any competitor."
                    ),
                    pillar=self.key,
                    effort="strategic",
                    impact="high",
                )
            )

        score = builder.score
        if score >= 80:
            summary = "Your claims are well evidenced and attributable."
        elif score >= 50:
            summary = "Some evidence is present, but key trust signals are thin."
        else:
            summary = "Your claims are largely unsupported, which makes them risky to repeat."

        return self.result(
            builder, summary=summary, findings=findings, recommendations=recommendations
        )
