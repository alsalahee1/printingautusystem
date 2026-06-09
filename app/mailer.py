"""Outgoing email via SMTP, configured from Settings.

send_email returns (ok, message). It never raises into the request handler —
SMTP problems (or missing configuration) come back as a friendly message that
the caller surfaces as a flash.
"""
import smtplib
from email.message import EmailMessage


def is_configured(settings) -> bool:
    return bool(settings.smtp_host and (settings.smtp_from or settings.smtp_user))


def send_email(settings, to: str, subject: str, body: str,
               attachment: bytes | None = None, attachment_name: str = "document.pdf"):
    if not is_configured(settings):
        return False, "Email is not configured. Add SMTP settings under Settings first."
    if not to:
        return False, "No recipient email address."

    msg = EmailMessage()
    msg["From"] = settings.smtp_from or settings.smtp_user
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    if attachment is not None:
        msg.add_attachment(attachment, maintype="application", subtype="pdf",
                           filename=attachment_name)

    try:
        if settings.smtp_use_tls:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port or 587, timeout=20) as s:
                s.starttls()
                if settings.smtp_user:
                    s.login(settings.smtp_user, settings.smtp_pass)
                s.send_message(msg)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port or 25, timeout=20) as s:
                if settings.smtp_user:
                    s.login(settings.smtp_user, settings.smtp_pass)
                s.send_message(msg)
    except Exception as exc:  # noqa: BLE001 - report any SMTP failure to the user
        return False, f"Could not send email: {exc}"
    return True, f"Email sent to {to}."
