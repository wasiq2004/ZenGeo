"""Parsing an assistant's answer for brand visibility.

Everything here is deterministic string analysis, not a second LLM call. That
keeps the measurement reproducible (the same answer always scores the same) and
means analysing results costs the user nothing on top of the answer itself.

The sentiment read is a lexicon heuristic scoped to the sentences that mention
the brand. It is reported as a heuristic in the UI rather than dressed up as
model-grade sentiment analysis.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlparse

Sentiment = Literal["positive", "neutral", "negative"]

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")

POSITIVE_TERMS = {
    "best", "leading", "excellent", "great", "popular", "recommended", "strong",
    "powerful", "reliable", "trusted", "top", "favourite", "favorite", "robust",
    "intuitive", "affordable", "comprehensive", "well-regarded", "standout",
    "solid", "impressive", "ideal", "preferred", "widely used", "highly rated",
}
NEGATIVE_TERMS = {
    "expensive", "limited", "lacks", "lacking", "poor", "difficult", "confusing",
    "outdated", "buggy", "slow", "unreliable", "complicated", "drawback",
    "downside", "criticised", "criticized", "complaint", "weak", "clunky",
    "steep learning curve", "no longer", "discontinued",
}


#: Trailing words that describe what a company *is* rather than name it.
#: An assistant that says "Acme" about "Acme Analytics" is still mentioning the
#: brand, and scoring that as invisible would be a false negative on the
#: product's headline metric. Only a trailing descriptor is dropped, and only
#: when a distinctive name remains - "General Motors" never becomes "General".
GENERIC_SUFFIXES = {
    "inc", "inc.", "llc", "ltd", "ltd.", "limited", "plc", "corp", "corp.",
    "corporation", "co", "co.", "company", "gmbh", "bv", "ag", "sa", "srl",
    "group", "holdings", "labs", "lab", "software", "technologies", "technology",
    "tech", "solutions", "systems", "analytics", "digital", "media", "studio",
    "studios", "agency", "consulting", "partners", "ventures", "io", "ai", "app",
}

#: A leading token shorter than this is too generic to search for on its own.
MIN_ALIAS_LENGTH = 4


def brand_aliases(name: str) -> list[str]:
    """The name plus, where safe, the same name without a trailing descriptor."""
    cleaned = " ".join(name.split())
    if not cleaned:
        return []

    aliases = [cleaned]
    tokens = cleaned.split()

    # Strip trailing descriptors one at a time, keeping each intermediate form.
    while len(tokens) > 1 and tokens[-1].lower().strip(".,") in GENERIC_SUFFIXES:
        tokens = tokens[:-1]
        candidate = " ".join(tokens)
        if len(candidate) >= MIN_ALIAS_LENGTH and candidate not in aliases:
            aliases.append(candidate)

    return aliases


def _name_pattern(name: str) -> re.Pattern[str] | None:
    """Word-boundary matcher for a brand name and its safe aliases.

    Tolerates punctuation and spacing differences ("Acme Corp." vs "Acme Corp")
    without ever matching inside a longer word - "Acme" must not match
    "Acmetric".
    """
    aliases = brand_aliases(name)
    if not aliases or len(aliases[0]) < 2:
        return None

    bodies: list[str] = []
    for alias in aliases:
        parts = [re.escape(part) for part in re.split(r"[\s\-_.]+", alias) if part]
        if parts:
            bodies.append(r"[\s\-_.]*".join(parts))
    if not bodies:
        return None

    # Longest first so the fuller name wins when both would match.
    bodies.sort(key=len, reverse=True)
    return re.compile(rf"(?<![\w])(?:{'|'.join(bodies)})(?![\w])", re.IGNORECASE)


@dataclass(slots=True)
class BrandAppearance:
    name: str
    mentioned: bool
    first_index: int | None = None
    mention_count: int = 0


@dataclass(slots=True)
class AnswerAnalysis:
    mentioned: bool
    mention_count: int
    cited: bool
    #: Rank among all brands named in the answer, ordered by first appearance.
    #: 1 means the answer led with this brand. None when not mentioned.
    position: int | None
    #: 0.0 (end of answer) to 1.0 (very first characters). None when not mentioned.
    prominence: float | None
    sentiment: Sentiment | None
    competitors_mentioned: list[str] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    excerpt: str = ""


def find_brand(text: str, name: str) -> BrandAppearance:
    pattern = _name_pattern(name)
    if pattern is None or not text:
        return BrandAppearance(name=name, mentioned=False)

    matches = list(pattern.finditer(text))
    if not matches:
        return BrandAppearance(name=name, mentioned=False)

    return BrandAppearance(
        name=name,
        mentioned=True,
        first_index=matches[0].start(),
        mention_count=len(matches),
    )


def domain_is_cited(citations: list[str], website_url: str) -> bool:
    """True when one of the cited URLs belongs to the brand's own domain."""
    own_host = (urlparse(website_url).hostname or "").lower().removeprefix("www.")
    if not own_host:
        return False
    for url in citations:
        host = (urlparse(url).hostname or "").lower().removeprefix("www.")
        if not host:
            continue
        # Accept subdomains (docs.example.com counts as example.com).
        if host == own_host or host.endswith(f".{own_host}"):
            return True
    return False


