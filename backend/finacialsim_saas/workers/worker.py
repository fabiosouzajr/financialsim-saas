from arq.connections import RedisSettings

from finacialsim_saas.settings import get_settings
from finacialsim_saas.workers.tasks import ping


def get_redis_settings() -> RedisSettings:
    s = get_settings()
    return RedisSettings.from_dsn(str(s.redis_url))


class WorkerSettings:
    """ARQ reads this class to configure the worker process."""

    functions = [ping]
    redis_settings = get_redis_settings()
    max_jobs = 10
    job_timeout = 30
