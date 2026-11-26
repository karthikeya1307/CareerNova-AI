"""Phase 2: the email module (modes, SMTP security, failures, templates, delivery log).

No real mail server is contacted: SMTP classes are replaced by fakes, and conftest forces
EMAIL_MODE=outbox in a temporary folder unless a test sets it explicitly.
"""

import email
import logging
import smtplib
import socket
from email import policy

import pytest
from sqlalchemy import select

from backend.models import EmailDelivery
from backend.services import email_service, mailer

SECRET = "app-pass-word-1234"


class FakeSMTP:
    """Records the conversation; ``fail`` makes one step raise."""

    instances: list["FakeSMTP"] = []
    fail: dict = {}

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port, self.timeout, self.context = host, port, timeout, context
        self.calls = []
        self.ssl = False
        FakeSMTP.instances.append(self)
        if "connect" in self.fail:
            raise self.fail["connect"]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.calls.append("quit")

    def ehlo(self):
        self.calls.append("ehlo")

    def starttls(self, context=None):
        self.calls.append("starttls")
        if "starttls" in self.fail:
            raise self.fail["starttls"]

    def login(self, user, password):
        self.calls.append(("login", user))
        if "login" in self.fail:
            raise self.fail["login"]

    def send_message(self, message):
        self.calls.append("send")
        self.message = message
        if "send" in self.fail:
            raise self.fail["send"]
        return {}


class FakeSMTPSSL(FakeSMTP):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ssl = True


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.instances, FakeSMTP.fail = [], {}
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", FakeSMTPSSL)
    monkeypatch.setenv("EMAIL_MODE", "smtp")
    monkeypatch.setenv("SMTP_HOST", "smtp.mail.test")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.delenv("SMTP_SECURITY", raising=False)
    monkeypatch.setenv("SMTP_USERNAME", "sender@mail.test")
    monkeypatch.setenv("SMTP_PASSWORD", SECRET)
    monkeypatch.setenv("MAIL_FROM", "sender@mail.test")
    return FakeSMTP


def rendered():
    return mailer.render("invitation", first_name="Anu", link="http://localhost:5173/accept-invitation?token=abc",
                         expires_text="72 hours", invited_by="Ada Admin")


def deliveries(db_session):
    db_session.expire_all()
    return db_session.scalars(select(EmailDelivery).order_by(EmailDelivery.delivery_id)).all()


# ------------------------------------------------------------------
# Modes
# ------------------------------------------------------------------

def test_outbox_mode_writes_a_complete_message_and_sends_nothing(tmp_path, monkeypatch, db_session, smtp):
    monkeypatch.setenv("EMAIL_MODE", "outbox")
    monkeypatch.setenv("EMAIL_OUTBOX_DIR", str(tmp_path / "box"))
    result = mailer.deliver("invitation", "anu@example.com", rendered())
    assert result.status == "outboxed" and not result.delivered and result.accepted
    assert smtp.instances == []                                    # no connection at all
    [path] = list((tmp_path / "box").glob("*.eml"))
    message = email.message_from_bytes(path.read_bytes(), policy=policy.default)
    assert message["To"] == "anu@example.com" and "CareerNova AI" in message["From"]
    assert message["Subject"] == "You're invited to CareerNova AI · CareerNova AI"
    text = message.get_body(("plain",)).get_content()
    html = message.get_body(("html",)).get_content()
    assert "Your Skills. Your Potential. Your Career." in text and "accept-invitation?token=abc" in text
    assert "Activate my account" in html and "Ada Admin has created" in html
    [row] = deliveries(db_session)
    assert (row.kind, row.recipient, row.status, row.error_code) == ("invitation", "anu@example.com", "outboxed", None)


def test_disabled_mode_skips(monkeypatch, smtp):
    monkeypatch.setenv("EMAIL_MODE", "disabled")
    result = mailer.deliver("verification", "a@example.com", rendered())
    assert result.status == "skipped" and smtp.instances == []


def test_default_mode_is_outbox(monkeypatch):
    monkeypatch.delenv("EMAIL_MODE", raising=False)
    assert mailer.load_config().mode == "outbox"


# ------------------------------------------------------------------
# SMTP security and authentication
# ------------------------------------------------------------------

def test_starttls_on_587_with_login(smtp, db_session):
    result = mailer.deliver("verification", "a@example.com", rendered())
    assert result.status == "sent" and result.delivered
    [conn] = smtp.instances
    assert (conn.host, conn.port, conn.ssl) == ("smtp.mail.test", 587, False)
    assert conn.calls == ["ehlo", "starttls", "ehlo", ("login", "sender@mail.test"), "send", "quit"]
    assert deliveries(db_session)[0].status == "sent" and deliveries(db_session)[0].sent_at is not None


