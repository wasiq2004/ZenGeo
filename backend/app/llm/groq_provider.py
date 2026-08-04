"""Groq adapter.

Groq serves open-weight models (Llama, Qwen, GPT-OSS) on their own inference
hardware, behind an OpenAI-compatible API. That compatibility is why this
module is thin: the `openai` SDK we already depend on is pointed at Groq's base
URL rather than pulling in a second client library that would speak the same
protocol. Every error type, retry and timeout behaviour is therefore identical
to the OpenAI adapter, which is the point - one less thing that behaves subtly
differently in production.

Answers come from model weights, not retrieval, so results are reported
ungrounded and any citations are whatever URLs appear in the prose - the same
treatment the OpenAI adapter gets.
"""

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

log = get_logger("llm.groq")

#: Groq's OpenAI-compatible endpoint. The SDK appends /chat/completions itself.
GROQ_BASE_URL = "https://api.groq.com/openai/v1"


@register_provider
class GroqProvider(LLMProvider):
    name = "groq"
    display_name = "Groq"
    default_model = "llama-3.3-70b-versatile"
    #: Starting suggestions only. Groq retires models faster than any hardcoded
    #: list survives - `validate()` returns what the key can actually reach, and
    #: the settings UI shows that live list beside these.
    suggested_models = (
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "openai/gpt-oss-120b",
        "qwen/qwen3-32b",
    )
    key_format_hint = "Starts with gsk_"
    docs_url = "https://console.groq.com/keys"
    #: Open-weight models answering from training data, with no retrieval layer.
    supports_web_search = False

    def _client(self) -> openai.AsyncOpenAI:
        return openai.AsyncOpenAI(
            api_key=self.api_key,
            base_url=GROQ_BASE_URL,
            timeout=self.timeout,
            max_retries=1,
        )

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
                        "this key can reach. Groq retires models regularly - pick one "
                        "from the list before running an audit."
                    ),
                    available_models=model_ids,
                )
            return ValidationResult(
                ok=True, message="Key verified with Groq.", available_models=model_ids
            )
        except openai.AuthenticationError:
            return ValidationResult(ok=False, message="Groq rejected this API key.")
        except openai.PermissionDeniedError:
            return ValidationResult(
                ok=False, message="This key does not have permission to list models."
            )
        except openai.RateLimitError:
            return ValidationResult(
                ok=False, message="Groq is rate limiting this key. Try again shortly."
            )
        except openai.APIError as exc:
            return ValidationResult(ok=False, message=f"Groq error: {exc.__class__.__name__}")
        except Exception as exc:
            log.warning("groq_validate_failed", error=type(exc).__name__)
            return ValidationResult(ok=False, message="Could not reach Groq.")
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
            raise InvalidAPIKey("Groq rejected this API key") from exc
        except openai.RateLimitError as exc:
            raise ProviderRateLimited("Groq rate limit reached") from exc
        except openai.NotFoundError as exc:
            # Groq returns 404 for a model that has been decommissioned, which
            # happens often enough to deserve its own message rather than a
            # generic "unavailable".
            raise ProviderUnavailable(
                f"Groq does not serve '{self.model}'. It may have been retired - "
                "re-test your key in Settings to see the current model list."
            ) from exc
        except openai.APIStatusError as exc:
            raise ProviderUnavailable(f"Groq returned {exc.status_code}") from exc
        except openai.APIConnectionError as exc:
            raise ProviderUnavailable("Could not reach Groq") from exc
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
