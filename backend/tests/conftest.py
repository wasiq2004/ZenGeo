"""Shared test fixtures.

The audit engine is tested without network access: `FakeFetcher` serves canned
pages, and `FakeProvider` stands in for a BYOK LLM adapter. That keeps the
suite deterministic and means Share of Voice - the one pillar that normally
needs a real API key - is still covered end to end.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.audit.context import AuditContext
from app.audit.fetcher import FetchResult
from app.llm.base import LLMProvider, LLMResponse, ValidationResult


class FakeFetcher:
    """Stands in for SafeFetcher. Serves a dict of URL -> response."""

    def __init__(self, pages: dict[str, dict[str, Any]] | None = None) -> None:
        self.pages = pages or {}
        self.requested: list[str] = []

    async def fetch(self, url: str) -> FetchResult:
        self.requested.append(url)
        spec = self.pages.get(url)

        if spec is None:
            return FetchResult(
                url=url,
                final_url=url,
                status_code=404,
                content_type="text/html",
                text="",
                ok=False,
                elapsed_ms=1,
                error="Not found",
            )

        status = spec.get("status", 200)
        return FetchResult(
            url=url,
            final_url=spec.get("final_url", url),
            status_code=status,
            content_type=spec.get("content_type", "text/html; charset=utf-8"),
            text=spec.get("text", ""),
            ok=200 <= status < 300,
            elapsed_ms=spec.get("elapsed_ms", 12),
        )


class FakeProvider(LLMProvider):
    """A BYOK adapter that returns canned answers instead of calling out."""

    name = "fake"
    display_name = "Fake Provider"
    default_model = "fake-model-1"
    supports_web_search = True

    def __init__(
        self,
        answers: dict[str, str] | str = "",
        *,
        citations: list[str] | None = None,
        grounded: bool = False,
        raises: Exception | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__("fake-key", **kwargs)
        self.answers = answers
        self.citations = citations or []
        self.grounded = grounded
        self.raises = raises
        self.calls: list[str] = []

    async def validate(self) -> ValidationResult:
        return ValidationResult(ok=True, message="ok")

    async def ask(self, prompt: str, *, max_tokens: int = 1024) -> LLMResponse:
        self.calls.append(prompt)
        if self.raises is not None:
            raise self.raises
        text = self.answers if isinstance(self.answers, str) else self.answers.get(prompt, "")
        return LLMResponse(
            text=text,
            model=self.model,
            citations=list(self.citations),
            grounded=self.grounded,
            input_tokens=10,
            output_tokens=20,
        )


async def _noop_emit(_stage: str, _message: str, _level: str = "info") -> None:
    """Progress sink for tests - the runner's DB writes are not under test."""


def make_context(
    *,
    pages: dict[str, dict[str, Any]] | None = None,
    business_name: str = "Acme Analytics",
    website_url: str = "https://acme.test",
    competitors: list[str] | None = None,
    key_pages: list[str] | None = None,
    questionnaire: dict[str, Any] | None = None,
) -> AuditContext:
    return AuditContext(
        business_name=business_name,
        website_url=website_url,
        industry="Analytics",
        description="Product analytics for small teams",
        location="United Kingdom",
        competitors=competitors or [],
        key_pages=key_pages or [],
        questionnaire=questionnaire or {},
        fetcher=FakeFetcher(pages),  # type: ignore[arg-type]
        emit=_noop_emit,
    )


@pytest.fixture
def rich_html() -> str:
    """A page that scores well: headings, lists, tables, schema, evidence."""
    return """
    <html><head>
      <script type="application/ld+json">
      {"@context":"https://schema.org","@type":"Organization",
       "name":"Acme Analytics","url":"https://acme.test",
       "logo":"https://acme.test/logo.png","description":"Product analytics",
       "telephone":"+44 20 7946 0000",
       "address":{"@type":"PostalAddress","streetAddress":"1 Test Road",
                  "addressLocality":"London","postalCode":"E1 6AN"},
       "sameAs":["https://www.linkedin.com/company/acme",
                 "https://www.crunchbase.com/organization/acme",
                 "https://x.com/acme"]}
      </script>
      <script type="application/ld+json">
      {"@context":"https://schema.org","@type":"FAQPage","mainEntity":[]}
      </script>
      <script type="application/ld+json">
      {"@context":"https://schema.org","@type":"Product","name":"Acme"}
      </script>
      <script type="application/ld+json">
      {"@context":"https://schema.org","@type":"Article","author":{"name":"Alex Kim"},
       "datePublished":"2026-06-01"}
      </script>
    </head><body>
      <h1>Product analytics for small engineering teams</h1>
      <p>Acme Analytics tracks 2.4x more release events than the average tool.
         Teams ship 38% faster within one quarter.</p>
      <h2>How it works</h2>
      <p>By Alex Kim, published 2026-06-01. We attribute every metric to a commit,
         so you can see which change moved which number without guessing. Events are
         collected at the edge and written to your own warehouse within 30 seconds.</p>
      <p>Most teams connect their first repository in under ten minutes. There is no
         sampling at any plan level, so the numbers you see are the numbers that
         happened. Self-hosting is supported on any container platform.</p>
      <ul><li>Per-commit attribution</li><li>No sampling</li><li>Self-hosted option</li></ul>
      <h2>Pricing</h2>
      <table><tr><th>Plan</th><th>Price</th></tr><tr><td>Team</td><td>$49</td></tr></table>
      <h2>Evidence</h2>
      <blockquote>"It cut our triage time in half." - Dana Reed, CTO</blockquote>
      <p>See the <a href="https://www.nature.com/articles/example">underlying study</a>
         and the <a href="https://arxiv.org/abs/1234.5678">benchmark paper</a> for the
         methodology behind these figures, both published in 2026 and independently
         reviewed before we cited them here.</p>
      <time datetime="2026-06-01">1 June 2026</time>
      <footer><a href="https://www.linkedin.com/company/acme">LinkedIn</a></footer>
    </body></html>
    """


@pytest.fixture
def sparse_html() -> str:
    """A page that scores badly: a client-rendered shell with nothing in it."""
    return '<html><head><title>Acme</title></head><body><div id="root"></div></body></html>'
