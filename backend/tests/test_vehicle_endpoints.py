import pytest
import uuid
from finacialsim_saas.data.models import Tenant, User, Role
from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.settings import get_settings


async def _seed(session):
    tenant = Tenant(name="VT", slug=f"vt-{uuid.uuid4().hex[:6]}")
    session.add(tenant)
    await session.flush()
    svc = AuthService(session, get_settings())
    email = f"vt-{uuid.uuid4().hex[:6]}@t.com"
    user = await svc.register_user(
        tenant_id=tenant.id, email=email, name="U",
        password="pass123!", role=Role.manager
    )
    await session.flush()
    access_token, _ = await svc.issue_tokens(user)
    await session.commit()
    return tenant, access_token


_VEHICLE_BODY = {
    "fonte": "fipe_parallelum",
    "tipo": "carro",
    "marca": "Toyota",
    "modelo": "Corolla",
    "ano_modelo": 2023,
    "codigo_fipe": "005004-4",
    "valor_fipe": "120000.00",
    "mes_referencia_fipe": "maio/2026",
    "snapshot_json": {"marca_id": "21", "modelo_id": "4591", "year_id": "2023-1"},
}


@pytest.mark.asyncio
async def test_create_and_list_vehicles(client, session):
    _, token = await _seed(session)
    headers = {"Authorization": f"Bearer {token}"}

    resp = await client.post("/api/v1/vehicles", json=_VEHICLE_BODY, headers=headers)
    assert resp.status_code == 201
    assert resp.json()["status"] == "ativo"

    list_resp = await client.get("/api/v1/vehicles", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()["items"]) == 1


@pytest.mark.asyncio
async def test_set_vehicle_status(client, session):
    _, token = await _seed(session)
    headers = {"Authorization": f"Bearer {token}"}

    v = (await client.post("/api/v1/vehicles", json=_VEHICLE_BODY, headers=headers)).json()
    resp = await client.post(
        f"/api/v1/vehicles/{v['id']}/status",
        json={"status": "reservado"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "reservado"


@pytest.mark.asyncio
async def test_invalid_status_transition_returns_422(client, session):
    _, token = await _seed(session)
    headers = {"Authorization": f"Bearer {token}"}

    v = (await client.post("/api/v1/vehicles", json=_VEHICLE_BODY, headers=headers)).json()
    await client.post(f"/api/v1/vehicles/{v['id']}/status", json={"status": "vendido"}, headers=headers)
    resp = await client.post(
        f"/api/v1/vehicles/{v['id']}/status",
        json={"status": "ativo"},
        headers=headers,
    )
    assert resp.status_code == 422
