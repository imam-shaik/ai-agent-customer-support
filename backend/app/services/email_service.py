"""Email dispatch for staff replies (SMTP provider boundary).

Mirrors the LLM/embedding provider pattern: a small, honest boundary
that either really sends (SMTP configured) or reports an explicit,
typed "not delivered" outcome — never a fake success.

Missing SMTP config is a DOCUMENTED state, not an error: the staff
reply is still stored as ticket correspondence with
`email_dispatched=False` and a safe note, and the UI says exactly that.
SMTP failures (bad credentials, refused recipient, timeout) are the
same — the note carries a safe reason; low-level details go to the log
only.
"""

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("app.email")

_NOT_CONFIGURED_NOTE = (
    "Email dispatch is not configured on the server (SMTP_HOST missing) — "
    "the reply is stored with the ticket but was NOT delivered."
)

_REJECTED_NOTE = (
    "The mail server did not accept the message — the reply is stored with "
    "the ticket but was NOT delivered."
)


@dataclass(frozen=True)
class DispatchResult:
    """Outcome of one send attempt; `note` is safe to show to staff."""

    dispatched: bool
    note: str | None = None


def _build_message(from_addr: str, to: str, subject: str, body: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = from_addr
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    return message


def dispatch_email(*, to: str, subject: str, body: str) -> DispatchResult:
    """Send one plain-text email via SMTP; never raises to the caller.

    Returns DispatchResult(dispatched=True) on success, or a typed
    not-delivered outcome whose note is safe to render in the staff UI.
    """
    settings = get_settings()
    if not settings.smtp_host:
        logger.info("email_dispatch_skipped reason=not_configured to=%s", to)
        return DispatchResult(dispatched=False, note=_NOT_CONFIGURED_NOTE)

    from_addr = settings.smtp_from or settings.smtp_username or "noreply@localhost"
    message = _build_message(from_addr, to, subject, body)

    try:
        if settings.smtp_port == 465:
            # Implicit-TLS submission port.
            with smtplib.SMTP_SSL(
                settings.smtp_host,
                settings.smtp_port,
                timeout=settings.smtp_timeout_seconds,
                context=ssl.create_default_context(),
            ) as server:
                if settings.smtp_username and settings.smtp_password:
                    server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(message)
        else:
            with smtplib.SMTP(
                settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds
            ) as server:
                server.ehlo()
                # STARTTLS on the standard submission port (587). Other
                # ports are sent in the clear only when explicitly chosen.
                if settings.smtp_port == 587:
                    server.starttls(context=ssl.create_default_context())
                    server.ehlo()
                if settings.smtp_username and settings.smtp_password:
                    server.login(settings.smtp_username, settings.smtp_password)
                server.send_message(message)
    except smtplib.SMTPAuthenticationError:
        logger.error("email_dispatch_failed reason=auth host=%s", settings.smtp_host)
        return DispatchResult(dispatched=False, note=_REJECTED_NOTE)
    except smtplib.SMTPRecipientsRefused:
        logger.error("email_dispatch_failed reason=recipients_refused to=%s", to)
        return DispatchResult(dispatched=False, note=_REJECTED_NOTE)
    except (smtplib.SMTPException, OSError, TimeoutError) as exc:
        logger.error(
            "email_dispatch_failed reason=%s host=%s", type(exc).__name__, settings.smtp_host
        )
        return DispatchResult(dispatched=False, note=_REJECTED_NOTE)

    logger.info("email_dispatched to=%s subject=%r", to, subject)
    return DispatchResult(dispatched=True)