def read_sentiment(text: str, brand: str) -> Sentiment | None:
    """Lexicon read over just the sentences that name the brand."""
    pattern = _name_pattern(brand)
    if pattern is None:
        return None

    relevant = [s for s in SENTENCE_SPLIT.split(text) if pattern.search(s)]
    if not relevant:
        return None

    window = " ".join(relevant).lower()
    positive = sum(1 for term in POSITIVE_TERMS if term in window)
    negative = sum(1 for term in NEGATIVE_TERMS if term in window)

    if positive > negative:
        return "positive"
    if negative > positive:
        return "negative"
    return "neutral"


def excerpt_around(text: str, brand: str, *, width: int = 320) -> str:
    """The sentence that first mentions the brand, for the results table."""
    pattern = _name_pattern(brand)
    if pattern is not None:
        for sentence in SENTENCE_SPLIT.split(text):
            if pattern.search(sentence):
                clean = " ".join(sentence.split())
                return clean[:width] + ("…" if len(clean) > width else "")

    clean = " ".join(text.split())
    return clean[:width] + ("…" if len(clean) > width else "")


def analyse_answer(
    *,
    text: str,
    brand: str,
    website_url: str,
    competitors: list[str],
    citations: list[str],
) -> AnswerAnalysis:
    """Score one assistant answer for the brand's visibility in it."""
    own = find_brand(text, brand)

    competitor_hits = [find_brand(text, name) for name in competitors]
    named_competitors = [hit.name for hit in competitor_hits if hit.mentioned]

    position: int | None = None
    prominence: float | None = None
    if own.mentioned and own.first_index is not None:
        # Rank by which brand the answer reaches first.
        ordered = sorted(
            [own, *[hit for hit in competitor_hits if hit.mentioned]],
            key=lambda hit: hit.first_index if hit.first_index is not None else 10**9,
        )
        position = next(
            (index for index, hit in enumerate(ordered, start=1) if hit.name == own.name),
            None,
        )
        if text:
            prominence = round(max(0.0, 1 - own.first_index / max(len(text), 1)), 3)

    # A citation counts whether it arrived in a structured citation list or was
    # written into the prose - providers differ, the user's visibility does not.
    own_host = (urlparse(website_url).hostname or "").lower().removeprefix("www.")
    cited = domain_is_cited(citations, website_url) or (
        bool(own_host) and own_host in text.lower()
    )

    return AnswerAnalysis(
        mentioned=own.mentioned,
        mention_count=own.mention_count,
        cited=cited,
        position=position,
        prominence=prominence,
        sentiment=read_sentiment(text, brand) if own.mentioned else None,
        competitors_mentioned=named_competitors,
        citations=citations,
        excerpt=excerpt_around(text, brand),
    )
