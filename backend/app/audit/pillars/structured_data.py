"""Pillar 3 - Structured data / Schema.org JSON-LD (spec 2.3, weight 15%).

Machine-parseable entity facts. Schema turns "we think this page is about a
company called X" into "this page states it is about a company called X".
"""

from __future__ import annotations

import json
from typing import Any

from app.audit.context import AuditContext, PageSnapshot
from app.audit.pillars.base import Pillar, PillarResult, Recommendation, ScoreBuilder

#: Fields the spec names for Organization, each worth an equal share.
ORGANIZATION_FIELDS = ("name", "logo", "url", "sameAs", "address", "telephone", "description")

ORG_TYPES = {
    "organization",
    "corporation",
    "localbusiness",
    "onlinebusiness",
    "professionalservice",
    "ngo",
    "educationalorganization",
    "governmentorganization",
    "sportsorganization",
    "medicalorganization",
    "store",
    "restaurant",
    "hotel",
}
OFFERING_TYPES = {"product", "service", "softwareapplication", "offer", "menuitem", "course"}
CONTENT_TYPES = {"article", "blogposting", "newsarticle", "howto", "techarticle", "report"}


def _extract_jsonld(page: PageSnapshot) -> list[dict[str, Any]]:
    """All JSON-LD objects on a page, with @graph containers flattened."""
    if page.soup is None:
        return []

    objects: list[dict[str, Any]] = []
    for script in page.soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text() or ""
        if not raw.strip():
            continue
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            # Malformed JSON-LD is worse than none - it is invisible to parsers.
            objects.append({"__parse_error__": True})
            continue

        for node in parsed if isinstance(parsed, list) else [parsed]:
            if not isinstance(node, dict):
                continue
            graph = node.get("@graph")
            if isinstance(graph, list):
                objects.extend(item for item in graph if isinstance(item, dict))
            else:
                objects.append(node)
    return objects


def _types_of(node: dict[str, Any]) -> set[str]:
    raw = node.get("@type") or node.get("type") or []
    values = raw if isinstance(raw, list) else [raw]
    return {str(value).lower().split("/")[-1] for value in values if value}


