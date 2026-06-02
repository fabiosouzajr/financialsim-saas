from __future__ import annotations

import contextvars
import json
import re
import sys
from typing import Any

from loguru import logger

# Context vars set by auth/deps.py after JWT decoding — read by the patcher
_log_tenant_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "log_tenant_id", default=None
)
_log_user_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "log_user_id", default=None
)

_PII_KEYS = frozenset({"email", "cpf_cnpj", "password", "senha", "target_email", "recipient"})
_PII_PATTERNS = [
    re.compile(r"[\w.+%-]+@[\w.-]+\.[a-zA-Z]{2,}"),          # email addresses
    re.compile(r"\d{3}\.?\d{3}\.?\d{3}-?\d{2}"),              # CPF
    re.compile(r"\d{2}\.?\d{3}\.?\d{3}[/.]?\d{4}-?\d{2}"),   # CNPJ
]


def _mask_string(s: str) -> str:
    """Apply regex PII patterns to a free-form string."""
    for pattern in _PII_PATTERNS:
        s = pattern.sub("[REDACTED]", s)
    return s


def _pii_patcher(record: dict[str, Any]) -> None:
    """Loguru global patcher: masks known PII keys in structured extra fields.

    Also enriches record with tenant_id and user_id from contextvars when available.
    """
    extra = record["extra"]
    for key in list(extra.keys()):
        if key in _PII_KEYS:
            extra[key] = "[REDACTED]"

    if (tid := _log_tenant_id.get()) is not None:
        extra.setdefault("tenant_id", tid)
    if (uid := _log_user_id.get()) is not None:
        extra.setdefault("user_id", uid)


def _json_sink(message: Any) -> None:
    """Production JSON sink with PII-masked message text."""
    record = message.record
    output: dict[str, Any] = {
        "ts": record["time"].isoformat(),
        "level": record["level"].name,
        "msg": _mask_string(record["message"]),
        **record["extra"],
    }
    print(json.dumps(output, default=str), file=sys.stdout, flush=True)


def configure_logging(app_env: str = "development") -> None:
    """Set up Loguru. Production: JSON to stdout with PII masking. Dev: colored human-readable."""
    logger.remove()
    logger.configure(patcher=_pii_patcher)

    if app_env == "production":
        logger.add(_json_sink, level="INFO")
    else:
        logger.add(
            sys.stdout,
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
            level="DEBUG",
            colorize=True,
        )
