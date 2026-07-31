"""Transactional email.

Three transports, chosen by configuration (see ``Settings.email_backend``):

* **Resend** when ``RESEND_API_KEY`` is set - the production path.
* **SMTP** when only ``SMTP_HOST`` is set - a fallback for self-hosters.
* **Console** otherwise - the message, including the verification or reset
  link, is written to the application log instead of being sent. That keeps
  local development and CI self-contained with no outbound dependency.

Sends normally go through the Celery worker (see ``dispatch``), so a slow or
failing mail provider never holds up the request that triggered it, and a
transient failure is retried rather than lost.
"""

from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path

import aiosmtplib
import httpx
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger("email")


class EmailSendError(Exception):
    """A send failed in a way that is worth retrying."""

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "email"

_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=select_autoescape(["html", "xml"]),  # escapes user-supplied names
    trim_blocks=True,
    lstrip_blocks=True,
)


def _render(template: str, **context: object) -> str:
    return _env.get_template(template).render(
        frontend_url=settings.frontend_url.rstrip("/"), **context
    )


async def _send_via_resend(*, to: str, subject: str, html: str, text: str) -> str:
    """POST one message to Resend. Returns the provider's message id.

    Raises ``EmailSendError`` on anything the caller should retry.
    """
    payload = {
        # Resend wants the RFC 5322 form; MAIL_FROM already is one, and its
        # domain must be a verified sending domain on the Resend account.
        "from": settings.mail_from,
        "to": [to],
        "subject": subject,
        "html": html,
        "text": text,
    }

    try:
        async with httpx.AsyncClient(timeout=settings.resend_timeout_seconds) as client:
            response = await client.post(
                settings.resend_api_url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {settings.resend_api_key.get_secret_value()}",
                    "Content-Type": "application/json",
                },
            )
    except httpx.HTTPError as exc:
        raise EmailSendError(f"Resend unreachable: {type(exc).__name__}") from exc

    if response.status_code >= 400:
        # 4xx is usually a configuration fault - an unverified sending domain,
        # a revoked key - and retrying will not fix it, but the retry policy
        # lives in the worker task rather than here, so surface the status and
        # let it decide. The body may name the exact problem; it never contains
        # our key, so it is safe to log.
        detail = response.text[:400]
        log.error(
            "email_provider_rejected",
            provider="resend",
            to=to,
            subject=subject,
            status=response.status_code,
            detail=detail,
            sending_domain=settings.mail_from_domain,
        )
        raise EmailSendError(f"Resend returned {response.status_code}: {detail}")

    body = response.json() if response.content else {}
    message_id = str(body.get("id", "")) if isinstance(body, dict) else ""
    log.info(
        "email_sent",
        provider="resend",
        to=to,
        subject=subject,
        status=response.status_code,
        resend_id=message_id,
    )
    return message_id


async def _send_via_smtp(*, to: str, subject: str, html: str, text: str) -> str:
    message = EmailMessage()
    message["From"] = settings.mail_from
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text)
    message.add_alternative(html, subtype="html")

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user or None,
            password=(settings.smtp_password.get_secret_value() or None),
            start_tls=settings.smtp_starttls,
            timeout=20,
        )
    except Exception as exc:
        raise EmailSendError(f"SMTP send failed: {exc}") from exc

    log.info("email_sent", provider="smtp", to=to, subject=subject)
    return ""


async def send_email(*, to: str, subject: str, html: str, text: str) -> bool:
    """Send one message now, in this process.

    Returns True on success. Prefer ``dispatch`` - this is the inner call the
    worker makes, and the escape hatch for the admin test-send endpoint, which
    wants the failure reported synchronously.
    """
    try:
        await send_email_or_raise(to=to, subject=subject, html=html, text=text)
        return True
    except EmailSendError as exc:
        # A mail outage must not fail the surrounding request (e.g. signup).
        log.error("email_send_failed", to=to, subject=subject, error=str(exc))
        return False


async def send_email_or_raise(*, to: str, subject: str, html: str, text: str) -> str:
    """As ``send_email``, but raises so the worker's retry policy can see it."""
    backend = settings.email_backend

    if backend == "resend":
        return await _send_via_resend(to=to, subject=subject, html=html, text=text)
    if backend == "smtp":
        return await _send_via_smtp(to=to, subject=subject, html=html, text=text)

    log.info(
        "email_console_backend",
        to=to,
        subject=subject,
        body=text,
        note="No RESEND_API_KEY or SMTP_HOST configured; message logged instead of sent.",
    )
    return ""


# --- Message building ------------------------------------------------------
#
# Messages are built from a small context dict rather than passed around
# pre-rendered. The worker re-renders from that context, so the Celery payload
# stays small and a template fix applies to anything still queued.


