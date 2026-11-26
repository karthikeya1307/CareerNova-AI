"""Email delivery for CareerNova AI.

Modes (``EMAIL_MODE``):
    outbox   (default) - nothing is sent; each message is written as an .eml file to
                         ``EMAIL_OUTBOX_DIR`` (default ``uploads/email_outbox``, git-ignored) so the
                         flows can be tested end to end. Status "outboxed".
    smtp               - send through the configured SMTP server. Only enable this when real
                         emails are authorised.
    brevo              - send through the Brevo transactional email HTTPS API (port 443). Use this
                         where SMTP ports are blocked (Render's free web services block 25/465/587).
                         Needs BREVO_API_KEY and a MAIL_FROM address verified as a sender in Brevo.
    disabled           - nothing is sent or written. Status "skipped".

Brevo settings: BREVO_API_KEY, MAIL_FROM (a verified Brevo sender), MAIL_FROM_NAME, SMTP_TIMEOUT_SECONDS
(also used as the HTTPS timeout), FRONTEND_URL.

SMTP settings (environment / .env):
    SMTP_HOST, SMTP_PORT (587), SMTP_SECURITY (starttls | ssl | none; default starttls,
    or ssl when the port is 465), SMTP_USERNAME, SMTP_PASSWORD, MAIL_FROM, MAIL_FROM_NAME,
    SMTP_TIMEOUT_SECONDS (15), FRONTEND_URL (links in emails; default http://localhost:5173).

Every attempt is recorded in ``email_deliveries`` (kind, recipient, status, error code) in its own
transaction, so a failure is recorded even if the caller rolls back. A message is never reported
as sent unless the SMTP server accepted it. Passwords, tokens and links are never logged or
recorded.
"""

from __future__ import annotations

import html
import json
import logging
import os
import re
import smtplib
import socket
import ssl
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

logger = logging.getLogger("careernova.email")

PRODUCT = "CareerNova AI"
TAGLINE = "Your Skills. Your Potential. Your Career."
MODES = ("outbox", "smtp", "brevo", "disabled")
BREVO_URL = "https://api.brevo.com/v3/smtp/email"
SECURITY = ("starttls", "ssl", "none")
PLACEHOLDER = re.compile(r"your[_-]|example\.(com|org)|changeme|placeholder", re.IGNORECASE)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------

@dataclass
class MailConfig:
    mode: str
    host: str | None
    port: int
    security: str
    username: str | None
    password: str | None = field(repr=False)
    mail_from: str | None
    from_name: str
    timeout: float
    frontend_url: str
    outbox_dir: Path
    api_key: str | None = field(default=None, repr=False)

    @property
    def sender(self) -> str:
        return formataddr((self.from_name, self.mail_from or ""))


def load_config() -> MailConfig:
    """Read the configuration on every call, so changes to the environment apply without restarts."""
    port_text = os.getenv("SMTP_PORT", "587").strip()
    port = int(port_text) if port_text.isdigit() else 0
    security = (os.getenv("SMTP_SECURITY") or ("ssl" if port == 465 else "starttls")).strip().lower()
    outbox = Path(os.getenv("EMAIL_OUTBOX_DIR", "uploads/email_outbox"))
    try:
        timeout = float(os.getenv("SMTP_TIMEOUT_SECONDS", "15"))
    except ValueError:
        timeout = 15.0
    return MailConfig(
        mode=(os.getenv("EMAIL_MODE") or "outbox").strip().lower(),
        host=(os.getenv("SMTP_HOST") or "").strip() or None,
        port=port,
        security=security,
        username=(os.getenv("SMTP_USERNAME") or "").strip() or None,
        password=(os.getenv("SMTP_PASSWORD") or "").replace(" ", "") or None,
        mail_from=(os.getenv("MAIL_FROM") or os.getenv("SMTP_USERNAME") or "").strip() or None,
        from_name=(os.getenv("MAIL_FROM_NAME") or PRODUCT).strip(),
        timeout=timeout,
        frontend_url=(os.getenv("FRONTEND_URL") or "http://localhost:5173").strip().rstrip("/"),
        outbox_dir=outbox if outbox.is_absolute() else PROJECT_ROOT / outbox,
        api_key=(os.getenv("BREVO_API_KEY") or "").strip() or None,
    )


