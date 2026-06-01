import asyncio
import pytest
from sqlalchemy import select


@pytest.mark.asyncio
async def test_all_phase1_models_importable_and_tables_exist(session):
    from finacialsim_saas.data.models import (
        AuditLog, NotificationsOutbox, PasswordResetToken,
        RefreshToken, Tenant, User,
    )
    for Model in (Tenant, User, PasswordResetToken, RefreshToken, AuditLog, NotificationsOutbox):
        result = await session.execute(select(Model))
        result.scalars().all()  # tables exist if this doesn't raise


def test_all_phase2_models_importable_and_tables_exist(engine):
    from finacialsim_saas.data.models import (
        BusinessRule, SimulationCounter, Simulation,
        SimulationFee, SimulationExtra, AmortizationRow,
        ExtraordinaryAmortization, SimulationStatus,
    )
    from sqlalchemy import inspect

    async def _check():
        async with engine.connect() as conn:
            tables = await conn.run_sync(
                lambda c: inspect(c).get_table_names()
            )
        return tables

    tables = asyncio.run(_check())
    for t in ("business_rules", "simulation_counters", "simulations",
              "simulation_fees", "simulation_extras", "amortization_rows",
              "extraordinary_amortizations"):
        assert t in tables


def test_all_phase3_models_importable_and_tables_exist(engine):
    from finacialsim_saas.data.models import Client, Vehicle, FipeCache
    from sqlalchemy import inspect
    import asyncio

    async def _check():
        async with engine.connect() as conn:
            tables = await conn.run_sync(
                lambda sync_conn: inspect(sync_conn).get_table_names()
            )
        return tables

    tables = asyncio.run(_check())
    assert "clients" in tables
    assert "vehicles" in tables
    assert "fipe_cache" in tables


def test_all_phase4_models_importable_and_tables_exist(engine):
    from finacialsim_saas.data.models import IndicatorHistory, ProviderHealth
    from sqlalchemy import inspect
    import asyncio

    async def _check():
        async with engine.connect() as conn:
            tables = await conn.run_sync(
                lambda c: inspect(c).get_table_names()
            )
        return tables

    tables = asyncio.run(_check())
    assert "indicators_history" in tables
    assert "provider_health" in tables
