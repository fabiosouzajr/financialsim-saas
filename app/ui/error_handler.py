"""Shared UI error handler for event callbacks."""

from __future__ import annotations

from loguru import logger
from nicegui import ui


def handle_unexpected(exc: Exception, context: str) -> None:
    logger.opt(exception=exc).error(f"Unexpected error [{context}]")
    ui.notify("Erro inesperado. Tente novamente.", type="negative")