def validate_config(config: MailConfig | None = None) -> dict:
    """Problems that would stop delivery, and warnings. Never includes secret values."""
    config = config or load_config()
    problems: list[str] = []
    warnings: list[str] = []
    if config.mode not in MODES:
        problems.append(f"EMAIL_MODE must be one of {', '.join(MODES)}.")
    if config.mode == "smtp":
        if not config.host:
            problems.append("SMTP_HOST is not set.")
        if not 0 < config.port < 65536:
            problems.append("SMTP_PORT must be a port number.")
        if config.security not in SECURITY:
            problems.append(f"SMTP_SECURITY must be one of {', '.join(SECURITY)}.")
        if config.security == "ssl" and config.port == 587:
            warnings.append("Port 587 normally uses STARTTLS, not SSL (set SMTP_SECURITY=starttls).")
        if config.security == "starttls" and config.port == 465:
            warnings.append("Port 465 normally uses SSL (set SMTP_SECURITY=ssl).")
        if config.security == "none":
            warnings.append("SMTP_SECURITY=none sends credentials and links unencrypted; use only for a local test server.")
        if bool(config.username) != bool(config.password):
            problems.append("Set both SMTP_USERNAME and SMTP_PASSWORD, or neither.")
        if not config.mail_from or not EMAIL_RE.match(config.mail_from):
            problems.append("MAIL_FROM must be a valid email address.")
        elif PLACEHOLDER.search(config.mail_from):
            problems.append("MAIL_FROM still looks like a placeholder address.")
        if (config.host or "").endswith("gmail.com") and config.username and config.mail_from \
                and config.mail_from.lower() != config.username.lower():
            warnings.append("With Gmail, MAIL_FROM should be the signed-in address (or a verified alias); "
                            "otherwise Gmail rewrites or rejects the sender.")
    if config.mode == "brevo":
        if not config.api_key:
            problems.append("BREVO_API_KEY is not set.")
        if not config.mail_from or not EMAIL_RE.match(config.mail_from):
            problems.append("MAIL_FROM must be a valid email address (a sender verified in Brevo).")
        elif PLACEHOLDER.search(config.mail_from):
            problems.append("MAIL_FROM still looks like a placeholder address.")
    if not config.frontend_url.startswith(("http://", "https://")):
        problems.append("FRONTEND_URL must start with http:// or https://.")
    return {"mode": config.mode, "ok": not problems, "problems": problems, "warnings": warnings,
            "host": config.host, "port": config.port, "security": config.security,
            "sender_configured": bool(config.mail_from),
            "credentials_configured": bool(config.api_key) if config.mode == "brevo" else bool(config.username and config.password),
            "frontend_url": config.frontend_url}


# ------------------------------------------------------------------
# Templates (HTML + plain text, CareerNova branding)
# ------------------------------------------------------------------

@dataclass
class Rendered:
    subject: str
    text: str
    html: str