def build_message(kind: str, context: dict[str, object]) -> tuple[str, str, str]:
    """Return ``(subject, html, text)`` for one kind of message."""
    name = str(context.get("name") or "there")
    base = settings.frontend_url.rstrip("/")

    if kind == "verify":
        link = f"{base}/verify-email?token={context['token']}"
        return (
            "Confirm your email — CheckGEO.ai",
            _render("verify_email.html", name=name, link=link),
            (
                f"Hi {name},\n\n"
                "Confirm your email address to start running GEO audits:\n"
                f"{link}\n\n"
                f"The link expires in {settings.email_token_ttl_hours} hours.\n"
                "If you did not create this account you can ignore this message."
            ),
        )

    if kind == "password_reset":
        link = f"{base}/reset-password?token={context['token']}"
        return (
            "Reset your password — CheckGEO.ai",
            _render("reset_password.html", name=name, link=link),
            (
                f"Hi {name},\n\n"
                "Use this link to choose a new password:\n"
                f"{link}\n\n"
                f"The link expires in {settings.password_reset_ttl_minutes} minutes and "
                "can only be used once.\n"
                "If you did not request this, no action is needed - your password is "
                "unchanged."
            ),
        )

    if kind == "email_changed":
        # Goes to the PREVIOUS address, which is the only one an attacker who
        # just took over the account does not control. It is how the real owner
        # finds out.
        new_address = str(context["new_email"])
        return (
            "Your email address was changed — CheckGEO.ai",
            _render("email_changed.html", name=name, new_email=new_address),
            (
                f"Hi {name},\n\n"
                f"The email address on your CheckGEO.ai account was just changed to "
                f"{new_address}.\n\n"
                "If that was you, nothing further is needed - confirm the new address "
                "from the message sent to it.\n\n"
                "If it was NOT you, reset your password immediately at "
                f"{base}/forgot-password and contact support."
            ),
        )

    if kind == "audit_complete":
        link = f"{base}/app/audits/{context['audit_id']}"
        business = str(context["business"])
        score = float(context["score"])  # type: ignore[arg-type]
        band = str(context["band"])
        return (
            f"Your GEO audit for {business} is ready — score {score:.0f}/100",
            _render(
                "audit_complete.html",
                name=name,
                business=business,
                score=f"{score:.0f}",
                band=band,
                link=link,
            ),
            (
                f"Hi {name},\n\n"
                f"The GEO audit for {business} finished.\n"
                f"Overall score: {score:.0f}/100 ({band})\n\n"
                f"Full report: {link}\n"
            ),
        )

    if kind == "test":
        return (
            "CheckGEO.ai test message",
            _render("test_message.html", name=name),
            (
                "This is a test message from CheckGEO.ai.\n\n"
                "If you are reading it, the mail provider is configured correctly "
                "and the sending domain is verified."
            ),
        )

    raise ValueError(f"Unknown email kind: {kind!r}")


async def send_now(kind: str, *, to: str, context: dict[str, object]) -> str:
    """Render and send immediately, raising on failure. Used by the worker."""
    subject, html, text = build_message(kind, context)
    return await send_email_or_raise(to=to, subject=subject, html=html, text=text)


# --- Dispatch --------------------------------------------------------------


async def dispatch_async(kind: str, *, to: str, **context: object) -> None:
    """Hand a message to the worker.

    Never raises: a mail problem must not fail the request that triggered it.
    If the broker is unreachable the message is sent inline instead - losing a
    verification link silently is worse than a slow signup. That fallback is
    also what keeps tests and worker-less deployments working.
    """
    from app.worker.tasks import send_email_task

    try:
        send_email_task.delay(kind, to, context)
        log.info("email_queued", kind=kind, to=to)
        return
    except Exception as exc:
        log.warning(
            "email_enqueue_failed_sending_inline", kind=kind, to=to, error=str(exc)
        )

    subject, html, text = build_message(kind, context)
    await send_email(to=to, subject=subject, html=html, text=text)


# --- Call-site helpers -----------------------------------------------------


async def send_verification_email(*, to: str, name: str | None, token: str) -> bool:
    await dispatch_async("verify", to=to, name=name, token=token)
    return True


async def send_password_reset_email(*, to: str, name: str | None, token: str) -> bool:
    await dispatch_async("password_reset", to=to, name=name, token=token)
    return True


async def send_email_changed_notice(
    *, to: str, name: str | None, new_email: str
) -> bool:
    await dispatch_async("email_changed", to=to, name=name, new_email=new_email)
    return True


async def send_audit_complete_email(
    *, to: str, name: str | None, business: str, score: float, band: str, audit_id: str
) -> bool:
    await dispatch_async(
        "audit_complete",
        to=to,
        name=name,
        business=business,
        score=score,
        band=band,
        audit_id=audit_id,
    )
    return True
