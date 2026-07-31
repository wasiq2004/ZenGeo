"""The six automated pillars, run against canned pages."""

from __future__ import annotations

import pytest

from app.audit.pillars.crawlability import AI_BOTS, CrawlabilityPillar, RobotsRules
from app.audit.pillars.entity_authority import EntityAuthorityPillar
from app.audit.pillars.evidence import EvidencePillar
from app.audit.pillars.extractability import ExtractabilityPillar
from app.audit.pillars.llms_txt import LlmsTxtPillar
from app.audit.pillars.structured_data import StructuredDataPillar
from tests.conftest import make_context

SITE = "https://acme.test"


class TestRobotsParser:
    def test_wildcard_disallow_blocks_everything(self):
        rules = RobotsRules("User-agent: *\nDisallow: /")
        assert not rules.allows("GPTBot")

    def test_empty_disallow_permits_everything(self):
        rules = RobotsRules("User-agent: *\nDisallow:")
        assert rules.allows("GPTBot")

    def test_a_named_agent_group_overrides_the_wildcard(self):
        rules = RobotsRules(
            "User-agent: *\nDisallow: /\n\nUser-agent: GPTBot\nAllow: /"
        )
        assert rules.allows("GPTBot")
        assert not rules.allows("SomeOtherBot")

    def test_blocking_one_named_agent_leaves_others_alone(self):
        rules = RobotsRules("User-agent: GPTBot\nDisallow: /")
        assert not rules.allows("GPTBot")
        assert rules.allows("ClaudeBot")

    def test_longest_matching_rule_wins(self):
        rules = RobotsRules("User-agent: *\nDisallow: /private\nAllow: /private/public")
        assert not rules.allows("GPTBot", "/private/secret")
        assert rules.allows("GPTBot", "/private/public/page")

    def test_allow_beats_disallow_at_equal_specificity(self):
        rules = RobotsRules("User-agent: *\nDisallow: /docs\nAllow: /docs")
        assert rules.allows("GPTBot", "/docs")

    def test_wildcard_patterns(self):
        rules = RobotsRules("User-agent: *\nDisallow: /*.pdf$")
        assert not rules.allows("GPTBot", "/manual.pdf")
        assert rules.allows("GPTBot", "/manual.html")

    def test_sitemaps_are_collected(self):
        rules = RobotsRules("Sitemap: https://acme.test/sitemap.xml\nUser-agent: *\nAllow: /")
        assert rules.sitemaps == ["https://acme.test/sitemap.xml"]

    def test_comments_are_ignored(self):
        rules = RobotsRules("# a comment\nUser-agent: *  # trailing\nDisallow: /")
        assert not rules.allows("GPTBot")

    def test_agent_matching_is_case_insensitive(self):
        rules = RobotsRules("User-agent: gptbot\nDisallow: /")
        assert not rules.allows("GPTBot")


class TestCrawlabilityPillar:
    @pytest.mark.asyncio
    async def test_unreachable_homepage_fails_cleanly(self):
        ctx = make_context(pages={})
        result = await CrawlabilityPillar().run(ctx)

        assert result.score == 0.0
        assert not result.skipped  # a failure, not an exclusion
        assert "could not load" in result.summary.lower()

    @pytest.mark.asyncio
    async def test_blocked_ai_crawlers_are_named(self, rich_html):
        ctx = make_context(
            pages={
                SITE: {"text": rich_html},
                f"{SITE}/robots.txt": {
                    "text": "User-agent: GPTBot\nDisallow: /\n\nUser-agent: ClaudeBot\nDisallow: /",
                    "content_type": "text/plain",
                },
            }
        )
        result = await CrawlabilityPillar().run(ctx)

        blocked = result.findings["ai_bots_blocked"]
        assert "GPTBot" in blocked
        assert "ClaudeBot" in blocked
        assert "PerplexityBot" not in blocked
        assert "unblock-ai-crawlers" in {rec.id for rec in result.recommendations}

    @pytest.mark.asyncio
    async def test_open_robots_scores_well(self, rich_html):
        ctx = make_context(
            pages={
                SITE: {"text": rich_html},
                f"{SITE}/robots.txt": {
                    "text": "User-agent: *\nAllow: /\nSitemap: https://acme.test/sitemap.xml",
                    "content_type": "text/plain",
                },
                f"{SITE}/sitemap.xml": {
                    "text": '<?xml version="1.0"?><urlset><url><loc>https://acme.test/</loc></url></urlset>',
                    "content_type": "application/xml",
                },
            }
        )
        result = await CrawlabilityPillar().run(ctx)

        assert result.findings["ai_bots_blocked"] == []
        assert result.findings["sitemap_found"] is True
        assert result.score > 85

    @pytest.mark.asyncio
    async def test_client_rendered_shell_is_flagged(self, sparse_html):
        ctx = make_context(
            pages={
                SITE: {"text": sparse_html},
                f"{SITE}/robots.txt": {"text": "User-agent: *\nAllow: /", "content_type": "text/plain"},
            }
        )
        result = await CrawlabilityPillar().run(ctx)

        assert "server-render-content" in {rec.id for rec in result.recommendations}

    @pytest.mark.asyncio
    async def test_plain_http_is_penalised(self, rich_html):
        ctx = make_context(
            website_url="http://acme.test",
            pages={
                "http://acme.test": {"text": rich_html, "final_url": "http://acme.test"},
                "http://acme.test/robots.txt": {"text": "User-agent: *\nAllow: /"},
            },
        )
        result = await CrawlabilityPillar().run(ctx)

        assert "enable-https" in {rec.id for rec in result.recommendations}

    def test_the_bot_list_covers_the_major_assistants(self):
        for bot in ("GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended", "CCBot"):
            assert bot in AI_BOTS


