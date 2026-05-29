import sys
from loguru import logger


def configure_logging(app_env: str = "development") -> None:
    """Set up loguru. In production: JSON to stdout. In dev: colored human-readable."""
    logger.remove()
    if app_env == "production":
        logger.add(sys.stdout, format="{message}", serialize=True, level="INFO")
    else:
        logger.add(
            sys.stdout,
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
            level="DEBUG",
            colorize=True,
        )
