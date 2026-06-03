import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine
from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.data.database import build_session_factory
from finacialsim_saas.data.models import AuditLog, Role, Tenant
from finacialsim_saas.settings import get_settings


@pytest.mark.asyncio
async def test_audit_log_includes_usuario_email(client: AsyncClient, engine: AsyncEngine):
    factory = build_session_factory(engine)
    async with factory() as session:
        t = Tenant(name=f"AuditEmail-{uuid.uuid4().hex[:6]}", slug=f"ae-{uuid.uuid4().hex[:6]}")
        session.add(t)
        await session.flush()
        svc = AuthService(session, get_settings())
        user = await svc.register_user(
            tenant_id=t.id,
            email=f"audit-{uuid.uuid4().hex[:6]}@test.com",
            password="pw",
            name="AuditUser",
            role=Role.admin,
        )
        await session.flush()
        # Create an audit log entry attributed to this user
        session.add(AuditLog(
            tenant_id=t.id,
            usuario_id=user.id,
            acao="update",
            entidade="test",
            entidade_id=uuid.uuid4(),
            diff_json={"x": 1},
        ))
        access_token, _ = await svc.issue_tokens(user)
        await session.commit()
        user_email = user.email

    resp = await client.get(
        "/api/v1/audit-log",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) >= 1
    assert items[0]["usuario_email"] == user_email
