"""Pillar 1 - Crawlability & AI bot access (spec 2.1, weight 15%).

Can AI crawlers reach the site at all? Everything else is moot if GPTBot gets a
403, or if the page is an empty shell that only fills in after JavaScript runs.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from app.audit.context import AuditContext
from app.audit.pillars.base import Pillar, PillarResult, Recommendation, ScoreBuilder

#: The crawlers that populate AI answers. Blocking these is the single most
#: effective way to be invisible inside an AI assistant.
AI_BOTS = (
    "GPTBot",
    "ChatGPT-User",
    "OAI-SearchBot",
    "PerplexityBot",
    "Perplexity-User",
    "ClaudeBot",
    "Claude-User",
    "anthropic-ai",
    "Google-Extended",
    "CCBot",
    "Applebot-Extended",
    "meta-externalagent",
)

#: Below this, a page is almost certainly a client-rendered shell.
MIN_MEANINGFUL_TEXT = 500


class RobotsRules:
    """A minimal robots.txt parser.

    Python's `urllib.robotparser` collapses group semantics in ways that hide
    exactly what we need to report - which named agent is blocked, and by which
    rule - so this walks the groups directly.
    """

    def __init__(self, text: str) -> None:
        self.groups: list[tuple[list[str], list[tuple[str, str]]]] = []
        self.sitemaps: list[str] = []
        self._parse(text)

    def _parse(self, text: str) -> None:
        agents: list[str] = []
        rules: list[tuple[str, str]] = []
        expecting_agent = True

        for raw_line in text.splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line or ":" not in line:
                continue
            field, _, value = line.partition(":")
            field = field.strip().lower()
            value = value.strip()

            if field == "user-agent":
                # A new agent line after rules starts a new group.
                if not expecting_agent:
                    self.groups.append((agents, rules))
                    agents, rules = [], []
                    expecting_agent = True
                agents.append(value.lower())
            elif field in ("allow", "disallow"):
                expecting_agent = False
                rules.append((field, value))
            elif field == "sitemap":
                self.sitemaps.append(value)

        if agents or rules:
            self.groups.append((agents, rules))

    def _group_for(self, agent: str) -> list[tuple[str, str]] | None:
        """Most specific matching group, falling back to the wildcard group."""
        agent_lower = agent.lower()
        wildcard: list[tuple[str, str]] | None = None
        for agents, rules in self.groups:
            for candidate in agents:
                if candidate == agent_lower:
                    return rules
                if candidate == "*" and wildcard is None:
                    wildcard = rules
        return wildcard

    def allows(self, agent: str, path: str = "/") -> bool:
        """Longest-match wins, and Allow beats Disallow at equal length."""
        rules = self._group_for(agent)
        if rules is None:
            return True  # nothing addressed to this agent means allowed

        best_len = -1
        best_allowed = True
        for kind, pattern in rules:
            if not pattern:
                # "Disallow:" with an empty value explicitly permits everything.
                if kind == "disallow" and best_len < 0:
                    best_allowed = True
                continue
            if not self._matches(pattern, path):
                continue
            # Longest match wins; Allow beats Disallow at equal specificity.
            if len(pattern) > best_len or (len(pattern) == best_len and kind == "allow"):
                best_len = len(pattern)
                best_allowed = kind == "allow"
        return best_allowed

    @staticmethod
    def _matches(pattern: str, path: str) -> bool:
        if "*" not in pattern and "$" not in pattern:
            return path.startswith(pattern)
        regex = re.escape(pattern).replace(r"\*", ".*")
        if regex.endswith(r"\$"):
            regex = regex[:-2] + "$"
        return re.match(regex, path) is not None


class CrawlabilityPillar(Pillar):
    key = "crawlability"
    name = "Crawlability & AI Bot Access"
    weight = 0.15
    description = "Whether AI crawlers can reach your pages and see real content."

    async def run(self, ctx: AuditContext) -> PillarResult:
        builder = ScoreBuilder()
        recommendations: list[Recommendation] = []
        findings: dict[str, Any] = {}

        home = await ctx.homepage()
        if not home.fetch.ok:
            reason = home.fetch.error or f"The homepage returned HTTP {home.fetch.status_code}"
            return self.failed(f"Could not load {ctx.website_url}. {reason}")

        # --- HTTPS -------------------------------------------------------
        final_scheme = urlparse(home.fetch.final_url).scheme
        is_https = final_scheme == "https"
        builder.award(
            "Served over HTTPS",
            is_https,
            weight=8,
            yes="The site is served over HTTPS.",
            no="The site is served over plain HTTP. Assistants and users both discount insecure sources.",
        )
        if not is_https:
            recommendations.append(
                Recommendation(
                    id="enable-https",
                    title="Serve the site over HTTPS",
                    detail=(
                        "Install a TLS certificate and redirect all HTTP traffic to HTTPS. "
                        "Let's Encrypt issues free certificates and most hosts automate renewal."
                    ),
                    pillar=self.key,
                    effort="medium",
                    impact="high",
                )
            )

        # --- robots.txt --------------------------------------------------
        robots = await ctx.get_robots()
        findings["robots_txt_status"] = robots.status_code
        findings["robots_txt_found"] = robots.ok

        if robots.ok and robots.text.strip():
            rules = RobotsRules(robots.text)
            findings["robots_txt_excerpt"] = robots.text[:4000]
            findings["sitemaps_declared"] = rules.sitemaps

            builder.award(
                "robots.txt is present",
                True,
                weight=6,
                yes="Found a robots.txt at the site root.",
                no="",
            )

            blocked = [bot for bot in AI_BOTS if not rules.allows(bot)]
            allowed = [bot for bot in AI_BOTS if bot not in blocked]
            findings["ai_bots_blocked"] = blocked
            findings["ai_bots_allowed"] = allowed

            # The heaviest single weight in this pillar: a blocked crawler is a
            # hard ceiling on everything else.
            ratio = len(allowed) / len(AI_BOTS)
            builder.add(
                "AI crawlers are allowed",
                not blocked,
                (
                    f"All {len(AI_BOTS)} checked AI crawlers may access the site."
                    if not blocked
                    else f"Blocked by robots.txt: {', '.join(blocked)}."
                ),
                points=round(30 * ratio, 2),
                max_points=30,
            )

            if blocked:
                recommendations.append(
                    Recommendation(
                        id="unblock-ai-crawlers",
                        title=f"Stop blocking {len(blocked)} AI crawler(s) in robots.txt",
                        detail=(
                            f"{', '.join(blocked)} are currently disallowed. If you want to appear "
                            "in AI answers, these agents need access. Add an explicit allow group "
                            "for each, for example:\n\n"
                            "User-agent: GPTBot\nAllow: /\n\n"
                            "Keep any bots you deliberately block for licensing reasons."
                        ),
                        pillar=self.key,
                        effort="quick_win",
                        impact="high",
                        actionable=bool(ctx.questionnaire.get("controls_site_root", True)),
                    )
                )
        else:
            findings["ai_bots_blocked"] = []
            builder.award(
                "robots.txt is present",
                False,
                weight=6,
                yes="",
                no=(
                    f"No robots.txt at {ctx.root_url('robots.txt')} "
                    f"(HTTP {robots.status_code or 'no response'})."
                ),
            )
            # A missing file means crawlers are permitted by default, so this is
            # a smaller problem than an actively blocking file.
            builder.add(
                "AI crawlers are allowed",
                True,
                "No robots.txt, so crawlers are allowed by default. An explicit file states intent.",
                points=24,
                max_points=30,
            )
            recommendations.append(
                Recommendation(
                    id="add-robots-txt",
                    title="Add a robots.txt that names the AI crawlers",
                    detail=(
                        "Without a robots.txt, crawler access is implied rather than stated. "
                        "Publish one that explicitly allows GPTBot, ClaudeBot, PerplexityBot, "
                        "Google-Extended and CCBot, and point to your sitemap."
                    ),
                    pillar=self.key,
                    effort="quick_win",
                    impact="medium",
                    actionable=bool(ctx.questionnaire.get("controls_site_root", True)),
                )
            )

        # --- Server-rendered content -------------------------------------
        text_length = len(home.visible_text)
        findings["homepage_text_length"] = text_length
        findings["homepage_status"] = home.fetch.status_code

        has_content = text_length >= MIN_MEANINGFUL_TEXT
        builder.award(
            "Real content without JavaScript",
            has_content,
            weight=25,
            yes=f"The raw HTML already contains {text_length:,} characters of readable text.",
            no=(
                f"Only {text_length:,} characters of text in the raw HTML. Crawlers that do not "
                "run JavaScript will see an almost empty page."
            ),
        )
        if not has_content:
            recommendations.append(
                Recommendation(
                    id="server-render-content",
                    title="Serve your content in the initial HTML",
                    detail=(
                        "Your pages appear to render client-side. Most AI crawlers do not execute "
                        "JavaScript, so they see an empty shell. Enable server-side rendering or "
                        "static pre-rendering (Next.js SSR/SSG, Nuxt, Astro, or a prerender "
                        "service) so the text is present in the HTML response."
                    ),
                    pillar=self.key,
                    effort="strategic",
                    impact="high",
                )
            )

        # --- Sitemap ------------------------------------------------------
        sitemap_url = ctx.root_url("sitemap.xml")
        sitemap = await ctx.fetcher.fetch(sitemap_url)
        declared = findings.get("sitemaps_declared") or []
        has_sitemap = (sitemap.ok and "<urlset" in sitemap.text[:5000]) or (
            sitemap.ok and "<sitemapindex" in sitemap.text[:5000]
        )
        if not has_sitemap and declared:
            # Honour a sitemap declared at a non-standard path.
            alt = await ctx.fetcher.fetch(declared[0])
            has_sitemap = alt.ok and ("<urlset" in alt.text[:5000] or "<sitemapindex" in alt.text[:5000])
            findings["sitemap_url_checked"] = declared[0]
        else:
            findings["sitemap_url_checked"] = sitemap_url

        findings["sitemap_found"] = has_sitemap
        builder.award(
            "Valid XML sitemap",
            has_sitemap,
            weight=12,
            yes="Found a valid XML sitemap.",
            no="No valid XML sitemap found. Crawlers have to discover pages by following links.",
        )
        if not has_sitemap:
            recommendations.append(
                Recommendation(
                    id="publish-sitemap",
                    title="Publish an XML sitemap",
                    detail=(
                        "Generate a sitemap.xml listing every page you want discovered, and "
                        "reference it from robots.txt with a `Sitemap:` line. Most CMS platforms "
                        "produce one automatically."
                    ),
                    pillar=self.key,
                    effort="quick_win",
                    impact="medium",
                )
            )

        # --- Server health -------------------------------------------------
        healthy = 200 <= home.fetch.status_code < 300
        builder.award(
            "Homepage responds cleanly",
            healthy,
            weight=9,
            yes=f"Homepage returned HTTP {home.fetch.status_code} in {home.fetch.elapsed_ms} ms.",
            no=f"Homepage returned HTTP {home.fetch.status_code}.",
        )
        builder.note(
            "Response time",
            f"The homepage responded in {home.fetch.elapsed_ms} ms.",
        )

        blocked_count = len(findings.get("ai_bots_blocked") or [])
        if blocked_count:
            summary = f"{blocked_count} AI crawler(s) are blocked from your site."
        elif not has_content:
            summary = "Crawlers are allowed, but your pages need JavaScript to show any content."
        elif builder.score >= 80:
            summary = "AI crawlers can reach your site and see real content."
        else:
            summary = "Crawlers can reach the site, but some access signals are missing."

        return self.result(
            builder, summary=summary, findings=findings, recommendations=recommendations
        )