class StructuredDataPillar(Pillar):
    key = "structured_data"
    name = "Structured Data"
    weight = 0.15
    description = "Schema.org JSON-LD that states your entity facts explicitly."

    async def run(self, ctx: AuditContext) -> PillarResult:
        builder = ScoreBuilder()
        recommendations: list[Recommendation] = []
        findings: dict[str, Any] = {}

        pages = await ctx.content_pages()
        if not pages:
            return self.failed("Could not load any pages to check for structured data.")

        all_nodes: list[dict[str, Any]] = []
        malformed = 0
        for page in pages:
            nodes = _extract_jsonld(page)
            malformed += sum(1 for node in nodes if node.get("__parse_error__"))
            all_nodes.extend(node for node in nodes if not node.get("__parse_error__"))

        types_found = sorted({t for node in all_nodes for t in _types_of(node)})
        findings["pages_checked"] = [page.url for page in pages]
        findings["jsonld_block_count"] = len(all_nodes)
        findings["schema_types_found"] = types_found
        findings["malformed_jsonld_blocks"] = malformed

        builder.award(
            "JSON-LD is present",
            bool(all_nodes),
            weight=15,
            yes=f"Found {len(all_nodes)} JSON-LD object(s) across {len(pages)} page(s).",
            no="No JSON-LD structured data found on any checked page.",
        )

        if malformed:
            builder.add(
                "JSON-LD parses cleanly",
                False,
                f"{malformed} JSON-LD block(s) contain invalid JSON and will be ignored by parsers.",
                points=0,
                max_points=5,
            )
            recommendations.append(
                Recommendation(
                    id="fix-malformed-jsonld",
                    title="Fix invalid JSON-LD",
                    detail=(
                        f"{malformed} script block(s) of type application/ld+json contain invalid "
                        "JSON. Parsers skip them entirely, so the markup does nothing. Validate "
                        "with Google's Rich Results Test or schema.org's validator."
                    ),
                    pillar=self.key,
                    effort="quick_win",
                    impact="high",
                )
            )
        else:
            builder.add(
                "JSON-LD parses cleanly",
                True,
                "All JSON-LD blocks are valid JSON.",
                points=5,
                max_points=5,
            )

        # --- Organization completeness (the heaviest sub-check) -------------
        org_nodes = [node for node in all_nodes if _types_of(node) & ORG_TYPES]
        findings["organization_schema_found"] = bool(org_nodes)

        if org_nodes:
            org = max(org_nodes, key=lambda node: sum(1 for f in ORGANIZATION_FIELDS if node.get(f)))
            present = [f for f in ORGANIZATION_FIELDS if org.get(f)]
            missing = [f for f in ORGANIZATION_FIELDS if not org.get(f)]
            findings["organization_fields_present"] = present
            findings["organization_fields_missing"] = missing

            share = len(present) / len(ORGANIZATION_FIELDS)
            builder.add(
                "Organization schema is complete",
                not missing,
                (
                    f"Organization schema has {len(present)} of {len(ORGANIZATION_FIELDS)} key "
                    f"fields. Present: {', '.join(present)}."
                    + (f" Missing: {', '.join(missing)}." if missing else "")
                ),
                points=round(35 * share, 2),
                max_points=35,
            )
            if missing:
                recommendations.append(
                    Recommendation(
                        id="complete-organization-schema",
                        title=f"Add {len(missing)} missing Organization field(s)",
                        detail=(
                            f"Your Organization schema is missing: {', '.join(missing)}. "
                            "Each field is a fact an assistant can state about you without "
                            "inferring it. `sameAs` matters most — it links your site to your "
                            "LinkedIn, Wikidata and other profiles, which is how a model confirms "
                            "you are the entity it thinks you are."
                        ),
                        pillar=self.key,
                        effort="quick_win",
                        impact="high",
                    )
                )
        else:
            builder.add(
                "Organization schema is complete",
                False,
                "No Organization (or LocalBusiness) schema found.",
                points=0,
                max_points=35,
            )
            recommendations.append(
                Recommendation(
                    id="add-organization-schema",
                    title="Add Organization schema to your homepage",
                    detail=(
                        "Organization schema is the single most valuable structured data for GEO — "
                        "it states your name, logo, URL, description, contact details and the "
                        "other profiles that belong to you. Add a JSON-LD block to your homepage:\n\n"
                        '{\n  "@context": "https://schema.org",\n  "@type": "Organization",\n'
                        f'  "name": "{ctx.business_name}",\n  "url": "{ctx.origin}",\n'
                        '  "logo": "https://.../logo.png",\n'
                        '  "description": "...",\n'
                        '  "sameAs": ["https://www.linkedin.com/company/...", "https://x.com/..."]\n}'
                    ),
                    pillar=self.key,
                    effort="quick_win",
                    impact="high",
                )
            )

        # --- Product / Service ----------------------------------------------
        has_offering = any(_types_of(node) & OFFERING_TYPES for node in all_nodes)
        findings["offering_schema_found"] = has_offering
        builder.award(
            "Product or Service schema",
            has_offering,
            weight=15,
            yes="Found Product/Service schema describing what you sell.",
            no="No Product or Service schema. Assistants have to infer your offering from prose.",
        )
        if not has_offering:
            recommendations.append(
                Recommendation(
                    id="add-product-schema",
                    title="Describe what you sell with Product or Service schema",
                    detail=(
                        "Add Product or Service JSON-LD to your product and pricing pages, "
                        "including name, description, and offers with price and currency where "
                        "you publish pricing. This is what lets an assistant answer 'how much "
                        "does X cost' with your actual number."
                    ),
                    pillar=self.key,
                    effort="medium",
                    impact="medium",
                )
            )

        # --- FAQPage ----------------------------------------------------------
        has_faq = any("faqpage" in _types_of(node) for node in all_nodes)
        findings["faq_schema_found"] = has_faq
        builder.award(
            "FAQPage schema",
            has_faq,
            weight=15,
            yes="Found FAQPage schema.",
            no="No FAQPage schema. FAQ markup maps directly onto the question-answer shape assistants produce.",
        )
        if not has_faq:
            recommendations.append(
                Recommendation(
                    id="add-faq-schema",
                    title="Mark up your FAQs with FAQPage schema",
                    detail=(
                        "FAQ markup is the closest structural match to how an assistant answers: "
                        "a question and a self-contained answer. Take the questions your customers "
                        "actually ask, answer each in two or three sentences, and wrap them in "
                        "FAQPage JSON-LD."
                    ),
                    pillar=self.key,
                    effort="quick_win",
                    impact="high",
                )
            )

        # --- Article / HowTo on content pages ---------------------------------
        has_content_schema = any(_types_of(node) & CONTENT_TYPES for node in all_nodes)
        findings["content_schema_found"] = has_content_schema
        builder.award(
            "Article or HowTo schema",
            has_content_schema,
            weight=15,
            yes="Found Article/HowTo schema on content pages.",
            no="No Article or HowTo schema found on the pages checked.",
        )
        if not has_content_schema:
            recommendations.append(
                Recommendation(
                    id="add-article-schema",
                    title="Add Article or HowTo schema to editorial pages",
                    detail=(
                        "Article schema carries the author, publish date and updated date — the "
                        "signals that let a model decide whether your content is current and "
                        "attributable. HowTo schema does the same for step-by-step guides."
                    ),
                    pillar=self.key,
                    effort="medium",
                    impact="medium",
                )
            )

        score = builder.score
        if score >= 80:
            summary = "Your structured data covers the entity facts assistants look for."
        elif score >= 40:
            summary = "Some structured data is present, but key schema types are missing."
        else:
            summary = "Little or no structured data. Assistants have to guess your entity facts."

        return self.result(
            builder, summary=summary, findings=findings, recommendations=recommendations
        )
