
import os
import ssl
import smtplib

from pathlib import Path
from email.message import EmailMessage
from dotenv import load_dotenv


# Load environment variables from the project's .env file
BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").replace(" ", "")
MAIL_FROM = os.getenv("MAIL_FROM") or SMTP_USERNAME

APP_BASE_URL = os.getenv(
    "APP_BASE_URL",
    "http://127.0.0.1:8000"
)


def send_verification_email(to_email: str, token: str) -> None:
    """
    Send an email containing a one-time verification link.
    """

    if not SMTP_USERNAME or not SMTP_PASSWORD or not MAIL_FROM:
        raise RuntimeError(
            "SMTP configuration is missing from .env"
        )

    verification_link = (
        f"{APP_BASE_URL.rstrip('/')}"
        f"/auth/verify-email?token={token}"
    )

    message = EmailMessage()

    message["Subject"] = "Verify your AI Career Companion account"
    message["From"] = MAIL_FROM
    message["To"] = to_email

    message.set_content(
        f"""
Hello,

Thank you for registering with AI Career Companion.

Please verify your email address using the link below:

{verification_link}

This link is intended for one-time use.

If you did not create this account, you can ignore this email.

Regards,
AI Career Companion Team
"""
    )

    context = ssl.create_default_context()

    with smtplib.SMTP(
        SMTP_HOST,
        SMTP_PORT,
        timeout=20
    ) as server:

        server.ehlo()
        server.starttls(context=context)
        server.ehlo()

        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(message)

def send_password_reset_email(to_email: str, token: str) -> None:
    """Send a password-reset token by email."""

    if not SMTP_USERNAME or not SMTP_PASSWORD or not MAIL_FROM:
        raise RuntimeError("SMTP configuration is missing from .env")

    docs_link = f"{APP_BASE_URL.rstrip('/')}/docs"

    message = EmailMessage()
    message["Subject"] = "Reset your AI Career Companion password"
    message["From"] = MAIL_FROM
    message["To"] = to_email

    message.set_content(
        f"""
Hello,

We received a request to reset your AI Career Companion password.

Your password-reset token is:

{token}

This token expires in 30 minutes and can only be used once.

To reset your password:

1. Open the API documentation:
   {docs_link}

2. Find POST /auth/reset-password.

3. Submit the token and your new password.

If you did not request a password reset, you can ignore this email.

Regards,
AI Career Companion Team
"""
    )

    context = ssl.create_default_context()

    with smtplib.SMTP(
        SMTP_HOST,
        SMTP_PORT,
        timeout=20
    ) as server:
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()

        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(message)
