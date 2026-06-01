import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.data.models import Role, Tenant, User
from finacialsim_saas.services.audit_service import AuditService


async def _seed_tenant_user(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    tenant = Tenant(name="Acme", slug=f"acme-{uuid.uuid4().hex[:6]}")
    session.add(tenant)
    await session.flush()
    user = User(
        tenant_id=tenant.id,
        email=f"u-{uuid.uuid4().hex[:6]}@test.com",
        name="Test",
        password_hash="x",
        role=Role.admin,
    )
    session.add(user)
    await session.flush()
    return tenant.id, user.id


async def test_log_and_list(session: AsyncSession):
    tenant_id, user_id = await _seed_tenant_user(session)
    ctx = RequestContext(user_id=user_id, tenant_id=tenant_id, role=Role.admin, iat=0.0)
    svc = AuditService(session)

    await svc.log("create", "client", uuid.uuid4(), {"before": None, "after": {"nome": "Test"}}, ctx)
    await session.commit()

    items, next_cursor = await svc.list(
        tenant_id=tenant_id,
        caller_role=Role.admin,
        caller_user_id=user_id,
    )
    assert len(items) == 1
    assert items[0].acao == "create"
    assert items[0].entidade == "client"
    assert next_cursor is None


async def test_list_user_sees_only_own(session: AsyncSession):
    tenant_id, user_id = await _seed_tenant_user(session)
    other_id = uuid.uuid4()
    ctx_self = RequestContext(user_id=user_id, tenant_id=tenant_id, role=Role.user, iat=0.0)
    ctx_other = RequestContext(user_id=other_id, tenant_id=tenant_id, role=Role.admin, iat=0.0)
    svc = AuditService(session)

    await svc.log("create", "simulation", uuid.uuid4(), None, ctx_self)
    await svc.log("create", "vehicle", uuid.uuid4(), None, ctx_other)
    await session.commit()

    items, _ = await svc.list(
        tenant_id=tenant_id,
        caller_role=Role.user,
        caller_user_id=user_id,
    )
    assert all(str(i.usuario_id) == str(user_id) for i in items)


async def test_cursor_pagination(session: AsyncSession):
    tenant_id, user_id = await _seed_tenant_user(session)
    ctx = RequestContext(user_id=user_id, tenant_id=tenant_id, role=Role.admin, iat=0.0)
    svc = AuditService(session)

    for i in range(25):
        await svc.log("create", "vehicle", uuid.uuid4(), None, ctx)
    await session.commit()

    page1, cursor = await svc.list(tenant_id=tenant_id, caller_role=Role.admin, caller_user_id=user_id)
    assert len(page1) == 20
    assert cursor is not None

    page2, cursor2 = await svc.list(
        tenant_id=tenant_id,
        caller_role=Role.admin,
        caller_user_id=user_id,
        cursor=cursor,
    )
    assert len(page2) == 5
    assert cursor2 is None


async def test_cross_tenant_isolation(session: AsyncSession):
    tenant_a, user_a = await _seed_tenant_user(session)
    tenant_b, user_b = await _seed_tenant_user(session)
    ctx_a = RequestContext(user_id=user_a, tenant_id=tenant_a, role=Role.admin, iat=0.0)
    ctx_b = RequestContext(user_id=user_b, tenant_id=tenant_b, role=Role.admin, iat=0.0)
    svc = AuditService(session)

    await svc.log("create", "client", uuid.uuid4(), None, ctx_a)
    await svc.log("create", "client", uuid.uuid4(), None, ctx_b)
    await session.commit()

    items_a, _ = await svc.list(tenant_id=tenant_a, caller_role=Role.admin, caller_user_id=user_a)
    assert all(str(i.tenant_id) == str(tenant_a) for i in items_a)
