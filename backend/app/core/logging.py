"""Structured logging.

Rules enforced here:
  * every log line carries a ``request_id`` so a user report can be traced;
  * secrets are scrubbed by `_redact` before rendering, so an accidental
    ``log.info("...", api_key=key)`` can never leak a credential to disk.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import MutableMapping
from contextvars import ContextVar
from typing import Any

import structlog

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

#: Any event-dict key containing one of these substrings is replaced wholesale.
_SENSITIVE_KEY_PARTS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "encrypted_key",
    "mfa",
)


EventDict = MutableMapping[str, Any]


def _redact(_logger: Any, _name: str, event_dict: EventDict) -> EventDict:
    for key in list(event_dict):
        lowered = key.lower()
        if any(part in lowered for part in _SENSITIVE_KEY_PARTS):
            event_dict[key] = "[redacted]"
    return event_dict


def _add_request_id(_logger: Any, _name: str, event_dict: EventDict) -> EventDict:
    event_dict.setdefault("request_id", request_id_ctx.get())
    return event_dict


def configure_logging(level: str = "INFO", fmt: str = "console") -> None:
    logging.basicConfig(
        format="%(message)s", stream=sys.stdout, level=getattr(logging, level.upper(), 20)
    )
    # Uvicorn's own access log duplicates our structured request log.
    logging.getLogger("uvicorn.access").disabled = True

    renderer: Any = (
        structlog.processors.JSONRenderer()
        if fmt == "json"
        else structlog.dev.ConsoleRenderer(colors=False)
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            _add_request_id,
            _redact,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), 20)
        ),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "app") -> Any:
    return structlog.get_logger(name)
