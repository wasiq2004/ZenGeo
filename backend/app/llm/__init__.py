"""LLM provider adapters.

Importing this package registers every adapter. To add a provider, drop a new
module here that subclasses `LLMProvider` and applies `@register_provider`,
then import it below - nothing else needs to change.
"""

from app.llm import anthropic_provider, openai_provider, perplexity_provider  # noqa: F401
from app.llm.base import (
    InvalidAPIKey,
    LLMError,
    LLMProvider,
    LLMResponse,
    ProviderRateLimited,
    ProviderUnavailable,
    ValidationResult,
    available_providers,
    get_provider_class,
    provider_catalog,
    register_provider,
)

__all__ = [
    "InvalidAPIKey",
    "LLMError",
    "LLMProvider",
    "LLMResponse",
    "ProviderRateLimited",
    "ProviderUnavailable",
    "ValidationResult",
    "available_providers",
    "get_provider_class",
    "provider_catalog",
    "register_provider",
]
