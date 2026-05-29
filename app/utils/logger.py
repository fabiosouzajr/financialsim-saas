"""Centralized loguru configuration for FinacialSim."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from loguru import logger


def setup_logging(log_dir: Path) -> None:
    """Configure loguru with file rotation, gzip, and console output."""
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.remove()  # drop default
    logger.add(
        sys.stderr,
        level=os.environ.get("FINACIALSIM_LOG_LEVEL", "INFO"),
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | "
               "<cyan>{module}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    )
    logger.add(
        log_dir / "finacialsim_{time:YYYY-MM-DD}.log",
        rotation="00:00",
        retention="30 days",
        compression="gz",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {module}:{function}:{line} - {message} {extra}",
        enqueue=True,
    )

    sentry_dsn = os.environ.get("SENTRY_DSN")
    if sentry_dsn:
        try:
            import sentry_sdk
            sentry_sdk.init(dsn=sentry_dsn, traces_sample_rate=0.0)
            logger.info("Sentry initialized")
        except ImportError:
            logger.warning("SENTRY_DSN set but sentry-sdk not installed")