"""Pillar 2 - llms.txt machine-readable brand file (spec 2.2, weight 10%).

A purpose-built file at the site root that tells an assistant who you are and
which pages matter, in the order you want them read.
"""

from __future__ import annotations

import re
from typing import Any

from app.audit.context import AuditContext
from app.audit.pillars.base import Pillar, PillarResult, Recommendation, ScoreBuilder

#: Curly quotes, em/en dashes and ellipses. The spec calls these out because
#: they tokenize awkwardly and are easy to avoid in a file written for machines.
SMART_TYPOGRAPHY = re.compile(r"[‘’“”–—…]")

H1 = re.compile(r"^#\s+(.+)$", re.MULTILINE)
H2 = re.compile(r"^##\s+(.+)$", re.MULTILINE)
BLOCKQUOTE = re.compile(r"^>\s*(.+)$", re.MULTILINE)
MD_LINK_LINE = re.compile(r"^\s*-\s*\[([^\]]+)\]\(([^)]+)\)\s*(?::\s*(.+))?$", re.MULTILINE)

ACCEPTED_MIME = ("text/markdown", "text/plain", "text/x-markdown")


class LlmsTxtPillar(Pillar):
    key = "llms_txt"
    name = "llms.txt Brand File"
    weight = 0.10
    description = "A machine-readable file that onboards an AI assistant to your site."

    async def run(self, ctx: AuditContext) -> PillarResult:
        builder = ScoreBuilder()
        recommendations: list[Recommendation] = []
        findings: dict[str, Any] = {}

        url = ctx.root_url("llms.txt")
        result = await ctx.fetcher.fetch(url)
        findings["llms_txt_url"] = url
        findings["llms_txt_status"] = result.status_code

        # A misconfigured server often returns the HTML 404 page with a 200.
        looks_like_html = "<html" in result.text[:1000].lower()
        exists = result.ok and bool(result.text.strip()) and not looks_like_html
        findings["llms_txt_found"] = exists

        if not exists:
            builder.award(
                "/llms.txt exists",
                False,
                weight=40,
                yes="",
                no=(
                    f"No llms.txt at {url} "
                    + (
                        "(the server returned an HTML page instead)."
                        if looks_like_html
                        else f"(HTTP {result.status_code or 'no response'})."
                    )
                ),
            )
            for label, weight in (
                ("Follows the llms.txt structure", 25),
                ("Has an llms-full.txt companion", 10),
                ("Referenced from robots.txt", 10),
                ("Avoids smart typography", 15),
            ):
                builder.add(label, False, "Not applicable - no llms.txt to check.", points=0, max_points=weight)

            recommendations.append(
                Recommendation(
                    id="create-llms-txt",
                    title="Publish an /llms.txt file",
                    detail=(
                        "llms.txt is a short markdown file at your site root that tells an AI "
                        "assistant what you do and which pages to read. Structure it as:\n\n"
                        f"# {ctx.business_name}\n\n"
                        f"> {ctx.description or 'One sentence describing what you do.'}\n\n"
                        "## Core pages\n"
                        "- [Product](https://example.com/product): What it does and who it is for\n"
                        "- [Pricing](https://example.com/pricing): Plans and what each includes\n\n"
                        "## About\n"
                        "- [Company](https://example.com/about): Founding, team and mission\n\n"
                        "Use straight quotes and hyphens throughout, and reference it from "
                        "robots.txt."
                    ),
                    pillar=self.key,
                    effort="quick_win",
                    impact="high",
                    actionable=bool(ctx.questionnaire.get("controls_site_root", True)),
                )
            )
            return self.result(
                builder,
                summary="No llms.txt file. This is one of the fastest wins available to you.",
                findings=findings,
                recommendations=recommendations,
            )

        content = result.text
        findings["llms_txt_excerpt"] = content[:4000]
        findings["llms_txt_bytes"] = len(content.encode("utf-8"))

        builder.award(
            "/llms.txt exists",
            True,
            weight=40,
            yes=f"Found llms.txt ({len(content.encode('utf-8')):,} bytes).",
            no="",
        )

        # --- MIME type and encoding ---------------------------------------
        mime = result.content_type.split(";")[0].strip().lower()
        findings["llms_txt_content_type"] = result.content_type
        good_mime = any(mime.startswith(accepted) for accepted in ACCEPTED_MIME)
        builder.add(
            "Served as markdown or plain text",
            good_mime,
            (
                f"Content-Type is '{mime or 'not set'}'."
                if good_mime
                else f"Content-Type is '{mime or 'not set'}'; use text/markdown or text/plain."
            ),
            points=5 if good_mime else 0,
            max_points=5,
        )

        # --- Structure (spec 2.2) -----------------------------------------
        h1_matches = H1.findall(content)
        quote_matches = BLOCKQUOTE.findall(content)
        h2_matches = H2.findall(content)
        link_matches = MD_LINK_LINE.findall(content)
        described_links = [m for m in link_matches if m[2]]

        findings["llms_txt_sections"] = h2_matches
        findings["llms_txt_link_count"] = len(link_matches)
        findings["llms_txt_described_link_count"] = len(described_links)

        structure_points = 0.0
        structure_notes: list[str] = []

        if h1_matches:
            structure_points += 5
            structure_notes.append(f"H1 '{h1_matches[0].strip()[:60]}'")
        else:
            structure_notes.append("no H1 site name")

        if quote_matches:
            structure_points += 5
            structure_notes.append("blockquote summary present")
        else:
            structure_notes.append("no blockquote summary")

        if h2_matches:
            structure_points += 5
            structure_notes.append(f"{len(h2_matches)} H2 section(s)")
        else:
            structure_notes.append("no H2 sections")

        if link_matches:
            structure_points += 5
            ratio = len(described_links) / len(link_matches)
            structure_points += 5 * ratio
            structure_notes.append(
                f"{len(link_matches)} link(s), {len(described_links)} with a description"
            )
        else:
            structure_notes.append("no markdown links")

        builder.add(
            "Follows the llms.txt structure",
            structure_points >= 20,
            "Structure check: " + "; ".join(structure_notes) + ".",
            points=round(structure_points, 2),
            max_points=25,
        )

        if structure_points < 25:
            recommendations.append(
                Recommendation(
                    id="fix-llms-txt-structure",
                    title="Tighten your llms.txt structure",
                    detail=(
                        "The spec expects a single H1 with your site name, one blockquote "
                        "summarising what you do, then H2 sections of markdown links where each "
                        "link is followed by a one-line description. Current state: "
                        + "; ".join(structure_notes)
                        + "."
                    ),
                    pillar=self.key,
                    effort="quick_win",
                    impact="medium",
                    actionable=bool(ctx.questionnaire.get("controls_site_root", True)),
                )
            )

        # --- llms-full.txt --------------------------------------------------
        full_url = ctx.root_url("llms-full.txt")
        full = await ctx.fetcher.fetch(full_url)
        has_full = (
            full.ok
            and bool(full.text.strip())
            and "<html" not in full.text[:1000].lower()
        )
        findings["llms_full_txt_found"] = has_full
        builder.award(
            "Has an llms-full.txt companion",
            has_full,
            weight=10,
            yes=f"Found llms-full.txt ({len(full.text.encode('utf-8')):,} bytes).",
            no="No llms-full.txt. This is the single-document version an assistant can read in one pass.",
        )
        if not has_full:
            recommendations.append(
                Recommendation(
                    id="add-llms-full-txt",
                    title="Add an /llms-full.txt",
                    detail=(
                        "llms-full.txt inlines the full text of your key pages into one document, "
                        "so an assistant gets everything without following links. Generate it from "
                        "the same source as llms.txt during your build."
                    ),
                    pillar=self.key,
                    effort="medium",
                    impact="medium",
                    actionable=bool(ctx.questionnaire.get("controls_site_root", True)),
                )
            )

        # --- Referenced from robots.txt -------------------------------------
        robots = await ctx.get_robots()
        referenced = robots.ok and "llms.txt" in robots.text.lower()
        findings["llms_txt_in_robots"] = referenced
        builder.award(
            "Referenced from robots.txt",
            referenced,
            weight=10,
            yes="robots.txt points at llms.txt.",
            no="robots.txt does not mention llms.txt, so crawlers must guess it exists.",
        )
        if not referenced:
            recommendations.append(
                Recommendation(
                    id="reference-llms-txt",
                    title="Reference llms.txt from robots.txt",
                    detail=(
                        f"Add `Sitemap: {url}` to robots.txt so crawlers discover the file "
                        "instead of having to guess the path."
                    ),
                    pillar=self.key,
                    effort="quick_win",
                    impact="low",
                    actionable=bool(ctx.questionnaire.get("controls_site_root", True)),
                )
            )

        # --- Typography -----------------------------------------------------
        smart_chars = SMART_TYPOGRAPHY.findall(content)
        clean_typography = not smart_chars
        findings["llms_txt_smart_char_count"] = len(smart_chars)
        builder.award(
            "Avoids smart typography",
            clean_typography,
            weight=15,
            yes="Uses straight quotes and plain hyphens throughout.",
            no=(
                f"Contains {len(smart_chars)} curly quote / dash character(s). These tokenize "
                "unpredictably; use straight quotes and hyphens."
            ),
        )
        if not clean_typography:
            recommendations.append(
                Recommendation(
                    id="clean-llms-txt-typography",
                    title="Replace smart quotes and dashes in llms.txt",
                    detail=(
                        f"Found {len(smart_chars)} typographic character(s). Replace curly quotes "
                        "with \" and ', and em/en dashes with -. Turn off smart-quote substitution "
                        "in whatever generates the file."
                    ),
                    pillar=self.key,
                    effort="quick_win",
                    impact="low",
                    actionable=bool(ctx.questionnaire.get("controls_site_root", True)),
                )
            )

        score = builder.score
        if score >= 85:
            summary = "Your llms.txt is present and well formed."
        elif score >= 55:
            summary = "You have an llms.txt, but parts of the spec are not being followed."
        else:
            summary = "An llms.txt exists but needs work before it is genuinely useful."

        return self.result(
            builder, summary=summary, findings=findings, recommendations=recommendations
        )
