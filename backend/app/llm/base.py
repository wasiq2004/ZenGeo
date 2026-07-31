"""LLM provider interface and registry.

Adding a provider means writing one subclass of :class:`LLMProvider` and
decorating it with :func:`register_provider`. Nothing else in the codebase
names a provider explicitly - the audit engine, the API and the UI all read
from the registry - so a new adapter is genuinely plug and play.

Every adapter is constructed with the *user's own* decrypted API key and lives
only for the duration of one call.
"""

from __future__ import annotations

import abc
import re
from dataclasses import dataclass, field
from typing import ClassVar

from app.core.logging import get_logger

log = get_logger("llm")

#: Matches bare URLs in prose so citations can be extracted from providers that
#: do not return a structured citation list.
URL_PATTERN = re.compile(r"https?://[^\s<>\"'\)\]\},]+")


class LLMError(Exception):
    """Base class for provider failures."""


class InvalidAPIKey(LLMError):
    """The key was rejected by the provider."""


class ProviderRateLimited(LLMError):
    """The provider throttled us; the caller may retry after a delay."""


class ProviderUnavailable(LLMError):
    """Transient provider-side failure (5xx, timeout, network)."""


@dataclass(slots=True)
class ValidationResult:
    ok: bool
    message: str
    #: Model IDs the key can actually reach, when the provider exposes them.
    available_models: list[str] = field(default_factory=list)


@dataclass(slots=True)
class LLMResponse:
    """One assistant answer, normalised across providers."""

    text: str
    model: str
    #: URLs the provider explicitly cited. Empty for providers that answer from
    #: model knowledge alone - see `grounded`.
    citations: list[str] = field(default_factory=list)
    #: True when the answer was produced with live web retrieval. Citation rate
    #: is only comparable between grounded answers, so the report shows this.
    grounded: bool = False
    input_tokens: int = 0
    output_tokens: int = 0

    def all_citations(self) -> list[str]:
        """Structured citations plus any bare URLs found in the prose."""
        found = list(self.citations)
        for url in URL_PATTERN.findall(self.text):
            cleaned = url.rstrip(".,;:")
            if cleaned not in found:
                found.append(cleaned)
        return found


class LLMProvider(abc.ABC):
    """One AI assistant a user can test their prompts against."""

    #: Stable key used in the database enum, the API and the registry.
    name: ClassVar[str]
    display_name: ClassVar[str]
    default_model: ClassVar[str]
    #: Suggestions for the UI. Users may type any model string - providers ship
    #: new models faster than this list can be updated.
    suggested_models: ClassVar[tuple[str, ...]] = ()
    key_format_hint: ClassVar[str] = ""
    docs_url: ClassVar[str] = ""
    #: Whether answers can be backed by live web retrieval on this provider.
    supports_web_search: ClassVar[bool] = False
    #: True when retrieval is always on and cannot be disabled.
    always_grounded: ClassVar[bool] = False

    def __init__(
        self,
        api_key: str,
        *,
        model: str | None = None,
        timeout: float = 120.0,
        use_web_search: bool = True,
    ) -> None:
        self.api_key = api_key
        self.model = model or self.default_model
        self.timeout = timeout
        self.use_web_search = use_web_search and self.supports_web_search

    @abc.abstractmethod
    async def validate(self) -> ValidationResult:
        """Cheapest possible check that the key works. Must not bill the user
        for generation where the provider offers a free metadata endpoint."""

    @abc.abstractmethod
    async def ask(self, prompt: str, *, max_tokens: int = 1024) -> LLMResponse:
        """Send one end-user-style question and return the assistant's answer."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<{type(self).__name__} model={self.model}>"


_REGISTRY: dict[str, type[LLMProvider]] = {}


def register_provider(cls: type[LLMProvider]) -> type[LLMProvider]:
    """Class decorator that makes an adapter discoverable everywhere."""
    if not getattr(cls, "name", None):
        raise ValueError(f"{cls.__name__} must define a `name`")
    _REGISTRY[cls.name] = cls
    return cls


def get_provider_class(name: str) -> type[LLMProvider]:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise LLMError(f"Unknown LLM provider {name!r}") from None


def available_providers() -> dict[str, type[LLMProvider]]:
    return dict(_REGISTRY)


def provider_catalog() -> list[dict[str, object]]:
    """Metadata for the settings UI, derived from the registry."""
    return [
        {
            "name": cls.name,
            "display_name": cls.display_name,
            "default_model": cls.default_model,
            "models": list(cls.suggested_models),
            "key_format_hint": cls.key_format_hint,
            "docs_url": cls.docs_url,
            "supports_web_search": cls.supports_web_search,
            "always_grounded": cls.always_grounded,
        }
        for cls in _REGISTRY.values()
    ]
