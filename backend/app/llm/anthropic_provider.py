"""Anthropic (Claude) adapter, built on the official Anthropic Python SDK."""

from __future__ import annotations

import anthropic

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

log = get_logger("llm.anthropic")

#: Models that support the server-side web search tool. Grounded answers make
#: the citation-rate metric comparable with Perplexity's.
_WEB_SEARCH_PREFIXES = ("claude-opus-", "claude-sonnet-", "claude-fable-", "claude-mythos-")


@register_provider
class AnthropicProvider(LLMProvider):
    name = "anthropic"
    display_name = "Anthropic (Claude)"
    default_model = "claude-opus-5"
    suggested_models = (
        "claude-opus-5",
        "claude-sonnet-5",
        "claude-haiku-4-5",
        "claude-opus-4-8",
    )
    key_format_hint = "Starts with sk-ant-"
    docs_url = "https://console.anthropic.com/settings/keys"
    supports_web_search = True

    def _client(self) -> anthropic.AsyncAnthropic:
        return anthropic.AsyncAnthropic(api_key=self.api_key, timeout=self.timeout, max_retries=1)

    def _web_search_enabled(self) -> bool:
        return self.use_web_search and self.model.startswith(_WEB_SEARCH_PREFIXES)

    async def validate(self) -> ValidationResult:
        """Uses the Models API - a metadata read that costs the user nothing and
        also proves the key can reach the model they selected."""
        client = self._client()
        try:
            listing = await client.models.list(limit=50)
            model_ids = [m.id for m in listing.data]
            if self.model not in model_ids:
                return ValidationResult(
                    ok=True,
                    message=(
                        f"Key is valid, but '{self.model}' was not in the list of models "
                        "this key can reach. Audits using it may fail."
                    ),
                    available_models=model_ids,
                )
            return ValidationResult(
                ok=True, message="Key verified with Anthropic.", available_models=model_ids
            )
        except anthropic.AuthenticationError:
            return ValidationResult(ok=False, message="Anthropic rejected this API key.")
        except anthropic.PermissionDeniedError:
            return ValidationResult(
                ok=False, message="This key does not have permission to use the Messages API."
            )
        except anthropic.RateLimitError:
            return ValidationResult(
                ok=False, message="Anthropic is rate limiting this key. Try again shortly."
            )
        except anthropic.APIError as exc:
            return ValidationResult(ok=False, message=f"Anthropic error: {exc.__class__.__name__}")
        except Exception as exc:
            log.warning("anthropic_validate_failed", error=type(exc).__name__)
            return ValidationResult(ok=False, message="Could not reach Anthropic.")
        finally:
            await client.close()

    async def ask(self, prompt: str, *, max_tokens: int = 1024) -> LLMResponse:
        client = self._client()
        # No `thinking` or `effort` override: this must read like the answer a
        # real person would get, and the defaults differ per model.
        # `extra_body` carries the web-search tool so the call stays on the
        # SDK's typed overload rather than a loose kwargs dict.
        extra: dict[str, object] = {}
        if self._web_search_enabled():
            extra["tools"] = [{"type": "web_search_20260209", "name": "web_search"}]

        try:
            message = await client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
                extra_body=extra or None,
            )
        except anthropic.AuthenticationError as exc:
            raise InvalidAPIKey("Anthropic rejected this API key") from exc
        except anthropic.RateLimitError as exc:
            raise ProviderRateLimited("Anthropic rate limit reached") from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                raise ProviderUnavailable(f"Anthropic returned {exc.status_code}") from exc
            raise ProviderUnavailable(f"Anthropic error: {exc.__class__.__name__}") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderUnavailable("Could not reach Anthropic") from exc
        finally:
            await client.close()

        # Safety classifiers can decline a request: HTTP 200 with an empty or
        # partial body. Checking stop_reason before reading content avoids an
        # IndexError on an otherwise successful response.
        if message.stop_reason == "refusal":
            raise ProviderUnavailable(
                "Claude declined to answer this prompt (safety classifier)."
            )

        text_parts: list[str] = []
        citations: list[str] = []
        for block in message.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "web_search_tool_result":
                content = getattr(block, "content", None)
                # An error result is a single object; a success is a list.
                if isinstance(content, list):
                    for result in content:
                        url = getattr(result, "url", None)
                        if url and url not in citations:
                            citations.append(url)

        return LLMResponse(
            text="\n".join(text_parts).strip(),
            model=message.model,
            citations=citations,
            grounded=bool(citations) or self._web_search_enabled(),
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
        )
