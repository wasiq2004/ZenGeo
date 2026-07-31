"""Pillar 6 - Entity authority & trust graph (spec 2.6, weight 10%).

Whether you exist as a recognised *entity* rather than just a website. A model
resolves "who is X" against a knowledge graph; if you are not in one, it has
nothing to anchor your name to and will happily answer about someone else.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote, urlparse

from app.audit.context import AuditContext
from app.audit.pillars.base import Pillar, PillarResult, Recommendation, ScoreBuilder
from app.core.logging import get_logger

log = get_logger("audit.entity")

#: Profiles that meaningfully corroborate an organisation's identity.
KNOWN_PROFILE_HOSTS = {
    "linkedin.com": "LinkedIn",
    "crunchbase.com": "Crunchbase",
    "wikidata.org": "Wikidata",
    "wikipedia.org": "Wikipedia",
    "x.com": "X",
    "twitter.com": "X",
    "github.com": "GitHub",
    "facebook.com": "Facebook",
    "youtube.com": "YouTube",
    "instagram.com": "Instagram",
    "g.page": "Google Business",
    "trustpilot.com": "Trustpilot",
    "g2.com": "G2",
    "capterra.com": "Capterra",
}

PHONE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")

ORG_TYPES = {"organization", "corporation", "localbusiness", "onlinebusiness", "professionalservice"}


def _normalise_phone(value: str) -> str:
    return re.sub(r"\D", "", value)


class EntityAuthorityPillar(Pillar):
    key = "entity_authority"
    name = "Entity Authority"
    weight = 0.10
    description = "Whether you exist as a recognised entity in the knowledge graph."

    async def run(self, ctx: AuditContext) -> PillarResult:
        builder = ScoreBuilder()
        recommendations: list[Recommendation] = []
        findings: dict[str, Any] = {}

        home = await ctx.homepage()
        if home.soup is None:
            return self.failed("Could not load the homepage to check entity signals.")

        # --- Knowledge-graph presence (best-effort public lookup) -------------
        wikidata_hit = await self._search_wikidata(ctx)
        findings["wikidata_match"] = wikidata_hit

        answers = ctx.questionnaire.get("ai_presence") or {}
        self_reported = answers.get("has_wikipedia_or_wikidata")

        if wikidata_hit:
            builder.add(
                "Present in Wikidata",
                True,
                (
                    f"Found Wikidata entity {wikidata_hit['id']} — "
                    f"\"{wikidata_hit['label']}\": {wikidata_hit.get('description') or 'no description'}."
                ),
                points=25,
                max_points=25,
            )
        elif self_reported == "yes":
            # Trust the user over our fuzzy search, but score it lower - we
            # could not confirm it, and neither can a model searching blind.
            builder.add(
                "Present in Wikidata",
                None,
                "You reported having an entry, but a public search for your business name did not "
                "surface a clear match. Worth checking that the entry is findable by name.",
                points=15,
                max_points=25,
            )
        else:
            builder.add(
                "Present in Wikidata",
                False,
                "No Wikidata entity found for this business name.",
                points=0,
                max_points=25,
            )
            recommendations.append(
                Recommendation(
                    id="create-wikidata-entry",
                    title="Get into Wikidata",
                    detail=(
                        "Wikidata is the structured knowledge base most assistants resolve entity "
                        "questions against, and unlike Wikipedia it has no notability bar for "
                        "organisations that can be sourced. Create an item with your official "
                        "name, website, founding date, industry and any identifiers you hold, "
                        "then link to it from your Organization schema's `sameAs`."
                    ),
                    pillar=self.key,
                    effort="strategic",
                    impact="high",
                )
            )

        # --- sameAs links --------------------------------------------------------
        same_as = self._collect_same_as(home)
        matched_profiles: dict[str, str] = {}
        for url in same_as:
            host = (urlparse(url).hostname or "").lower().removeprefix("www.")
            for known, label in KNOWN_PROFILE_HOSTS.items():
                if host.endswith(known):
                    matched_profiles[label] = url
                    break

        findings["same_as_links"] = same_as
        findings["recognised_profiles"] = sorted(matched_profiles)

        # Three recognised profiles is a reasonable bar for corroboration.
        profile_ratio = min(1.0, len(matched_profiles) / 3)
        builder.add(
            "Links to recognised profiles via sameAs",
            len(matched_profiles) >= 3,
            (
                f"Found {len(matched_profiles)} recognised profile(s) in sameAs"
                + (f": {', '.join(sorted(matched_profiles))}." if matched_profiles else ".")
            ),
            points=round(25 * profile_ratio, 2),
            max_points=25,
        )
        if len(matched_profiles) < 3:
            recommendations.append(
                Recommendation(
                    id="add-sameas-profiles",
                    title="List your other profiles in sameAs",
                    detail=(
                        "The `sameAs` array in your Organization schema is how you tell a model "
                        "'these accounts are also me'. Include LinkedIn, Crunchbase, your Wikidata "
                        "item, X and any review-site profiles. Without it, a model has no way to "
                        "connect corroborating mentions back to your site."
                    ),
                    pillar=self.key,
                    effort="quick_win",
                    impact="high",
                )
            )

        # --- NAP consistency --------------------------------------------------------
        nap = self._check_nap(ctx, home)
        findings.update(nap["findings"])
        builder.add(
            "Consistent name, address and phone",
            nap["consistent"],
            nap["detail"],
            points=nap["points"],
            max_points=25,
        )
        if not nap["consistent"]:
            recommendations.append(
                Recommendation(
                    id="fix-nap-consistency",
                    title="Make your name, address and phone consistent",
                    detail=(
                        "Your contact details should be byte-identical everywhere they appear — "
                        "site footer, Organization schema, and every third-party profile. "
                        "Mismatches make it harder for a model to be confident two mentions "
                        "refer to the same organisation. " + nap["detail"]
                    ),
                    pillar=self.key,
                    effort="quick_win",
                    impact="medium",
                )
            )

        # --- Third-party mentions (self-reported; spec 2.6) --------------------------
        mentions = (answers.get("known_third_party_mentions") or "").strip()
        findings["self_reported_mentions"] = bool(mentions)
        if mentions:
            builder.add(
                "Known third-party mentions",
                True,
                "You listed third-party coverage that corroborates your entity.",
                points=25,
                max_points=25,
            )
        else:
            builder.add(
                "Known third-party mentions",
                False,
                "No third-party coverage reported. Independent mentions are what turn a website "
                "into a recognised entity.",
                points=0,
                max_points=25,
            )
            recommendations.append(
                Recommendation(
                    id="earn-third-party-mentions",
                    title="Earn mentions on sites that already have authority",
                    detail=(
                        "Assistants weight what others say about you more heavily than what you "
                        "say about yourself. Target directory listings in your category, industry "
                        "publications, podcast appearances and roundup posts — anywhere your name "
                        "appears next to a description of what you do."
                    ),
                    pillar=self.key,
                    effort="strategic",
                    impact="high",
                )
            )

        score = builder.score
        if score >= 75:
            summary = "You are recognisable as a distinct entity."
        elif score >= 40:
            summary = "Some entity signals exist, but a model would struggle to confirm who you are."
        else:
            summary = "You are effectively invisible as an entity outside your own website."

        return self.result(
            builder, summary=summary, findings=findings, recommendations=recommendations
        )

    async def _search_wikidata(self, ctx: AuditContext) -> dict[str, Any] | None:
        """Best-effort public Wikidata lookup by business name."""
        if not ctx.business_name.strip():
            return None

        url = (
            "https://www.wikidata.org/w/api.php?action=wbsearchentities"
            f"&search={quote(ctx.business_name)}&language=en&format=json&limit=5&type=item"
        )
        result = await ctx.fetcher.fetch(url)
        if not result.ok:
            log.info("wikidata_lookup_failed", status=result.status_code, error=result.error)
            return None

        try:
            payload = json.loads(result.text)
        except (json.JSONDecodeError, ValueError):
            return None

        target = ctx.business_name.strip().lower()
        for entry in payload.get("search", []):
            label = (entry.get("label") or "").strip()
            if label.lower() == target:
                return {
                    "id": entry.get("id"),
                    "label": label,
                    "description": entry.get("description"),
                    "url": f"https://www.wikidata.org/wiki/{entry.get('id')}",
                }
        return None

    @staticmethod
    def _collect_same_as(home: Any) -> list[str]:
        """sameAs URLs from Organization schema, falling back to footer links."""
        links: list[str] = []
        if home.soup is None:
            return links

        for script in home.soup.find_all("script", attrs={"type": "application/ld+json"}):
            raw = script.string or script.get_text() or ""
            try:
                parsed = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                continue

            stack = parsed if isinstance(parsed, list) else [parsed]
            while stack:
                node = stack.pop()
                if not isinstance(node, dict):
                    continue
                if isinstance(node.get("@graph"), list):
                    stack.extend(node["@graph"])
                same_as = node.get("sameAs")
                if isinstance(same_as, str):
                    links.append(same_as)
                elif isinstance(same_as, list):
                    links.extend(str(item) for item in same_as if isinstance(item, str))

        if not links:
            # No schema, but the footer icons carry the same information.
            footer = home.soup.find("footer")
            if footer:
                for anchor in footer.find_all("a", href=True):
                    if anchor["href"].startswith("http"):
                        links.append(anchor["href"])

        return list(dict.fromkeys(links))

    @staticmethod
    def _check_nap(ctx: AuditContext, home: Any) -> dict[str, Any]:
        """Compare the name/address/phone in schema against the visible page."""
        findings: dict[str, Any] = {}
        schema_name: str | None = None
        schema_phone: str | None = None
        schema_address: str | None = None

        for script in home.soup.find_all("script", attrs={"type": "application/ld+json"}):
            raw = script.string or script.get_text() or ""
            try:
                parsed = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                continue
            stack = parsed if isinstance(parsed, list) else [parsed]
            while stack:
                node = stack.pop()
                if not isinstance(node, dict):
                    continue
                if isinstance(node.get("@graph"), list):
                    stack.extend(node["@graph"])
                raw_type = node.get("@type") or ""
                types = raw_type if isinstance(raw_type, list) else [raw_type]
                if not any(str(t).lower() in ORG_TYPES for t in types):
                    continue
                schema_name = schema_name or node.get("name")
                schema_phone = schema_phone or node.get("telephone")
                address = node.get("address")
                if isinstance(address, dict):
                    schema_address = schema_address or ", ".join(
                        str(address[k])
                        for k in ("streetAddress", "addressLocality", "addressRegion", "postalCode")
                        if address.get(k)
                    )
                elif isinstance(address, str):
                    schema_address = schema_address or address

        page_text = home.visible_text
        page_phones = {_normalise_phone(p) for p in PHONE.findall(page_text)}
        page_phones.discard("")

        findings["schema_name"] = schema_name
        findings["schema_phone"] = schema_phone
        findings["schema_address"] = schema_address
        findings["phone_numbers_on_page"] = len(page_phones)

        points = 0.0
        notes: list[str] = []

        # Name: schema should match what the user calls the business.
        if schema_name:
            if schema_name.strip().lower() == ctx.business_name.strip().lower():
                points += 10
                notes.append("schema name matches your business name")
            else:
                notes.append(
                    f"schema name is '{schema_name}' but you entered '{ctx.business_name}'"
                )
        else:
            notes.append("no organisation name in schema")

        # Phone: schema phone should also appear on the page.
        if schema_phone:
            if _normalise_phone(schema_phone) in page_phones or not page_phones:
                points += 8
                notes.append("schema phone is consistent with the page")
            else:
                notes.append("schema phone does not match any phone number shown on the page")
        elif page_phones:
            notes.append("a phone number is shown but not declared in schema")
        else:
            notes.append("no phone number found")

        if schema_address:
            points += 7
            notes.append("postal address declared in schema")
        else:
            notes.append("no postal address in schema")

        return {
            "consistent": points >= 20,
            "points": points,
            "detail": "NAP check: " + "; ".join(notes) + ".",
            "findings": findings,
        }
