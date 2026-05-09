import logging
from email.message import EmailMessage as MimeMessage
from typing import Protocol

import aiosmtplib
from pydantic import BaseModel, Field

from .settings import Settings, get_settings

logger = logging.getLogger(__name__)


class EmailMessage(BaseModel):
    to: list[str] = Field(min_length=1)
    subject: str
    text: str
    html: str | None = None


class EmailBackend(Protocol):
    async def send(self, msg: EmailMessage) -> None: ...


class ConsoleBackend:
    async def send(self, msg: EmailMessage) -> None:
        logger.info(
            "email (console): to=%s subject=%s text=%r html=%r",
            msg.to,
            msg.subject,
            msg.text,
            msg.html,
        )


class SmtpBackend:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def send(self, msg: EmailMessage) -> None:
        mime = MimeMessage()
        mime["From"] = self._settings.email_from
        mime["To"] = ", ".join(msg.to)
        mime["Subject"] = msg.subject
        mime.set_content(msg.text)
        if msg.html is not None:
            mime.add_alternative(msg.html, subtype="html")

        username = self._settings.smtp_username or None
        password = self._settings.smtp_password or None

        await aiosmtplib.send(
            mime,
            hostname=self._settings.smtp_host,
            port=self._settings.smtp_port,
            username=username,
            password=password,
            start_tls=self._settings.smtp_starttls,
        )


def get_mailer() -> EmailBackend:
    settings = get_settings()
    if settings.email_backend == "smtp":
        return SmtpBackend(settings)
    return ConsoleBackend()
