from loguru import logger


async def ping(ctx: dict) -> str:
    """Health-check job. Enqueue it to verify the worker is alive and Redis is reachable."""
    logger.info("ping job executed")
    return "pong"
