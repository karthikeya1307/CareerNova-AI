# Email (SMTP) Setup — CareerNova AI

CareerNova AI sends four kinds of email: **email verification** (self-registration), **invitation**
(admin-created account → the person sets their own password), **password reset**, and **account
activated** (confirmation). All are branded HTML with a plain-text alternative, and links open the
frontend (`FRONTEND_URL`).

## Modes — nothing is sent unless you choose `smtp`

| `EMAIL_MODE` | What happens |
|---|---|
| `outbox` (**default**) | Nothing is sent. Each message is saved as an `.eml` file in `EMAIL_OUTBOX_DIR` (default `uploads/email_outbox/`, git-ignored). Open it in any mail client or text editor to follow the link. Use this for demos and testing. |
| `smtp` | Messages are sent through your SMTP server. Enable only when real emails are authorised. |
| `disabled` | Nothing is sent or saved. |

Outbox files contain working one-time links; they stay on this machine and are excluded from git.

## Settings (`.env` — never commit this file)

| Variable | Example | Notes |
|---|---|---|
| `EMAIL_MODE` | `outbox` | `outbox`, `smtp` or `disabled` |
| `FRONTEND_URL` | `http://localhost:5173` | Base of every link in emails |
| `SMTP_HOST` | `smtp.gmail.com` | |
| `SMTP_PORT` | `587` | 587 = STARTTLS, 465 = SSL |
| `SMTP_SECURITY` | `starttls` | `starttls` (default), `ssl` (default when port is 465) or `none` (local test servers only) |
| `SMTP_USERNAME` | your mailbox | |
| `SMTP_PASSWORD` | app password | Spaces are removed automatically (Gmail shows app passwords in groups of four) |
| `MAIL_FROM` | same as `SMTP_USERNAME` for Gmail | Must be a real address — placeholders are rejected |
| `MAIL_FROM_NAME` | `CareerNova AI` | Display name |
| `SMTP_TIMEOUT_SECONDS` | `15` | |

### Gmail
1. Turn on 2-Step Verification for the Google account.
2. Create an **App password** (Google Account → Security → App passwords) and put it in `SMTP_PASSWORD`.
3. Set `MAIL_FROM` to the **same Gmail address** (or a verified "Send mail as" alias) — otherwise Gmail rewrites or rejects the sender.
4. Gmail is fine for development and small pilots (about 500 messages/day). For production use a
   transactional provider (Amazon SES, Postmark, SendGrid, Brevo, Mailgun) with SPF/DKIM on your own
   domain; they all work with the same SMTP settings.

## Check the configuration (sends nothing)

```powershell
.\.venv\Scripts\python.exe -m backend.manage email-check
```

Prints the mode, server, port, security, whether credentials and sender are configured, and any
problems/warnings — **never** the username, password or sender address. Admins can see the same
report (plus delivery counts) at `GET /admin/email/status`.

Current finding (2026-11-19): `.env` has `SMTP_HOST=smtp.gmail.com`, port 587, credentials set, but
`MAIL_FROM` is still a placeholder (`your_actual_…`) — fix it before switching to `smtp` mode.

## Send one test message (owner authorisation required in `smtp` mode)

```powershell
$env:EMAIL_MODE = 'smtp'
.\.venv\Scripts\python.exe -m backend.manage email-check --send-test you@yourdomain.com
```

In `outbox` mode the same command only writes a file.

## Delivery status and failures

* Every attempt is recorded in `email_deliveries` (kind, recipient, status, error code — never the
  body, links or tokens). Statuses: `sent` (accepted by the SMTP server), `outboxed`, `skipped`, `failed`.
  A message is never reported as sent unless the server accepted it.
* Failure codes: `auth_failed`, `connect_failed`, `timeout`, `tls_failed`, `tls_not_supported`,
  `sender_refused`, `recipient_refused`, `disconnected`, `smtp_error`, `network_error`, `config_invalid`.
* Logs show the kind, a masked recipient (`a***@domain`), the mode and the outcome — never credentials.
* Admins: **Admin → Users** shows each pending account's invitation and email status, with
  **Resend invitation**; `GET /admin/email/deliveries` lists recent outcomes.

## Limits

* Invitations: single use, expire after 72 hours, a new one revokes the previous; at most one per
  account per minute and five per day.
* Password reset: at most one email per account per minute (same response either way); links expire
  after 30 minutes. Verification resend: one per minute.
