import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.data.models import BusinessRule, Role, Tenant, User
from finacialsim_saas.services.rules_service import RulesService


async def _seed(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    t = Tenant(name="Test", slug=f"t-{uuid.uuid4().hex[:6]}")
    session.add(t)
    await session.flush()
    u = User(
        tenant_id=t.id, email=f"a-{uuid.uuid4().hex[:6]}@test.com",
        name="Admin", password_hash="x", role=Role.admin,
    )
    session.add(u)
    rule = BusinessRule(
        tenant_id=t.id,
        chave="entrada_minima_pct",
        valor_json="0.20",  # raw JSON string value, NOT wrapped in dict
    )
    session.add(rule)
    await session.flush()
    return t.id, u.id


async def test_update_changes_value_and_writes_audit(session: AsyncSession):
    from finacialsim_saas.data.models import AuditLog
    from sqlalchemy import select

    tenant_id, user_id = await _seed(session)
    ctx = RequestContext(user_id=user_id, tenant_id=tenant_id, role=Role.admin, iat=0.0)

    svc = RulesService(session)
    await svc.update("entrada_minima_pct", "0.30", ctx)
    await session.commit()

    result = await session.execute(
        select(AuditLog).where(AuditLog.tenant_id == tenant_id, AuditLog.acao == "update")
    )
    logs = result.scalars().all()
    assert len(logs) == 1
    assert logs[0].diff_json["before"] == "0.20"
    assert logs[0].diff_json["after"] == "0.30"
    assert logs[0].entidade == "business_rule"


async def test_update_with_motivo_stored_in_diff(session: AsyncSession):
    from finacialsim_saas.data.models import AuditLog
    from sqlalchemy import select

    tenant_id, user_id = await _seed(session)
    ctx = RequestContext(user_id=user_id, tenant_id=tenant_id, role=Role.admin, iat=0.0)

    svc = RulesService(session)
    await svc.update("entrada_minima_pct", "0.25", ctx, motivo="Ajuste comercial")
    await session.commit()

    result = await session.execute(
        select(AuditLog).where(AuditLog.tenant_id == tenant_id)
    )
    log = result.scalar_one()
    assert log.diff_json["motivo"] == "Ajuste comercial"


async def test_update_publishes_redis_event(session: AsyncSession):
    tenant_id, user_id = await _seed(session)
    ctx = RequestContext(user_id=user_id, tenant_id=tenant_id, role=Role.admin, iat=0.0)

    mock_redis = AsyncMock()
    svc = RulesService(session)
    await svc.update("entrada_minima_pct", "0.30", ctx, redis=mock_redis)

    mock_redis.publish.assert_awaited_once_with("rules.invalidated", str(tenant_id))


async def test_update_nonexistent_rule_raises(session: AsyncSession):
    from finacialsim_saas.errors import AppError

    t = Tenant(name="T2", slug=f"t2-{uuid.uuid4().hex[:6]}")
    session.add(t)
    await session.flush()
    u = User(
        tenant_id=t.id, email=f"b-{uuid.uuid4().hex[:6]}@test.com",
        name="B", password_hash="x", role=Role.admin,
    )
    session.add(u)
    await session.flush()
    ctx = RequestContext(user_id=u.id, tenant_id=t.id, role=Role.admin, iat=0.0)

    svc = RulesService(session)
    with pytest.raises(AppError):
        await svc.update("nonexistent_key", "1", ctx)
