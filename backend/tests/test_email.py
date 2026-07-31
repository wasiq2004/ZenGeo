"""Transactional email: sender parsing, transport selection, Resend calls.

The failure this file mostly guards against is silent: a misconfigured sender or
a quietly-swallowed provider error means password-reset links stop arriving, and
nothing in the application looks broken while it happens.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.core.config import Settings
from app.services import email as email_service


def make_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "postgres_host": "db.internal",
        "postgres_user": "geo_app",
        "postgres_password": "owner-secret",
        "app_db_user": "geo_runtime",
        "app_db_password": "runtime-secret",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


class FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, Any] | None = None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.content = json.dumps(self._payload).encode()
        self.text = json.dumps(self._payload)

    def json(self) -> dict[str, Any]:
        return self._payload


class FakeClient:
    """Stands in for httpx.AsyncClient, capturing the one request made."""

    last_call: dict[str, Any] = {}

    def __init__(self, response: FakeResponse | Exception):
        self._response = response

    def __call__(self, *args: object, **kwargs: object) -> FakeClient:
        FakeClient.last_call["client_kwargs"] = kwargs
        return self

    async def __aenter__(self) -> FakeClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def post(self, url: str, **kwargs: Any) -> FakeResponse:
        FakeClient.last_call["url"] = url
        FakeClient.last_call.update(kwargs)
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


@pytest.fixture
def resend_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    settings = make_settings(
        resend_api_key="re_test_key",
        mail_from="CHECKGEO AI <no-reply@zenautomations.in>",
    )
    monkeypatch.setattr(email_service, "settings", settings)
    FakeClient.last_call = {}
    return settings


class TestSenderParsing:
    def test_splits_display_name_from_address(self):
        settings = make_settings(mail_from="CHECKGEO AI <no-reply@zenautomations.in>")
        assert settings.mail_from_parts == ("CHECKGEO AI", "no-reply@zenautomations.in")
        assert settings.mail_from_address == "no-reply@zenautomations.in"
        assert settings.mail_from_domain == "zenautomations.in"

    def test_accepts_a_bare_address(self):
        settings = make_settings(mail_from="no-reply@zenautomations.in")
        assert settings.mail_from_parts == ("", "no-reply@zenautomations.in")
        assert settings.mail_from_domain == "zenautomations.in"

    def test_domain_is_lowercased(self):
        # DNS is case-insensitive; comparing against the verified domain is not.
        settings = make_settings(mail_from="X <no-reply@ZenAutomations.IN>")
        assert settings.mail_from_domain == "zenautomations.in"

    def test_smtp_from_still_populates_mail_from(self, monkeypatch: pytest.MonkeyPatch):
        # An .env written before Resend should not silently lose its sender.
        monkeypatch.setenv("SMTP_FROM", "Legacy <old@zenautomations.in>")
        monkeypatch.delenv("MAIL_FROM", raising=False)
        assert make_settings().mail_from_address == "old@zenautomations.in"


class TestBackendSelection:
    def test_resend_wins_when_a_key_is_present(self):
        settings = make_settings(resend_api_key="re_x", smtp_host="smtp.example.com")
        assert settings.email_backend == "resend"

    def test_smtp_is_the_fallback(self):
        assert make_settings(smtp_host="smtp.example.com").email_backend == "smtp"

    def test_console_when_nothing_is_configured(self):
        assert make_settings().email_backend == "console"


class TestProductionGuards:
    def test_production_requires_a_resend_key(self):
        problems = make_settings(
            environment="production", mail_from="A <a@zenautomations.in>"
        ).validate_for_production()
        assert any("RESEND_API_KEY" in problem for problem in problems)

    def test_production_rejects_the_placeholder_domain(self):
        problems = make_settings(
            environment="production",
            resend_api_key="re_x",
            mail_from="CheckGEO.ai <no-reply@example.com>",
        ).validate_for_production()
        assert any("example.com" in problem for problem in problems)

    def test_production_rejects_a_sender_without_a_display_name(self):
        problems = make_settings(
            environment="production",
            resend_api_key="re_x",
            mail_from="no-reply@zenautomations.in",
        ).validate_for_production()
        assert any("display name" in problem for problem in problems)

    def test_a_fully_configured_sender_passes(self):
        problems = make_settings(
            environment="production",
            resend_api_key="re_x",
            mail_from="CHECKGEO AI <no-reply@zenautomations.in>",
        ).validate_for_production()
        assert not any(
            "MAIL_FROM" in problem or "RESEND_API_KEY" in problem for problem in problems
        )


class TestResendTransport:
    @pytest.mark.anyio
    async def test_posts_the_expected_payload(
        self, resend_settings: Settings, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(
            email_service.httpx,
            "AsyncClient",
            FakeClient(FakeResponse(200, {"id": "msg_123"})),
        )

        message_id = await email_service.send_email_or_raise(
            to="user@example.com", subject="Hi", html="<p>Hi</p>", text="Hi"
        )

        assert message_id == "msg_123"
        call = FakeClient.last_call
        assert call["url"] == resend_settings.resend_api_url
        assert call["json"]["from"] == "CHECKGEO AI <no-reply@zenautomations.in>"
        assert call["json"]["to"] == ["user@example.com"]
        assert call["json"]["subject"] == "Hi"
        assert call["headers"]["Authorization"] == "Bearer re_test_key"

    @pytest.mark.anyio
    async def test_a_provider_rejection_raises_so_the_worker_can_retry(
        self, resend_settings: Settings, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(
            email_service.httpx,
            "AsyncClient",
            FakeClient(FakeResponse(403, {"message": "Domain is not verified"})),
        )

        with pytest.raises(email_service.EmailSendError, match="403"):
            await email_service.send_email_or_raise(
                to="user@example.com", subject="Hi", html="<p>Hi</p>", text="Hi"
            )

    @pytest.mark.anyio
    async def test_a_network_error_raises_rather_than_reporting_success(
        self, resend_settings: Settings, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(
            email_service.httpx,
            "AsyncClient",
            FakeClient(email_service.httpx.ConnectTimeout("timed out")),
        )

        with pytest.raises(email_service.EmailSendError, match="unreachable"):
            await email_service.send_email_or_raise(
                to="user@example.com", subject="Hi", html="<p>Hi</p>", text="Hi"
            )

    @pytest.mark.anyio
    async def test_send_email_swallows_failure_so_signup_still_succeeds(
        self, resend_settings: Settings, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(
            email_service.httpx,
            "AsyncClient",
            FakeClient(FakeResponse(500, {"message": "boom"})),
        )

        assert (
            await email_service.send_email(
                to="user@example.com", subject="Hi", html="<p>Hi</p>", text="Hi"
            )
            is False
        )

    @pytest.mark.anyio
    async def test_the_api_key_never_appears_in_the_request_body(
        self, resend_settings: Settings, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(
            email_service.httpx, "AsyncClient", FakeClient(FakeResponse(200, {"id": "x"}))
        )
        await email_service.send_email_or_raise(
            to="user@example.com", subject="Hi", html="<p>Hi</p>", text="Hi"
        )
        assert "re_test_key" not in json.dumps(FakeClient.last_call["json"])


class TestMessageBuilding:
    @pytest.mark.parametrize(
        "kind, context",
        [
            ("verify", {"name": "Ada", "token": "tok"}),
            ("password_reset", {"name": "Ada", "token": "tok"}),
            ("email_changed", {"name": "Ada", "new_email": "new@example.com"}),
            (
                "audit_complete",
                {
                    "name": "Ada",
                    "business": "Acme",
                    "score": 57.4,
                    "band": "Needs Work",
                    "audit_id": "abc",
                },
            ),
            ("test", {"name": "Ada"}),
        ],
    )
    def test_every_kind_renders_a_subject_and_both_bodies(
        self, kind: str, context: dict[str, object]
    ):
        subject, html, text = email_service.build_message(kind, context)
        assert subject
        assert "<" in html  # rendered the template, not the raw name
        assert text.strip()

    def test_an_unknown_kind_is_a_loud_error(self):
        with pytest.raises(ValueError, match="Unknown email kind"):
            email_service.build_message("nope", {})

    def test_the_change_notice_names_the_new_address(self):
        _, html, text = email_service.build_message(
            "email_changed", {"name": "Ada", "new_email": "attacker@evil.example"}
        )
        # The whole point of this message is that the old address can see what
        # the new one is.
        assert "attacker@evil.example" in html
        assert "attacker@evil.example" in text

    def test_a_name_with_markup_is_escaped(self):
        _, html, _ = email_service.build_message(
            "verify", {"name": "<script>alert(1)</script>", "token": "t"}
        )
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
