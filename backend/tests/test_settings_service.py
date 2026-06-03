import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from finacialsim_saas.data.database import build_session_factory
from finacialsim_saas.services.settings_service import SettingsService


@pytest_asyncio.fixture(autouse=True)
async def clean_settings(engine: AsyncEngine):
    """Truncate system_settings before each test to ensure isolation."""
    factory = build_session_factory(engine)
    async with factory() as session:
        await session.execute(text("DELETE FROM system_settings"))
        await session.commit()
    yield


@pytest.mark.asyncio
async def test_get_all_returns_env_defaults_when_table_empty(engine: AsyncEngine):
    """When system_settings is empty, get_all falls back to env values."""
    factory = build_session_factory(engine)
    async with factory() as session:
        svc = SettingsService(session)
        result = await svc.get_all()
    assert "smtp_host" in result
    assert "smtp_port" in result
    assert "pix_provider" in result
    assert result["pix_provider"][1] == "env"
    assert result["smtp_host"][1] == "env"


@pytest.mark.asyncio
async def test_update_and_get_round_trip(engine: AsyncEngine):
    """update() persists to DB; subsequent get_all returns source=db."""
    factory = build_session_factory(engine)
    async with factory() as session:
        svc = SettingsService(session)
        await svc.update("smtp_host", "mail.example.com", updated_by="admin@test.com")
        await session.commit()

    async with factory() as session:
        svc = SettingsService(session)
        result = await svc.get_all()
    assert result["smtp_host"][0] == "mail.example.com"
    assert result["smtp_host"][1] == "db"


@pytest.mark.asyncio
async def test_update_readonly_key_raises(engine: AsyncEngine):
    factory = build_session_factory(engine)
    async with factory() as session:
        svc = SettingsService(session)
        with pytest.raises(ValueError, match="read-only"):
            await svc.update("pix_provider", "external", updated_by="admin@test.com")
