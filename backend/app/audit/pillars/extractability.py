"""Pillar 4 - Content extractability & structure (spec 2.4, weight 20%).

The heaviest pillar, because it decides whether a model can lift a clean,
quotable answer out of your page or has to paraphrase a wall of text and
probably get it wrong.
"""

from __future__ import annotations

import re
import statistics
from typing import Any

from app.audit.context import AuditContext, PageSnapshot
from app.audit.pillars.base import Pillar, PillarResult, Recommendation, ScoreBuilder

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
NUMERIC = re.compile(r"\d")

#: A paragraph longer than this is hard to quote without truncating mid-thought.
LONG_PARAGRAPH_WORDS = 150
#: Quotable claims are short, self-contained and specific.
QUOTABLE_MAX_WORDS = 30
QUOTABLE_MIN_WORDS = 5


def _heading_levels(page: PageSnapshot) -> dict[str, int]:
    if page.soup is None:
        return {}
    return {
        f"h{level}": len(page.soup.find_all(f"h{level}"))
        for level in range(1, 5)
    }


def _paragraph_words(page: PageSnapshot) -> list[int]:
    if page.soup is None:
        return []
    counts = []
    for para in page.soup.find_all("p"):
        words = len(para.get_text(" ", strip=True).split())
        if words >= 10:  # ignore captions and one-line boilerplate
            counts.append(words)
    return counts


def _first_words(page: PageSnapshot, limit: int = 200) -> str:
    return " ".join(page.visible_text.split()[:limit])


def _quotable_sentences(text: str) -> list[str]:
    """Short, specific, self-contained sentences - ideally with a number in them."""
    found = []
    for sentence in SENTENCE_SPLIT.split(text):
        clean = sentence.strip()
        word_count = len(clean.split())
        if QUOTABLE_MIN_WORDS <= word_count <= QUOTABLE_MAX_WORDS and NUMERIC.search(clean):
            found.append(clean)
    return found


