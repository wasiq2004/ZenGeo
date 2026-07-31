"""Perplexity adapter.

Perplexity exposes an OpenAI-compatible REST surface, so this adapter talks to
it directly with httpx rather than pulling in another SDK. Every answer is web
grounded and comes back with a citation list, which makes Perplexity the
baseline the other providers' citation rates are compared against.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.core.logging import get_logger
from app.llm.base import (
    InvalidAPIKey,
    LLMProvider,
    LLMResponse,
    ProviderRateLimited,
    ProviderUnavailable,
    ValidationResult,
    register_provider,
)

log = get_logger("llm.perplexity")

API_BASE = "https://api.perplexity.ai"


@register_provider
class PerplexityProvider(LLMProvider):
    name = "perplexity"
    display_name = "Perplexity"
    default_model = "sonar"
    suggested_models = ("sonar", "sonar-pro", "sonar-reasoning")
    key_format_hint = "Starts with pplx-"
    docs_url = "https://www.perplexity.ai/settings/api"
    supports_web_search = True
    #: Retrieval cannot be turned off - every Perplexity answer is grounded.
    always_grounded = True

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    # Named `request_timeout` rather than `timeout`: this is httpx's per-request
    # deadline, not an asyncio cancellation scope.
    async def _post(self, payload: dict[str, Any], request_timeout: float) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=request_timeout) as client:
            response = await client.post(
                f"{API_BASE}/chat/completions", headers=self._headers(), json=payload
            )
        if response.status_code == 401:
            raise InvalidAPIKey("Perplexity rejected this API key")
        if response.status_code == 429:
            raise ProviderRateLimited("Perplexity rate limit reached")
        if response.status_code >= 400:
            raise ProviderUnavailable(f"Perplexity returned {response.status_code}")
        return response.json()

    async def validate(self) -> ValidationResult:
        """Perplexity has no free metadata endpoint, so this is a deliberately
        tiny completion - a handful of tokens on the user's account."""
        try:
            await self._post(
                {
                    "model": self.model,
                    "messages": [{"role": "user", "content": "Reply with OK."}],
                    "max_tokens": 5,
                },
                request_timeout=min(self.timeout, 30.0),
            )
        except InvalidAPIKey:
            return ValidationResult(ok=False, message="Perplexity rejected this API key.")
        except ProviderRateLimited:
            return ValidationResult(
                ok=False, message="Perplexity is rate limiting this key. Try again shortly."
            )
        except ProviderUnavailable as exc:
            return ValidationResult(ok=False, message=str(exc))
        except httpx.HTTPError:
            return ValidationResult(ok=False, message="Could not reach Perplexity.")
        return ValidationResult(
            ok=True,
            message="Key verified with Perplexity.",
            available_models=list(self.suggested_models),
        )

    async def ask(self, prompt: str, *, max_tokens: int = 1024) -> LLMResponse:
        try:
            data = await self._post(
                {
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                },
                request_timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise ProviderUnavailable("Could not reach Perplexity") from exc

        choices = data.get("choices") or []
        text = ""
        if choices:
            text = (choices[0].get("message") or {}).get("content") or ""

        # Perplexity has returned citations under two shapes over time: a plain
        # list of URL strings, and a richer search_results array.
        citations: list[str] = []
        for entry in data.get("citations") or []:
            if isinstance(entry, str) and entry not in citations:
                citations.append(entry)
        for result in data.get("search_results") or []:
            url = result.get("url") if isinstance(result, dict) else None
            if url and url not in citations:
                citations.append(url)

        usage = data.get("usage") or {}
        return LLMResponse(
            text=text.strip(),
            model=data.get("model") or self.model,
            citations=citations,
            grounded=True,
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
        )
