from __future__ import annotations

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from finacialsim_saas.settings import Settings


class EmailChannel:
    def __init__(self, settings: Settings) -> None:
        self._s = settings

    async def send(self, *, to: str, subject: str, body_html: str, body_txt: str) -> None:
        """Send a multipart email via SMTP. Raises on any delivery failure."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self._s.smtp_from
        msg["To"] = to
        msg.attach(MIMEText(body_txt, "plain", "utf-8"))
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        await aiosmtplib.send(
            msg,
            hostname=self._s.smtp_host,
            port=self._s.smtp_port,
            username=self._s.smtp_user or None,
            password=self._s.smtp_password or None,
            use_tls=self._s.smtp_tls,
        )
