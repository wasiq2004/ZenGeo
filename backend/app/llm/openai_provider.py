"""OpenAI (ChatGPT) adapter, built on the official OpenAI Python SDK."""

from __future__ import annotations

import openai

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

log = get_logger("llm.openai")


@register_provider
class OpenAIProvider(LLMProvider):
    name = "openai"
    display_name = "OpenAI (ChatGPT)"
    default_model = "gpt-4o"
    suggested_models = ("gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini")
    key_format_hint = "Starts with sk- or sk-proj-"
    docs_url = "https://platform.openai.com/api-keys"
    #: Answers come from model knowledge, not live retrieval, so citations are
    #: whatever URLs appear in the prose. Reported as ungrounded.
    supports_web_search = False

    def _client(self) -> openai.AsyncOpenAI:
        return openai.AsyncOpenAI(api_key=self.api_key, timeout=self.timeout, max_retries=1)

    async def validate(self) -> ValidationResult:
        """Lists models - a free metadata call, so validating costs nothing."""
        client = self._client()
        try:
            listing = await client.models.list()
            model_ids = sorted(m.id for m in listing.data)
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
                ok=True, message="Key verified with OpenAI.", available_models=model_ids
            )
        except openai.AuthenticationError:
            return ValidationResult(ok=False, message="OpenAI rejected this API key.")
        except openai.PermissionDeniedError:
            return ValidationResult(
                ok=False, message="This key does not have permission to list models."
            )
        except openai.RateLimitError:
            return ValidationResult(
                ok=False, message="OpenAI is rate limiting this key. Try again shortly."
            )
        except openai.APIError as exc:
            return ValidationResult(ok=False, message=f"OpenAI error: {exc.__class__.__name__}")
        except Exception as exc:
            log.warning("openai_validate_failed", error=type(exc).__name__)
            return ValidationResult(ok=False, message="Could not reach OpenAI.")
        finally:
            await client.close()

    async def ask(self, prompt: str, *, max_tokens: int = 1024) -> LLMResponse:
        client = self._client()
        try:
            completion = await client.chat.completions.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
        except openai.AuthenticationError as exc:
            raise InvalidAPIKey("OpenAI rejected this API key") from exc
        except openai.RateLimitError as exc:
            raise ProviderRateLimited("OpenAI rate limit reached") from exc
        except openai.APIStatusError as exc:
            raise ProviderUnavailable(f"OpenAI returned {exc.status_code}") from exc
        except openai.APIConnectionError as exc:
            raise ProviderUnavailable("Could not reach OpenAI") from exc
        finally:
            await client.close()

        choice = completion.choices[0] if completion.choices else None
        text = (choice.message.content if choice and choice.message else None) or ""
        usage = completion.usage

        return LLMResponse(
            text=text.strip(),
            model=completion.model,
            citations=[],
            grounded=False,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )
