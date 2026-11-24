"""Account emails (welcome, password reset) through Flask-Mail.

With ``SMTP_ENABLED=1`` messages go out over STARTTLS with the same ``SMTP_*`` settings as alert delivery.
Otherwise each message is written as an ``.eml`` file to a private local outbox, so registration and
password reset can be demonstrated without a mail account. Tests suppress sending entirely.
"""

from datetime import datetime, timezone
import logging
import os
from pathlib import Path
import secrets
import smtplib

from flask import current_app, render_template
from flask_mail import Message

from app.extensions import mail
from app.i18n import translate
from app.services.alerts import VerifiedSMTPConnection
from config import APP_NAME

log = logging.getLogger("h_logsen.accounts")


def outbox_directory():
    configured = current_app.config.get("MAIL_OUTBOX_DIR") or os.environ.get("MAIL_OUTBOX_DIR")
    return Path(configured) if configured else Path.home() / ".h-logsen" / "outbox"


def account_message(subject, recipient, template, **context):
    if any(character in recipient for character in "\r\n,;"):
        raise ValueError("Invalid recipient address.")
    sender = os.environ.get("SMTP_FROM") or "h-logsen@localhost"
    return Message(
        subject=f"{APP_NAME} · {translate(subject)}",
        sender=sender,
        recipients=[recipient],
        body=render_template(template + ".txt", app_name=APP_NAME, **context),
        html=render_template(template + ".html", app_name=APP_NAME, **context),
    )


def send_account_mail(subject, recipient, template, **context):
    """Deliver one account email. Returns "sent", "outbox" or "suppressed"; never raises on SMTP errors."""
    message = account_message(subject, recipient, template, **context)
    if current_app.testing or current_app.config.get("MAIL_SUPPRESS_SEND"):
        current_app.extensions.setdefault("account_outbox", []).append(message)
        return "suppressed"
    if os.environ.get("SMTP_ENABLED") == "1":
        state = mail.init_mail(
            {
                "MAIL_SERVER": os.environ.get("SMTP_HOST", ""),
                "MAIL_PORT": int(os.environ.get("SMTP_PORT", "587")),
                "MAIL_USERNAME": os.environ.get("SMTP_USER"),
                "MAIL_PASSWORD": os.environ.get("SMTP_PASSWORD"),
                "MAIL_USE_TLS": True,
                "MAIL_SUPPRESS_SEND": False,
            }
        )
        try:
            with VerifiedSMTPConnection(state, smtplib.SMTP) as connection:
                connection.send(message)
            return "sent"
        except (OSError, smtplib.SMTPException):
            log.exception("account email could not be delivered; writing it to the local outbox")
    folder = outbox_directory()
    folder.mkdir(parents=True, exist_ok=True)
    try:
        folder.chmod(0o700)
    except OSError:
        pass
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = folder / f"{stamp}-{secrets.token_hex(4)}.eml"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(message.as_string())
    log.warning("SMTP is not enabled: account email written to %s", path)
    return "outbox"
