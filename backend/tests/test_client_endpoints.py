import pytest
import uuid
from finacialsim_saas.data.models import Tenant, Role
from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.settings import get_settings


async def _seed(session):
    tenant = Tenant(name="CT", slug=f"ct-{uuid.uuid4().hex[:6]}")
    session.add(tenant)
    await session.flush()
    svc = AuthService(session, get_settings())
    email = f"ct-{uuid.uuid4().hex[:6]}@t.com"
    user = await svc.register_user(
        tenant_id=tenant.id, email=email, name="U",
        password="pass123!", role=Role.manager
    )
    await session.flush()
    access_token, _ = await svc.issue_tokens(user)
    await session.commit()
    return tenant, user, access_token


@pytest.mark.asyncio
async def test_create_and_get_client(client, session):
    tenant, _user, token = await _seed(session)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        "/api/v1/clients",
        json={"nome": "João Silva", "cpf_cnpj": "529.982.247-25", "tipo": "pf"},
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["nome"] == "João Silva"

    resp2 = await client.get(f"/api/v1/clients/{data['id']}", headers=headers)
    assert resp2.status_code == 200
    assert resp2.json()["id"] == data["id"]


@pytest.mark.asyncio
async def test_create_client_invalid_cpf_returns_422(client, session):
    tenant, _user, token = await _seed(session)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post(
        "/api/v1/clients",
        json={"nome": "X", "cpf_cnpj": "111.111.111-11", "tipo": "pf"},
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_deactivate_client(client, session):
    tenant, _user, token = await _seed(session)
    headers = {"Authorization": f"Bearer {token}"}

    create_resp = await client.post(
        "/api/v1/clients",
        json={"nome": "João", "cpf_cnpj": "529.982.247-25", "tipo": "pf"},
        headers=headers,
    )
    cid = create_resp.json()["id"]
    deact = await client.post(f"/api/v1/clients/{cid}/deactivate", headers=headers)
    assert deact.status_code == 200
    assert deact.json()["is_active"] is False


@pytest.mark.asyncio
async def test_cross_tenant_client_returns_403(client, session):
    t1, _, tok1 = await _seed(session)
    t2, _, tok2 = await _seed(session)
    h1 = {"Authorization": f"Bearer {tok1}"}
    h2 = {"Authorization": f"Bearer {tok2}"}

    c_resp = await client.post(
        "/api/v1/clients",
        json={"nome": "T1 Client", "cpf_cnpj": "529.982.247-25", "tipo": "pf"},
        headers=h1,
    )
    cid = c_resp.json()["id"]
    resp = await client.get(f"/api/v1/clients/{cid}", headers=h2)
    assert resp.status_code == 403
