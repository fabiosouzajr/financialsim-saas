import pytest
from sqlalchemy import text

from finacialsim_saas.data.database import check_db


@pytest.mark.asyncio
async def test_db_ping(engine):
    result = await check_db(engine)
    assert result is True


@pytest.mark.asyncio
async def test_session_can_execute_query(session):
    result = await session.execute(text("SELECT 42 AS answer"))
    row = result.fetchone()
    assert row is not None
    assert row.answer == 42