class TestLlmsTxtPillar:
    @pytest.mark.asyncio
    async def test_missing_file_scores_zero_and_recommends_creating_one(self):
        ctx = make_context(pages={SITE: {"text": "<html><body>hi</body></html>"}})
        result = await LlmsTxtPillar().run(ctx)

        assert result.score == 0.0
        assert result.findings["llms_txt_found"] is False
        assert "create-llms-txt" in {rec.id for rec in result.recommendations}

    @pytest.mark.asyncio
    async def test_html_error_page_does_not_count_as_a_file(self):
        """A server that returns its 404 page with a 200 must not score."""
        ctx = make_context(
            pages={
                f"{SITE}/llms.txt": {
                    "text": "<html><body>404 Not Found</body></html>",
                    "content_type": "text/html",
                }
            }
        )
        result = await LlmsTxtPillar().run(ctx)

        assert result.findings["llms_txt_found"] is False

    @pytest.mark.asyncio
    async def test_well_formed_file_scores_highly(self):
        content = (
            "# Acme Analytics\n\n"
            "> Product analytics for small engineering teams.\n\n"
            "## Core pages\n"
            "- [Product](https://acme.test/product): What it does and who it is for\n"
            "- [Pricing](https://acme.test/pricing): Plans and what each includes\n\n"
            "## About\n"
            "- [Company](https://acme.test/about): Founding team and mission\n"
        )
        ctx = make_context(
            pages={
                f"{SITE}/llms.txt": {"text": content, "content_type": "text/markdown"},
                f"{SITE}/llms-full.txt": {"text": "# Acme\nEverything inline.", "content_type": "text/markdown"},
                f"{SITE}/robots.txt": {"text": "Sitemap: https://acme.test/llms.txt"},
            }
        )
        result = await LlmsTxtPillar().run(ctx)

        assert result.score > 90
        assert result.findings["llms_txt_link_count"] == 3
        assert result.findings["llms_txt_described_link_count"] == 3

    @pytest.mark.asyncio
    async def test_smart_typography_is_detected(self):
        content = "# Acme\n\n> We’re the “best” — really.\n\n## Pages\n- [A](https://acme.test/a): x\n"
        ctx = make_context(
            pages={f"{SITE}/llms.txt": {"text": content, "content_type": "text/markdown"}}
        )
        result = await LlmsTxtPillar().run(ctx)

        assert result.findings["llms_txt_smart_char_count"] > 0
        assert "clean-llms-txt-typography" in {rec.id for rec in result.recommendations}

    @pytest.mark.asyncio
    async def test_structure_gaps_are_reported(self):
        # Links but no H1 and no blockquote summary.
        ctx = make_context(
            pages={
                f"{SITE}/llms.txt": {
                    "text": "## Pages\n- [A](https://acme.test/a)\n",
                    "content_type": "text/markdown",
                }
            }
        )
        result = await LlmsTxtPillar().run(ctx)

        assert "fix-llms-txt-structure" in {rec.id for rec in result.recommendations}


class TestStructuredDataPillar:
    @pytest.mark.asyncio
    async def test_complete_schema_scores_highly(self, rich_html):
        ctx = make_context(pages={SITE: {"text": rich_html}})
        result = await StructuredDataPillar().run(ctx)

        assert result.findings["organization_schema_found"] is True
        assert result.findings["faq_schema_found"] is True
        assert result.findings["offering_schema_found"] is True
        assert result.score > 85

    @pytest.mark.asyncio
    async def test_no_schema_recommends_adding_organization(self, sparse_html):
        ctx = make_context(pages={SITE: {"text": sparse_html}})
        result = await StructuredDataPillar().run(ctx)

        assert result.score < 20
        assert "add-organization-schema" in {rec.id for rec in result.recommendations}

    @pytest.mark.asyncio
    async def test_malformed_json_ld_is_reported(self):
        html = '<html><head><script type="application/ld+json">{ not json }</script></head><body>x</body></html>'
        ctx = make_context(pages={SITE: {"text": html}})
        result = await StructuredDataPillar().run(ctx)

        assert result.findings["malformed_jsonld_blocks"] == 1
        assert "fix-malformed-jsonld" in {rec.id for rec in result.recommendations}

    @pytest.mark.asyncio
    async def test_graph_containers_are_flattened(self):
        html = """<html><head><script type="application/ld+json">
        {"@context":"https://schema.org","@graph":[
          {"@type":"Organization","name":"Acme","url":"https://acme.test"},
          {"@type":"FAQPage","mainEntity":[]}]}
        </script></head><body>x</body></html>"""
        ctx = make_context(pages={SITE: {"text": html}})
        result = await StructuredDataPillar().run(ctx)

        assert result.findings["organization_schema_found"] is True
        assert result.findings["faq_schema_found"] is True