class ExtractabilityPillar(Pillar):
    key = "extractability"
    name = "Content Extractability"
    weight = 0.20
    description = "How easily a model can lift a clean answer out of your pages."

    async def run(self, ctx: AuditContext) -> PillarResult:
        builder = ScoreBuilder()
        recommendations: list[Recommendation] = []
        findings: dict[str, Any] = {}

        pages = [page for page in await ctx.content_pages() if page.soup is not None]
        if not pages:
            return self.failed("Could not load any readable pages to analyse.")

        findings["pages_analysed"] = [page.url for page in pages]

        # --- Heading hierarchy ---------------------------------------------
        pages_with_h1 = 0
        pages_with_hierarchy = 0
        per_page_headings: dict[str, dict[str, int]] = {}

        for page in pages:
            levels = _heading_levels(page)
            per_page_headings[page.url] = levels
            if levels.get("h1", 0) >= 1:
                pages_with_h1 += 1
            # Real hierarchy means an H1 and at least a couple of H2 sections.
            if levels.get("h1", 0) >= 1 and levels.get("h2", 0) >= 2:
                pages_with_hierarchy += 1

        findings["headings_per_page"] = per_page_headings
        h1_ratio = pages_with_h1 / len(pages)
        hierarchy_ratio = pages_with_hierarchy / len(pages)

        builder.add(
            "Every page has one H1",
            h1_ratio == 1.0,
            f"{pages_with_h1} of {len(pages)} page(s) have an H1 heading.",
            points=round(10 * h1_ratio, 2),
            max_points=10,
        )
        builder.add(
            "Content is broken into H2 sections",
            hierarchy_ratio >= 0.75,
            f"{pages_with_hierarchy} of {len(pages)} page(s) use a real H1 to H2 structure.",
            points=round(20 * hierarchy_ratio, 2),
            max_points=20,
        )

        if hierarchy_ratio < 0.75:
            recommendations.append(
                Recommendation(
                    id="add-heading-hierarchy",
                    title="Give your pages a real heading structure",
                    detail=(
                        "Assistants use headings to decide which chunk of a page answers a "
                        "question. Give each page one H1 stating the topic, then H2 sections for "
                        "each sub-question a reader might have. Bolded paragraph text is not a "
                        "heading — it carries no structure a parser can see."
                    ),
                    pillar=self.key,
                    effort="quick_win",
                    impact="high",
                )
            )

        # --- Direct answer up front -----------------------------------------
        pages_with_direct_answer = 0
        for page in pages:
            opening = _first_words(page, 200)
            sentences = [s for s in SENTENCE_SPLIT.split(opening) if len(s.split()) >= 8]
            # A usable opening states something concrete within the first
            # couple of sentences rather than easing in with a preamble.
            if sentences and len(sentences[0].split()) <= 45:
                pages_with_direct_answer += 1

        answer_ratio = pages_with_direct_answer / len(pages)
        findings["pages_with_direct_answer"] = pages_with_direct_answer
        builder.add(
            "Answers the question up front",
            answer_ratio >= 0.75,
            (
                f"{pages_with_direct_answer} of {len(pages)} page(s) open with a direct, "
                "self-contained statement in the first 200 words."
            ),
            points=round(20 * answer_ratio, 2),
            max_points=20,
        )
        if answer_ratio < 0.75:
            recommendations.append(
                Recommendation(
                    id="lead-with-the-answer",
                    title="Lead each page with the answer",
                    detail=(
                        "Put a two-to-three sentence direct answer immediately under the H1, "
                        "before any background. Models weight the opening heavily and often quote "
                        "it verbatim. Write it so it stands alone if lifted out of the page."
                    ),
                    pillar=self.key,
                    effort="quick_win",
                    impact="high",
                )
            )

        # --- Lists and tables --------------------------------------------------
        total_lists = sum(len(p.soup.find_all(["ul", "ol"])) for p in pages if p.soup)
        total_tables = sum(len(p.soup.find_all("table")) for p in pages if p.soup)
        pages_with_list = sum(1 for p in pages if p.soup and p.soup.find(["ul", "ol"]))

        findings["list_count"] = total_lists
        findings["table_count"] = total_tables

        list_ratio = pages_with_list / len(pages)
        builder.add(
            "Uses bullet or numbered lists",
            list_ratio >= 0.5,
            f"{pages_with_list} of {len(pages)} page(s) contain a list ({total_lists} total).",
            points=round(12 * list_ratio, 2),
            max_points=12,
        )
        builder.award(
            "Uses comparison tables",
            total_tables > 0,
            weight=8,
            yes=f"Found {total_tables} table(s) — well suited to comparison questions.",
            no="No tables found. Comparison questions are answered far better from a table.",
        )

        if list_ratio < 0.5 or total_tables == 0:
            recommendations.append(
                Recommendation(
                    id="add-lists-and-tables",
                    title="Structure facts as lists and tables",
                    detail=(
                        "Lists and tables survive extraction intact where prose does not. Convert "
                        "feature rundowns into bullet lists, processes into numbered steps, and "
                        "any 'X vs Y' content into a comparison table with a header row."
                    ),
                    pillar=self.key,
                    effort="medium",
                    impact="medium",
                )
            )

        # --- Paragraph length ---------------------------------------------------
        all_paragraphs = [count for page in pages for count in _paragraph_words(page)]
        if all_paragraphs:
            median_words = statistics.median(all_paragraphs)
            long_paragraphs = sum(1 for c in all_paragraphs if c > LONG_PARAGRAPH_WORDS)
            long_ratio = long_paragraphs / len(all_paragraphs)
            findings["median_paragraph_words"] = median_words
            findings["long_paragraph_count"] = long_paragraphs

            readable = long_ratio <= 0.15
            builder.add(
                "Paragraphs stay quotable",
                readable,
                (
                    f"Median paragraph is {median_words:.0f} words; {long_paragraphs} of "
                    f"{len(all_paragraphs)} exceed {LONG_PARAGRAPH_WORDS} words."
                ),
                points=round(15 * max(0.0, 1 - long_ratio / 0.4), 2),
                max_points=15,
            )
            if not readable:
                recommendations.append(
                    Recommendation(
                        id="shorten-paragraphs",
                        title="Break up long paragraphs",
                        detail=(
                            f"{long_paragraphs} paragraph(s) run past {LONG_PARAGRAPH_WORDS} "
                            "words. A model quoting you has to either take the whole block or cut "
                            "it mid-thought. Aim for 40 to 80 words per paragraph, one idea each."
                        ),
                        pillar=self.key,
                        effort="medium",
                        impact="medium",
                    )
                )
        else:
            builder.add(
                "Paragraphs stay quotable",
                False,
                "No substantial paragraphs found to measure.",
                points=0,
                max_points=15,
            )

        # --- Quotable, specific claims ---------------------------------------
        quotable = [s for page in pages for s in _quotable_sentences(page.visible_text)]
        findings["quotable_sentence_count"] = len(quotable)
        findings["quotable_examples"] = quotable[:5]

        per_page = len(quotable) / len(pages)
        enough = per_page >= 3
        builder.add(
            "Contains specific, quotable claims",
            enough,
            (
                f"Found {len(quotable)} short sentence(s) containing a concrete number "
                f"({per_page:.1f} per page)."
            ),
            points=round(15 * min(1.0, per_page / 3), 2),
            max_points=15,
        )
        if not enough:
            recommendations.append(
                Recommendation(
                    id="write-quotable-facts",
                    title="Write single-fact sentences with real numbers",
                    detail=(
                        "Models prefer to quote a short sentence that carries one specific, "
                        "checkable fact. Replace 'we help teams move faster' with 'teams using "
                        "our workflow ship 2.4x more releases per quarter'. One claim, one "
                        "sentence, a number where you have one."
                    ),
                    pillar=self.key,
                    effort="medium",
                    impact="high",
                )
            )

        score = builder.score
        if score >= 80:
            summary = "Your content is well structured for extraction."
        elif score >= 50:
            summary = "Readable, but a model would struggle to lift a clean answer from some pages."
        else:
            summary = "Your content is hard to extract answers from."

        return self.result(
            builder, summary=summary, findings=findings, recommendations=recommendations
        )
