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


@pytest.mark.asyncio
async def test_all_phase7_models_importable_and_tables_exist(session):
    from finacialsim_saas.data.models import NotificationsOutbox, EmailLog
    from sqlalchemy import text

    result = await session.execute(
        text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
    )
    tables = {row[0] for row in result.fetchall()}
    assert "notifications_outbox" in tables
    assert "email_log" in tables

    result = await session.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='notifications_outbox'"
        )
    )
    columns = {row[0] for row in result.fetchall()}
    for col in ("channel", "template_key", "payload_json", "target_email",
                "scheduled_for", "status", "idempotency_key", "updated_at", "criado_em"):
        assert col in columns, f"Missing column: {col}"