class TestExtractabilityPillar:
    @pytest.mark.asyncio
    async def test_well_structured_page_scores_highly(self, rich_html):
        ctx = make_context(pages={SITE: {"text": rich_html}})
        result = await ExtractabilityPillar().run(ctx)

        assert result.score > 70
        assert result.findings["list_count"] >= 1
        assert result.findings["table_count"] >= 1

    @pytest.mark.asyncio
    async def test_wall_of_text_is_penalised(self):
        wall = " ".join(["word"] * 400)
        html = f"<html><body><h1>Title</h1><p>{wall}</p></body></html>"
        ctx = make_context(pages={SITE: {"text": html}})
        result = await ExtractabilityPillar().run(ctx)

        ids = {rec.id for rec in result.recommendations}
        assert "shorten-paragraphs" in ids
        assert "add-lists-and-tables" in ids

    @pytest.mark.asyncio
    async def test_quotable_numeric_claims_are_counted(self, rich_html):
        ctx = make_context(pages={SITE: {"text": rich_html}})
        result = await ExtractabilityPillar().run(ctx)

        assert result.findings["quotable_sentence_count"] >= 1


class TestEvidencePillar:
    @pytest.mark.asyncio
    async def test_evidence_rich_page_scores_well(self, rich_html):
        ctx = make_context(pages={SITE: {"text": rich_html}})
        result = await EvidencePillar().run(ctx)

        assert result.findings["statistic_count"] >= 2
        assert result.findings["authoritative_citation_count"] >= 1
        assert result.findings["byline_found"] is True
        assert result.score > 60

    @pytest.mark.asyncio
    async def test_vague_superlatives_without_evidence_are_flagged(self):
        html = """<html><body><h1>Us</h1>
        <p>We are the industry-leading, best-in-class, world-class provider.</p>
        <p>Our cutting-edge, state-of-the-art platform is second to none.</p>
        </body></html>"""
        ctx = make_context(pages={SITE: {"text": html}})
        result = await EvidencePillar().run(ctx)

        assert result.findings["vague_superlative_count"] >= 5
        assert "replace-superlatives" in {rec.id for rec in result.recommendations}

    @pytest.mark.asyncio
    async def test_missing_dates_are_flagged(self, sparse_html):
        ctx = make_context(pages={SITE: {"text": sparse_html}})
        result = await EvidencePillar().run(ctx)

        assert result.findings["most_recent_content_date"] is None
        assert "add-dates" in {rec.id for rec in result.recommendations}


class TestEntityAuthorityPillar:
    @pytest.mark.asyncio
    async def test_sameas_profiles_are_recognised(self, rich_html):
        ctx = make_context(pages={SITE: {"text": rich_html}})
        result = await EntityAuthorityPillar().run(ctx)

        recognised = result.findings["recognised_profiles"]
        assert "LinkedIn" in recognised
        assert "Crunchbase" in recognised
        assert "X" in recognised

    @pytest.mark.asyncio
    async def test_no_entity_signals_recommends_wikidata(self, sparse_html):
        ctx = make_context(pages={SITE: {"text": sparse_html}})
        result = await EntityAuthorityPillar().run(ctx)

        ids = {rec.id for rec in result.recommendations}
        assert "create-wikidata-entry" in ids
        assert "add-sameas-profiles" in ids

    @pytest.mark.asyncio
    async def test_nap_mismatch_is_detected(self):
        html = """<html><head><script type="application/ld+json">
        {"@context":"https://schema.org","@type":"Organization",
         "name":"A Completely Different Name","telephone":"+44 20 1111 1111"}
        </script></head><body><p>Call us on +44 20 9999 9999</p></body></html>"""
        ctx = make_context(pages={SITE: {"text": html}})
        result = await EntityAuthorityPillar().run(ctx)

        assert "fix-nap-consistency" in {rec.id for rec in result.recommendations}

    @pytest.mark.asyncio
    async def test_self_reported_mentions_are_credited(self, rich_html):
        ctx = make_context(
            pages={SITE: {"text": rich_html}},
            questionnaire={
                "ai_presence": {"known_third_party_mentions": "Featured in TechCrunch, listed on G2"}
            },
        )
        result = await EntityAuthorityPillar().run(ctx)

        assert result.findings["self_reported_mentions"] is True
        assert "earn-third-party-mentions" not in {rec.id for rec in result.recommendations}
