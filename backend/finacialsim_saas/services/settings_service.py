from __future__ import annotations

from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.data.models import SystemSetting
from finacialsim_saas.settings import get_settings

WRITABLE_KEYS: frozenset[str] = frozenset({
    "smtp_host", "smtp_port", "smtp_user", "smtp_password",
    "smtp_tls", "smtp_from", "email_provider",
})
READ_ONLY_KEYS: frozenset[str] = frozenset({"pix_provider", "pix_webhook_secret"})
ALL_KEYS: frozenset[str] = WRITABLE_KEYS | READ_ONLY_KEYS


def _env_default(key: str) -> str:
    s = get_settings()
    mapping: dict[str, str] = {
        "smtp_host": s.smtp_host,
        "smtp_port": str(s.smtp_port),
        "smtp_user": s.smtp_user,
        "smtp_password": s.smtp_password,
        "smtp_tls": str(s.smtp_tls).lower(),
        "smtp_from": s.smtp_from,
        "email_provider": s.email_provider,
        "pix_provider": s.pix_provider,
        "pix_webhook_secret": s.pix_webhook_secret,
    }
    return mapping[key]


class SettingsService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get_all(self) -> dict[str, tuple[str, Literal["db", "env"]]]:
        """Returns {key: (value, source)} for all managed keys."""
        db_rows = (await self._s.scalars(select(SystemSetting))).all()
        db_map = {row.key: row.value for row in db_rows}
        result: dict[str, tuple[str, Literal["db", "env"]]] = {}
        for key in ALL_KEYS:
            if key in READ_ONLY_KEYS:
                result[key] = (_env_default(key), "env")
            elif key in db_map:
                result[key] = (db_map[key], "db")
            else:
                result[key] = (_env_default(key), "env")
        return result

    async def update(self, key: str, value: str, updated_by: str) -> None:
        """Upsert a writable key. Caller must commit."""
        if key in READ_ONLY_KEYS:
            raise ValueError(f"Key {key!r} is read-only")
        if key not in WRITABLE_KEYS:
            raise ValueError(f"Unknown settings key: {key!r}")
        row = await self._s.get(SystemSetting, key)
        if row is None:
            self._s.add(SystemSetting(key=key, value=value, updated_by=updated_by))
        else:
            row.value = value
            row.updated_by = updated_by
            row.updated_at = func.now()
