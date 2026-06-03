from __future__ import annotations

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib


class EmailChannel:
    def __init__(
        self,
        *,
        smtp_host: str,
        smtp_port: int,
        smtp_user: str,
        smtp_password: str,
        smtp_tls: bool,
        smtp_from: str,
    ) -> None:
        self._host = smtp_host
        self._port = smtp_port
        self._user = smtp_user or None
        self._password = smtp_password or None
        self._tls = smtp_tls
        self._from = smtp_from

    async def send(
        self, *, to: str, subject: str, body_html: str, body_txt: str
    ) -> None:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self._from
        msg["To"] = to
        msg.attach(MIMEText(body_txt, "plain", "utf-8"))
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        await aiosmtplib.send(
            msg,
            hostname=self._host,
            port=self._port,
            username=self._user,
            password=self._password,
            use_tls=self._tls,
        )
