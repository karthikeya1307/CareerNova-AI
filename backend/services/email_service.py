"""Account emails (verification, password reset, invitation, activation).

Thin wrappers around ``backend.services.mailer`` (modes, SMTP, templates, delivery log).
``send_verification_email`` and ``send_password_reset_email`` keep their original signatures and
raise ``RuntimeError`` when the message could not be delivered, so the existing auth flows keep
their behaviour (e.g. 503 after registration). Links point at the frontend (FRONTEND_URL).

In the default EMAIL_MODE=outbox nothing is sent: messages are written to the local outbox folder.
"""

from __future__ import annotations

from backend.services import mailer

VERIFICATION_EXPIRES_TEXT = "24 hours"
RESET_EXPIRES_TEXT = "30 minutes"
INVITATION_EXPIRES_TEXT = "72 hours"


class EmailDeliveryError(RuntimeError):
    def __init__(self, result: mailer.DeliveryResult):
        super().__init__(result.detail or "Email could not be delivered")
        self.result = result


def _require(result: mailer.DeliveryResult) -> mailer.DeliveryResult:
    if not result.accepted:
        raise EmailDeliveryError(result)
    return result


def send_verification_email(to_email: str, token: str, user_id: int | None = None) -> mailer.DeliveryResult:
    rendered = mailer.render("verification", link=mailer.frontend_link("/auth/verify-email", token),
                             expires_text=VERIFICATION_EXPIRES_TEXT)
    return _require(mailer.deliver("verification", to_email, rendered, user_id=user_id))


def send_password_reset_email(to_email: str, token: str, user_id: int | None = None) -> mailer.DeliveryResult:
    rendered = mailer.render("password_reset", link=mailer.frontend_link("/reset-password", token),
                             expires_text=RESET_EXPIRES_TEXT)
    return _require(mailer.deliver("password_reset", to_email, rendered, user_id=user_id))


def send_invitation_email(to_email: str, token: str, *, first_name: str | None = None,
                          invited_by: str | None = None, user_id: int | None = None,
                          invitation_id: int | None = None) -> mailer.DeliveryResult:
    """Returns the outcome instead of raising: the account and invitation exist either way and the
    administrator sees the delivery status (and can resend)."""
    rendered = mailer.render("invitation", first_name=first_name, invited_by=invited_by,
                             link=mailer.frontend_link("/accept-invitation", token),
                             expires_text=INVITATION_EXPIRES_TEXT)
    return mailer.deliver("invitation", to_email, rendered, user_id=user_id, invitation_id=invitation_id)


def send_account_activated_email(to_email: str, first_name: str | None = None,
                                 user_id: int | None = None) -> mailer.DeliveryResult:
    rendered = mailer.render("account_activated", first_name=first_name, link=mailer.frontend_link("/login"))
    return mailer.deliver("account_activated", to_email, rendered, user_id=user_id)
