import pytest
from arq import Worker
from arq.connections import RedisSettings, create_pool

from finacialsim_saas.workers.tasks import ping


@pytest.mark.asyncio
async def test_ping_job_enqueue_and_process(redis_url):
    """
    Integration test: enqueue ping via ARQ, run the worker in burst mode
    (processes all pending jobs then exits), verify the result is 'pong'.
    Uses testcontainers Redis — no external Redis required.
    """
    settings = RedisSettings.from_dsn(redis_url)

    pool = await create_pool(settings)
    job = await pool.enqueue_job("ping")
    await pool.aclose()

    worker = Worker(
        functions=[ping],
        redis_settings=settings,
        burst=True,
        max_jobs=1,
    )
    await worker.main()
    await worker.close()

    pool = await create_pool(settings)
    result = await job.result(timeout=5)
    await pool.aclose()

    assert result == "pong"