def test_ssl_on_465(smtp, monkeypatch):
    monkeypatch.setenv("SMTP_PORT", "465")
    assert mailer.deliver("verification", "a@example.com", rendered()).status == "sent"
    [conn] = smtp.instances
    assert conn.ssl and "starttls" not in conn.calls


def test_app_password_spaces_are_removed(monkeypatch):
    monkeypatch.setenv("SMTP_PASSWORD", "abcd efgh ijkl mnop")
    assert mailer.load_config().password == "abcdefghijklmnop"


@pytest.mark.parametrize("step, exc, code", [
    ("login", smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted"), "auth_failed"),
    ("connect", ConnectionRefusedError(), "connect_failed"),
    ("connect", socket.timeout("timed out"), "timeout"),
    ("starttls", smtplib.SMTPNotSupportedError("STARTTLS extension not supported"), "tls_not_supported"),
    ("send", smtplib.SMTPSenderRefused(553, b"sender not allowed", "sender@mail.test"), "sender_refused"),
    ("send", smtplib.SMTPRecipientsRefused({"a@example.com": (550, b"no such user")}), "recipient_refused"),
    ("send", smtplib.SMTPServerDisconnected("closed"), "disconnected"),
])
def test_failures_are_classified_recorded_and_never_reported_as_sent(smtp, db_session, caplog, step, exc, code):
    smtp.fail = {step: exc}
    with caplog.at_level(logging.INFO, logger="careernova.email"):
        result = mailer.deliver("invitation", "anu@example.com", rendered())
    assert result.status == "failed" and result.error_code == code and not result.accepted
    assert SECRET not in (result.detail or "")
    [row] = deliveries(db_session)
    assert (row.status, row.error_code, row.sent_at) == ("failed", code, None)
    log = caplog.text
    assert SECRET not in log and "anu@example.com" not in log and "a***@example.com" in log


def test_invalid_configuration_fails_without_connecting(smtp, monkeypatch):
    monkeypatch.setenv("MAIL_FROM", "your_actual_gmail@gmail.com")
    result = mailer.deliver("verification", "a@example.com", rendered())
    assert result.status == "failed" and result.error_code == "config_invalid"
    assert "placeholder" in result.detail and smtp.instances == []


# ------------------------------------------------------------------
# Configuration validation
# ------------------------------------------------------------------

def test_validation_reports_problems_and_warnings_without_secrets(smtp, monkeypatch):
    assert mailer.validate_config()["ok"] is True
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_USERNAME", "real.account@gmail.com")
    monkeypatch.setenv("MAIL_FROM", "other@company.test")
    monkeypatch.setenv("SMTP_SECURITY", "ssl")
    report = mailer.validate_config()
    assert report["ok"] is True
    assert any("Gmail" in w for w in report["warnings"]) and any("587" in w for w in report["warnings"])
    assert SECRET not in str(report) and "real.account" not in str(report)

    monkeypatch.delenv("SMTP_HOST")
    monkeypatch.setenv("SMTP_PASSWORD", "")
    monkeypatch.setenv("EMAIL_MODE", "smtp")
    problems = mailer.validate_config()["problems"]
    assert "SMTP_HOST is not set." in problems
    assert any("both SMTP_USERNAME and SMTP_PASSWORD" in p for p in problems)


def test_unknown_mode_is_rejected(monkeypatch):
    monkeypatch.setenv("EMAIL_MODE", "carrier-pigeon")
    assert mailer.validate_config()["ok"] is False


# ------------------------------------------------------------------
# Account email wrappers and templates
# ------------------------------------------------------------------

def test_verification_and_reset_links_point_at_the_frontend(tmp_path, monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", "https://app.careernova.test/")
    email_service.send_verification_email("a@example.com", "tok-123")
    email_service.send_password_reset_email("a@example.com", "tok/456")
    texts = [email.message_from_bytes(p.read_bytes(), policy=policy.default).get_body(("plain",)).get_content()
             for p in sorted((tmp_path / "email_outbox").glob("*.eml"))]
    joined = "\n".join(texts)
    assert "https://app.careernova.test/auth/verify-email?token=tok-123" in joined
    assert "https://app.careernova.test/reset-password?token=tok%2F456" in joined
    assert "/docs" not in joined                                       # no more "use the API docs" instructions


def test_wrappers_raise_when_delivery_fails_so_auth_flows_can_report_it(smtp):
    smtp.fail = {"connect": ConnectionRefusedError()}
    with pytest.raises(RuntimeError):
        email_service.send_verification_email("a@example.com", "tok")
    result = email_service.send_invitation_email("a@example.com", "tok", first_name="A")
    assert result.status == "failed"                                   # invitations report, never raise


@pytest.mark.parametrize("kind", ["verification", "invitation", "password_reset", "account_activated"])
def test_every_template_is_branded_and_escapes_html(kind):
    out = mailer.render(kind, first_name="<b>Eve</b>", link="http://localhost:5173/x?token=a&b=1",
                        expires_text="1 hour", invited_by="<script>")
    assert "CareerNova AI" in out.subject and "CareerNova AI" in out.text and "CareerNova AI" in out.html
    assert "<b>Eve</b>" not in out.html and "&lt;b&gt;Eve&lt;/b&gt;" in out.html
    assert "<script>" not in out.html


def test_email_check_command_reports_without_secrets(smtp, capsys, monkeypatch):
    from backend import manage

    assert manage.main(["email-check"]) == 0
    out = capsys.readouterr().out
    assert "Configuration OK." in out and SECRET not in out and "sender@mail.test" not in out
    monkeypatch.setenv("MAIL_FROM", "your_actual_gmail@gmail.com")
    assert manage.main(["email-check"]) == 1
    assert "PROBLEM: MAIL_FROM still looks like a placeholder address." in capsys.readouterr().out


def test_email_check_send_test_in_outbox_mode(monkeypatch, tmp_path, capsys):
    from backend import manage

    assert manage.main(["email-check", "--send-test", "owner@example.com"]) == 0
    assert "Test message: outboxed" in capsys.readouterr().out
    assert list((tmp_path / "email_outbox").glob("*-test-*.eml"))


# ---- Brevo HTTPS API mode (no network: urlopen is replaced) ---------------------------------------------
BREVO_KEY = "xkeysib-test-not-a-real-key"


class FakeResponse:
    status = 201

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def brevo(monkeypatch):
    monkeypatch.setenv("EMAIL_MODE", "brevo")
    monkeypatch.setenv("BREVO_API_KEY", BREVO_KEY)
    monkeypatch.setenv("MAIL_FROM", "sender@mail.test")
    monkeypatch.setenv("FRONTEND_URL", "https://careernova.test")
    calls = []

    def fake_urlopen(request, timeout=None, context=None):
        calls.append({"url": request.full_url, "headers": dict(request.header_items()),
                      "body": request.data, "timeout": timeout})
        if calls_fail:
            raise calls_fail[0]
        return FakeResponse()

    calls_fail = []
    monkeypatch.setattr(mailer.urllib.request, "urlopen", fake_urlopen)
    return calls, calls_fail


def test_brevo_sends_over_https_with_the_api_key_header(brevo, db_session):
    import json

    calls, _ = brevo
    rendered = mailer.render("verification", first_name="Asha", link="https://careernova.test/verify-email?token=t")
    result = mailer.deliver("verification", "asha@mail.test", rendered)
    assert result.status == "sent" and result.delivered and "Brevo" in result.detail
    [call] = calls
    assert call["url"] == "https://api.brevo.com/v3/smtp/email"
    assert call["headers"]["Api-key"] == BREVO_KEY
    body = json.loads(call["body"])
    assert body["sender"]["email"] == "sender@mail.test" and body["to"] == [{"email": "asha@mail.test"}]
    assert "Verify your email address" in body["subject"] and "verify-email?token=t" in body["htmlContent"]
    record = db_session.scalar(select(EmailDelivery).where(EmailDelivery.delivery_id == result.delivery_id))
    assert record.status == "sent"


@pytest.mark.parametrize("status, code", [(401, "auth_failed"), (400, "provider_rejected"),
                                          (429, "rate_limited"), (500, "provider_error")])
def test_brevo_errors_are_classified_and_never_reported_as_sent(brevo, caplog, status, code):
    import urllib.error

    calls, fail = brevo
    fail.append(urllib.error.HTTPError("https://api.brevo.com/v3/smtp/email", status, "error", {}, None))
    with caplog.at_level(logging.INFO, logger="careernova.email"):
        result = mailer.deliver("test", "asha@mail.test", mailer.render("test"))
    assert result.status == "failed" and result.error_code == code and not result.accepted
    assert BREVO_KEY not in (result.detail or "") and BREVO_KEY not in caplog.text


def test_brevo_network_failure_is_reported(brevo):
    import urllib.error

    _, fail = brevo
    fail.append(urllib.error.URLError("unreachable"))
    result = mailer.deliver("test", "asha@mail.test", mailer.render("test"))
    assert result.status == "failed" and result.error_code == "network_error"


def test_brevo_configuration_is_validated_without_contacting_anyone(brevo, monkeypatch):
    calls, _ = brevo
    monkeypatch.setenv("BREVO_API_KEY", "")
    monkeypatch.setenv("MAIL_FROM", "your_sender_gmail@gmail.com")
    check = mailer.validate_config()
    assert not check["ok"] and any("BREVO_API_KEY" in p for p in check["problems"])
    assert any("placeholder" in p for p in check["problems"])
    assert mailer.deliver("test", "asha@mail.test", mailer.render("test")).error_code == "config_invalid"
    assert calls == []
    assert BREVO_KEY not in repr(mailer.load_config())
