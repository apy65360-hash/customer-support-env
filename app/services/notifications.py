import logging
import smtplib
from email.mime.text import MIMEText

from app.config import settings

logger = logging.getLogger(__name__)


def send_notification(to_email: str, subject: str, body: str) -> None:
    """Stub email notification. Logs if SMTP is not configured."""
    if not settings.SMTP_HOST or settings.SMTP_HOST == "localhost":
        logger.info(
            "NOTIFICATION (stub) → %s | Subject: %s | Body: %.120s…",
            to_email,
            subject,
            body,
        )
        return

    try:
        msg = MIMEText(body, "plain")
        msg["Subject"] = subject
        msg["From"] = settings.EMAIL_FROM
        msg["To"] = to_email

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            if settings.SMTP_USER:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.EMAIL_FROM, [to_email], msg.as_string())
    except Exception:
        logger.exception("Failed to send email to %s", to_email)


def notify_new_comment(ticket_id: int, comment_author: str, recipient_email: str) -> None:
    send_notification(
        to_email=recipient_email,
        subject=f"[Ticket #{ticket_id}] New comment from {comment_author}",
        body=(
            f"A new comment was added to ticket #{ticket_id} by {comment_author}.\n\n"
            "Please log in to view the full conversation."
        ),
    )
