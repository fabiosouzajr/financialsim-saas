import pytest


@pytest.mark.asyncio
async def test_ping_returns_pong():
    """Unit test: the ping function works in isolation."""
    from finacialsim_saas.workers.tasks import ping

    result = await ping({})
    assert result == "pong"
