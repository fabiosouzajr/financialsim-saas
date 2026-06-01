import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.data.database import build_session_factory
from finacialsim_saas.data.models import Role, Tenant
from finacialsim_saas.services.audit_service import AuditService
from finacialsim_saas.settings import get_settings


async def _seed_user_with_logs(
    engine: AsyncEngine, role: Role = Role.admin, log_count: int = 3
) -> tuple[uuid.UUID, str, uuid.UUID]:
    factory = build_session_factory(engine)
    async with factory() as s:
        t = Tenant(name=f"AL-{role.value}", slug=f"al-{uuid.uuid4().hex[:6]}")
        s.add(t)
        await s.flush()
        svc = AuthService(s, get_settings())
        u = await svc.register_user(
            tenant_id=t.id,
            email=f"al-{uuid.uuid4().hex[:6]}@test.com",
            password="pw", name="U", role=role,
        )
        await s.flush()
        access_token, _ = await svc.issue_tokens(u)
        audit = AuditService(s)
        ctx = RequestContext(user_id=u.id, tenant_id=t.id, role=role, iat=0.0)
        for i in range(log_count):
            await audit.log("create", "client", uuid.uuid4(), None, ctx)
        await s.commit()
        return t.id, access_token, u.id


async def test_audit_log_returns_entries(client: AsyncClient, engine: AsyncEngine):
    _, token, _ = await _seed_user_with_logs(engine, Role.admin, 3)
    resp = await client.get(
        "/api/v1/audit-log",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert len(data["items"]) == 3
    assert data["next_cursor"] is None


async def test_audit_log_filter_by_acao(client: AsyncClient, engine: AsyncEngine):
    _, token, _ = await _seed_user_with_logs(engine, Role.admin, 3)
    resp = await client.get(
        "/api/v1/audit-log?acao=create",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert all(i["acao"] == "create" for i in items)


async def test_audit_log_user_role_sees_only_own(client: AsyncClient, engine: AsyncEngine):
    factory = build_session_factory(engine)
    async with factory() as s:
        t = Tenant(name=f"UserScope-{uuid.uuid4().hex[:4]}", slug=f"us-{uuid.uuid4().hex[:6]}")
        s.add(t)
        await s.flush()
        svc = AuthService(s, get_settings())
        u1 = await svc.register_user(
            tenant_id=t.id, email=f"u1-{uuid.uuid4().hex[:6]}@test.com",
            password="pw", name="U1", role=Role.user,
        )
        await s.flush()
        u2 = await svc.register_user(
            tenant_id=t.id, email=f"u2-{uuid.uuid4().hex[:6]}@test.com",
            password="pw", name="U2", role=Role.admin,
        )
        await s.flush()
        access_token1, _ = await svc.issue_tokens(u1)
        audit = AuditService(s)
        ctx1 = RequestContext(user_id=u1.id, tenant_id=t.id, role=Role.user, iat=0.0)
        ctx2 = RequestContext(user_id=u2.id, tenant_id=t.id, role=Role.admin, iat=0.0)
        await audit.log("create", "simulation", uuid.uuid4(), None, ctx1)
        await audit.log("create", "vehicle", uuid.uuid4(), None, ctx2)
        await s.commit()
        u1_id = u1.id

    resp = await client.get(
        "/api/v1/audit-log",
        headers={"Authorization": f"Bearer {access_token1}"},
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert all(i["usuario_id"] == str(u1_id) for i in items)


async def test_audit_log_csv_export(client: AsyncClient, engine: AsyncEngine):
    _, token, _ = await _seed_user_with_logs(engine, Role.admin, 3)
    resp = await client.get(
        "/api/v1/audit-log?format=csv",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert b"acao" in resp.content


async def test_audit_log_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/audit-log")
    assert resp.status_code == 401
