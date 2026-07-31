"""Shared state for one audit run.

Pages are fetched once and reused by every pillar - four pillars all want the
homepage, and re-downloading it four times would be both slow and rude to the
site being audited.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from app.audit.fetcher import FetchResult, SafeFetcher
from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("audit.context")

ProgressCallback = Callable[[str, str, str], Awaitable[None]]


@dataclass(slots=True)
class PageSnapshot:
    """A fetched page plus its parsed form."""

    url: str
    fetch: FetchResult
    soup: BeautifulSoup | None = None

    @property
    def ok(self) -> bool:
        return self.fetch.ok and self.soup is not None

    @property
    def visible_text(self) -> str:
        if self.soup is None:
            return ""
        return _visible_text(self.soup)


def attr_text(tag: Tag, name: str) -> str:
    """One attribute as a plain string.

    An HTML attribute can legitimately parse as a list (``class``, and anything
    a malformed document duplicates), so callers that want a single value have
    to say which one they mean rather than assuming.
    """
    value = tag.get(name)
    if value is None:
        return ""
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return str(value)


def _visible_text(soup: BeautifulSoup) -> str:
    """Body text as a reader would see it, minus scripts and boilerplate."""
    clone = BeautifulSoup(str(soup), "lxml")
    for tag in clone(["script", "style", "noscript", "template", "svg"]):
        tag.decompose()
    return " ".join(clone.get_text(separator=" ", strip=True).split())


@dataclass
class AuditContext:
    """Everything a pillar needs to do its job."""

    business_name: str
    website_url: str
    industry: str | None
    description: str | None
    location: str | None
    competitors: list[str]
    key_pages: list[str]
    questionnaire: dict[str, Any]

    fetcher: SafeFetcher
    emit: ProgressCallback

    #: Populated lazily by `get_page`, keyed by URL.
    pages: dict[str, PageSnapshot] = field(default_factory=dict)
    robots_txt: FetchResult | None = None

    @property
    def origin(self) -> str:
        parsed = urlparse(self.website_url)
        return f"{parsed.scheme}://{parsed.netloc}"

    @property
    def hostname(self) -> str:
        return urlparse(self.website_url).hostname or ""

    def root_url(self, path: str) -> str:
        return urljoin(f"{self.origin}/", path.lstrip("/"))

    async def get_page(self, url: str) -> PageSnapshot:
        """Fetch and parse a page, reusing an earlier fetch when possible."""
        if url in self.pages:
            return self.pages[url]

        result = await self.fetcher.fetch(url)
        soup: BeautifulSoup | None = None
        if result.ok and "html" in result.content_type.lower():
            try:
                soup = BeautifulSoup(result.text, "lxml")
            except Exception as exc:
                log.warning("html_parse_failed", url=url, error=type(exc).__name__)

        snapshot = PageSnapshot(url=url, fetch=result, soup=soup)
        self.pages[url] = snapshot
        return snapshot

    async def homepage(self) -> PageSnapshot:
        return await self.get_page(self.website_url)

    async def get_robots(self) -> FetchResult:
        if self.robots_txt is None:
            self.robots_txt = await self.fetcher.fetch(self.root_url("robots.txt"))
        return self.robots_txt

    async def content_pages(self) -> list[PageSnapshot]:
        """The pages content pillars analyse.

        Uses the key pages the user nominated. When they gave none, falls back
        to the homepage plus the first few internal nav links, as the spec's
        pillar 4 describes.
        """
        home = await self.homepage()
        selected: list[PageSnapshot] = [home] if home.ok else []

        targets = [url for url in self.key_pages if url != self.website_url]
        if not targets and home.soup is not None:
            targets = _internal_nav_links(home, self.hostname)[:3]

        budget = max(0, settings.max_pages_per_audit - len(selected))
        for url in targets[:budget]:
            snapshot = await self.get_page(url)
            if snapshot.ok:
                selected.append(snapshot)

        return selected


def _internal_nav_links(page: PageSnapshot, hostname: str) -> list[str]:
    """Same-host links from the main navigation, in document order."""
    if page.soup is None:
        return []

    containers = page.soup.select("nav a[href], header a[href]")
    if not containers:
        containers = page.soup.select("a[href]")

    seen: list[str] = []
    skip_prefixes = ("#", "mailto:", "tel:", "javascript:")
    for anchor in containers:
        href = attr_text(anchor, "href").strip()
        if not href or href.startswith(skip_prefixes):
            continue
        absolute = urljoin(page.url, href)
        parsed = urlparse(absolute)
        if parsed.hostname != hostname:
            continue
        # Ignore the homepage itself and asset links.
        if parsed.path in ("", "/"):
            continue
        if parsed.path.lower().endswith(
            (".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".zip", ".xml", ".css", ".js")
        ):
            continue
        clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if clean not in seen:
            seen.append(clean)
    return seen