def _layout(title: str, paragraphs: list[str], button: tuple[str, str] | None, footer: str) -> str:
    body = "".join(f'<p style="margin:0 0 14px;line-height:1.55">{p}</p>' for p in paragraphs)
    cta = ""
    if button:
        label, url = button
        cta = (f'<p style="margin:22px 0"><a href="{html.escape(url, quote=True)}" '
               'style="background:#4f46e5;color:#ffffff;text-decoration:none;padding:12px 20px;border-radius:8px;'
               f'font-weight:600;display:inline-block">{html.escape(label)}</a></p>'
               '<p style="margin:0 0 14px;font-size:13px;color:#64748b;line-height:1.5">If the button does not work, '
               f'copy this link into your browser:<br><span style="word-break:break-all">{html.escape(url)}</span></p>')
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title></head>
<body style="margin:0;background:#f1f5f9;font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#0f172a">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:24px 12px"><tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border-radius:14px;border:1px solid #e2e8f0">
<tr><td style="padding:22px 28px;border-bottom:1px solid #e2e8f0">
<div style="font-size:18px;font-weight:700;color:#4f46e5">{PRODUCT}</div>
<div style="font-size:12px;color:#64748b">{TAGLINE}</div></td></tr>
<tr><td style="padding:26px 28px;font-size:15px">
<h1 style="font-size:20px;margin:0 0 16px">{html.escape(title)}</h1>{body}{cta}</td></tr>
<tr><td style="padding:16px 28px;border-top:1px solid #e2e8f0;font-size:12px;color:#64748b;line-height:1.5">{footer}</td></tr>
</table></td></tr></table></body></html>"""


def _text(title: str, lines: list[str], link: tuple[str, str] | None, footer: str) -> str:
    parts = [f"{PRODUCT} - {TAGLINE}", "", title, ""] + lines
    if link:
        parts += ["", f"{link[0]}:", link[1]]
    parts += ["", footer]
    return "\n".join(parts) + "\n"


def _greeting(first_name: str | None) -> str:
    return f"Hello {first_name.strip()}," if first_name and first_name.strip() else "Hello,"


def render(kind: str, *, first_name: str | None = None, link: str | None = None,
           expires_text: str | None = None, invited_by: str | None = None) -> Rendered:
    footer = f"You received this email because of an action on your {PRODUCT} account. " \
             "If this wasn't you, you can ignore it."
    greet = _greeting(first_name)
    if kind == "verification":
        title = "Verify your email address"
        lines = [greet, f"Thanks for creating your {PRODUCT} account. Confirm your email address to start "
                        "matching your skills with internships.", f"This link can be used once and expires in {expires_text}."]
        button = ("Verify email address", link)
    elif kind == "invitation":
        title = f"You're invited to {PRODUCT}"
        who = f"{invited_by} has" if invited_by else "An administrator has"
        lines = [greet, f"{who} created a {PRODUCT} account for you. Set your own password to activate it "
                        "and start building your career plan.",
                 f"This invitation can be used once and expires in {expires_text}. Nobody else knows or "
                 "chooses your password."]
        button = ("Activate my account", link)
    elif kind == "password_reset":
        title = "Reset your password"
        lines = [greet, f"We received a request to reset your {PRODUCT} password.",
                 f"This link can be used once and expires in {expires_text}. If you didn't ask for this, "
                 "ignore this email; your password stays the same."]
        button = ("Choose a new password", link)
    elif kind == "test":
        title = "Email delivery test"
        lines = [greet, f"This is a test message from {PRODUCT}. If you can read it, email delivery works."]
        button = None
    elif kind == "account_activated":
        title = "Your account is active"
        lines = [greet, f"Your {PRODUCT} account is active and your password is set. You can now sign in.",
                 "If you did not activate this account, contact your administrator immediately."]
        button = ("Sign in", link) if link else None
    else:
        raise ValueError(f"unknown email kind: {kind}")
    return Rendered(
        subject=f"{title} · {PRODUCT}",
        text=_text(title, lines, button, footer),
        html=_layout(title, [html.escape(line) for line in lines], button, html.escape(footer)),
    )


# ------------------------------------------------------------------
# Delivery
# ------------------------------------------------------------------

@dataclass
class DeliveryResult:
    status: str                 # sent | outboxed | skipped | failed
    error_code: str | None = None
    detail: str | None = None   # safe, human-readable (no secrets)
    delivery_id: int | None = None

    @property
    def delivered(self) -> bool:
        """True only when an SMTP server or the email provider accepted the message."""
        return self.status == "sent"

    @property
    def accepted(self) -> bool:
        """The flow can continue (sent, or captured in the outbox / deliberately disabled)."""
        return self.status in ("sent", "outboxed", "skipped")


def mask_email(address: str) -> str:
    local, _, domain = address.partition("@")
    return f"{local[:1]}***@{domain}" if domain else "***"


def build_message(config: MailConfig, to_email: str, rendered: Rendered) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = rendered.subject
    message["From"] = config.sender
    message["To"] = to_email
    message["Message-ID"] = make_msgid(domain=(config.mail_from or "careernova.local").split("@")[-1])
    message.set_content(rendered.text)
    message.add_alternative(rendered.html, subtype="html")
    return message


def _smtp_send(config: MailConfig, message: EmailMessage) -> None:
    context = ssl.create_default_context()
    if config.security == "ssl":
        server = smtplib.SMTP_SSL(config.host, config.port, timeout=config.timeout, context=context)
    else:
        server = smtplib.SMTP(config.host, config.port, timeout=config.timeout)
    with server:
        server.ehlo()
        if config.security == "starttls":
            server.starttls(context=context)
            server.ehlo()
        if config.username and config.password:
            server.login(config.username, config.password)
        refused = server.send_message(message)
        if refused:
            raise smtplib.SMTPRecipientsRefused(refused)


class ProviderError(RuntimeError):
    """An HTTPS email provider answered with an error (never carries the API key)."""

    def __init__(self, status: int):
        super().__init__(f"provider status {status}")
        self.status = status


def _brevo_send(config: MailConfig, to_email: str, rendered: Rendered) -> None:
    """Send one message through Brevo's HTTPS API. Raises on anything but 2xx."""
    body = json.dumps({
        "sender": {"name": config.from_name, "email": config.mail_from},
        "to": [{"email": to_email}],
        "subject": rendered.subject,
        "htmlContent": rendered.html,
        "textContent": rendered.text,
    }).encode("utf-8")
    request = urllib.request.Request(BREVO_URL, data=body, method="POST", headers={
        "api-key": config.api_key or "", "content-type": "application/json", "accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=config.timeout, context=ssl.create_default_context()) as response:
            if not 200 <= response.status < 300:
                raise ProviderError(response.status)
    except urllib.error.HTTPError as exc:
        raise ProviderError(exc.code) from None


def classify(exc: BaseException) -> tuple[str, str]:
    """Map an exception to a stable error code and a safe description (never includes credentials)."""
    if isinstance(exc, ProviderError):
        if exc.status in (401, 403):
            return "auth_failed", "The email provider rejected the API key (check BREVO_API_KEY and that the account is active)."
        if exc.status == 400:
            return "provider_rejected", ("The email provider rejected the message (check that MAIL_FROM is a verified "
                                         "sender in Brevo and the recipient address is valid).")
        if exc.status == 429:
            return "rate_limited", "The email provider's sending limit was reached; try again later."
        return "provider_error", f"The email provider returned an error (HTTP {exc.status})."
    if isinstance(exc, urllib.error.URLError):
        return "network_error", "Could not reach the email provider over HTTPS."
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        return "auth_failed", "The SMTP server rejected the username or password (for Gmail use an app password)."
    if isinstance(exc, smtplib.SMTPNotSupportedError):
        return "tls_not_supported", "The SMTP server does not support the configured security mode."
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return "sender_refused", "The SMTP server refused the sender address (check MAIL_FROM)."
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "recipient_refused", "The SMTP server refused the recipient address."
    if isinstance(exc, smtplib.SMTPConnectError | ConnectionRefusedError):
        return "connect_failed", "Could not connect to the SMTP server (check SMTP_HOST and SMTP_PORT)."
    if isinstance(exc, socket.timeout | TimeoutError):
        return "timeout", "The SMTP server did not respond in time."
    if isinstance(exc, ssl.SSLError):
        return "tls_failed", "The secure (TLS/SSL) connection failed (check SMTP_SECURITY and SMTP_PORT)."
    if isinstance(exc, smtplib.SMTPServerDisconnected):
        return "disconnected", "The SMTP server closed the connection."
    if isinstance(exc, smtplib.SMTPException):
        return "smtp_error", "The SMTP server returned an error."
    if isinstance(exc, OSError):
        return "network_error", "A network error occurred while contacting the SMTP server."
    return "unexpected_error", "Unexpected error while sending email."


def _record(kind: str, to_email: str, result: DeliveryResult, user_id: int | None,
            invitation_id: int | None) -> int | None:
    """Store the outcome in its own transaction. Never fails the caller."""
    try:
        from sqlalchemy import insert

        from backend import database
        from backend.models import EmailDelivery

        with database.engine.begin() as conn:
            return conn.execute(insert(EmailDelivery).values(
                kind=kind, recipient=to_email[:255], status=result.status, error_code=result.error_code,
                user_id=user_id, invitation_id=invitation_id,
                sent_at=datetime.now(timezone.utc) if result.status in ("sent", "outboxed") else None,
            ).returning(EmailDelivery.delivery_id)).scalar()
    except Exception:  # pragma: no cover - logging must never break delivery
        logger.exception("Could not record email delivery status")
        return None


def deliver(kind: str, to_email: str, rendered: Rendered, *, user_id: int | None = None,
            invitation_id: int | None = None, config: MailConfig | None = None) -> DeliveryResult:
    config = config or load_config()
    check = validate_config(config)
    if config.mode == "disabled":
        result = DeliveryResult("skipped", None, "Email is disabled (EMAIL_MODE=disabled).")
    elif not check["ok"]:
        result = DeliveryResult("failed", "config_invalid", " ".join(check["problems"]))
    elif config.mode == "outbox":
        try:
            config.outbox_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            path = config.outbox_dir / f"{stamp}-{kind}-{uuid.uuid4().hex[:8]}.eml"
            path.write_bytes(bytes(build_message(config, to_email, rendered)))
            result = DeliveryResult("outboxed", None, "Saved to the local email outbox (not sent).")
        except OSError as exc:
            result = DeliveryResult("failed", "outbox_failed", f"Could not write the outbox file ({type(exc).__name__}).")
    elif config.mode == "brevo":
        try:
            _brevo_send(config, to_email, rendered)
            result = DeliveryResult("sent", None, "Accepted by the email provider (Brevo).")
        except Exception as exc:  # classified below; never re-raised with secrets
            code, detail = classify(exc)
            result = DeliveryResult("failed", code, detail)
    else:
        try:
            _smtp_send(config, build_message(config, to_email, rendered))
            result = DeliveryResult("sent", None, "Accepted by the SMTP server.")
        except Exception as exc:  # classified below; never re-raised with secrets
            code, detail = classify(exc)
            result = DeliveryResult("failed", code, detail)
    log = logger.info if result.accepted else logger.warning
    log("email kind=%s to=%s mode=%s status=%s error=%s", kind, mask_email(to_email), config.mode,
        result.status, result.error_code)
    result.delivery_id = _record(kind, to_email, result, user_id, invitation_id)
    return result


def frontend_link(path: str, token: str | None = None) -> str:
    from urllib.parse import quote

    base = load_config().frontend_url
    return f"{base}{path}" + (f"?token={quote(token, safe='')}" if token else "")
