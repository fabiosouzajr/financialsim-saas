import pytest
from uuid import uuid4

from finacialsim_saas.data.models import Role, Tenant, Client, ClientType, Vehicle, VehicleStatus


async def _make_token(client, session, role=Role.user):
    from finacialsim_saas.auth.service import AuthService
    from finacialsim_saas.settings import get_settings

    t = Tenant(name=f"T-{uuid4().hex[:4]}", slug=f"t-{uuid4().hex[:6]}")
    session.add(t)
    await session.flush()

    from finacialsim_saas.cli.main import _seed_business_rules
    await _seed_business_rules(session, t.id)

    svc = AuthService(session, get_settings())
    email = f"ep-{uuid4().hex[:8]}@test.com"
    u = await svc.register_user(
        tenant_id=t.id, email=email, password="pass1234",
        name="Test", role=role,
    )
    await session.flush()

    cl = Client(
        tenant_id=t.id, nome="Test Client", cpf_cnpj="52998224725",
        tipo=ClientType.pf, criado_por=u.id,
    )
    session.add(cl)
    v = Vehicle(
        tenant_id=t.id, fonte="fipe_parallelum", tipo="carro",
        marca="Toyota", modelo="Corolla", ano_modelo=2023,
        status=VehicleStatus.ativo, criado_por=u.id,
    )
    session.add(v)
    await session.flush()

    access_token, _ = await svc.issue_tokens(u)
    await session.commit()
    return access_token, t, u, cl, v


@pytest.mark.asyncio
async def test_get_business_rules(client, session):
    token, _, _, _, _ = await _make_token(client, session)
    resp = await client.get(
        "/api/v1/business-rules",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "entrada_minima_pct" in data
    assert "taxa_por_prazo_curva" in data


@pytest.mark.asyncio
async def test_preview_returns_schedule(client, session):
    token, _, _, _, _ = await _make_token(client, session)
    resp = await client.post(
        "/api/v1/simulations/preview",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "valor_veiculo": "50000.00",
            "valor_entrada": "10000.00",
            "taxa_mensal": "0.0199",
            "prazo_meses": 24,
            "data_liberacao": "2026-06-01",
            "primeiro_vencimento": "2026-07-01",
            "incluir_iof": False,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["rows"]) == 24
    assert "summary" in data


@pytest.mark.asyncio
async def test_create_simulation_returns_201(client, session):
    token, _, _, cl, v = await _make_token(client, session)
    resp = await client.post(
        "/api/v1/simulations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "client_id": str(cl.id),
            "vehicle_id": str(v.id),
            "valor_veiculo": "50000.00",
            "valor_entrada": "10000.00",
            "taxa_mensal": "0.0199",
            "prazo_meses": 24,
            "data_liberacao": "2026-06-01",
            "primeiro_vencimento": "2026-07-01",
            "incluir_iof": False,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["codigo"].startswith("SIM-")
    assert data["status"] == "confirmado"


@pytest.mark.asyncio
async def test_list_simulations_pagination(client, session):
    token, _, _, cl, v = await _make_token(client, session)
    for _ in range(3):
        await client.post(
            "/api/v1/simulations",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "client_id": str(cl.id),
                "vehicle_id": str(v.id),
                "valor_veiculo": "50000.00", "valor_entrada": "10000.00",
                "taxa_mensal": "0.0199", "prazo_meses": 24,
                "data_liberacao": "2026-06-01", "primeiro_vencimento": "2026-07-01",
                "incluir_iof": False,
            },
        )
    resp = await client.get(
        "/api/v1/simulations",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()["items"]) >= 3


@pytest.mark.asyncio
async def test_get_simulation_by_id(client, session):
    token, _, _, cl, v = await _make_token(client, session)
    created = (await client.post(
        "/api/v1/simulations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "client_id": str(cl.id),
            "vehicle_id": str(v.id),
            "valor_veiculo": "50000.00", "valor_entrada": "10000.00",
            "taxa_mensal": "0.0199", "prazo_meses": 24,
            "data_liberacao": "2026-06-01", "primeiro_vencimento": "2026-07-01",
            "incluir_iof": False,
        },
    )).json()
    resp = await client.get(
        f"/api/v1/simulations/{created['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == created["id"]
    assert len(resp.json()["rows"]) == 24


@pytest.mark.asyncio
async def test_cross_tenant_isolation(client, session):
    token_a, tenant_a, _, cl_a, v_a = await _make_token(client, session)
    token_b, _, _, _, _ = await _make_token(client, session)
    sim = (await client.post(
        "/api/v1/simulations",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "client_id": str(cl_a.id),
            "vehicle_id": str(v_a.id),
            "valor_veiculo": "50000.00", "valor_entrada": "10000.00",
            "taxa_mensal": "0.0199", "prazo_meses": 24,
            "data_liberacao": "2026-06-01", "primeiro_vencimento": "2026-07-01",
            "incluir_iof": False,
        },
    )).json()
    resp = await client.get(
        f"/api/v1/simulations/{sim['id']}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_clone_creates_rascunho(client, session):
    token, _, _, cl, v = await _make_token(client, session)
    sim = (await client.post(
        "/api/v1/simulations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "client_id": str(cl.id),
            "vehicle_id": str(v.id),
            "valor_veiculo": "50000.00", "valor_entrada": "10000.00",
            "taxa_mensal": "0.0199", "prazo_meses": 24,
            "data_liberacao": "2026-06-01", "primeiro_vencimento": "2026-07-01",
            "incluir_iof": False,
        },
    )).json()
    resp = await client.post(
        f"/api/v1/simulations/{sim['id']}/clone",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    assert resp.json()["status"] == "rascunho"
    assert resp.json()["id"] != sim["id"]


@pytest.mark.asyncio
async def test_get_simulation_includes_proposal_id_none(client, session):
    """GET /simulations/{id} returns proposal_id=null when no proposal exists."""
    token, _, _, cl, v = await _make_token(client, session)
    created = (await client.post(
        "/api/v1/simulations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "client_id": str(cl.id),
            "vehicle_id": str(v.id),
            "valor_veiculo": "50000.00", "valor_entrada": "10000.00",
            "taxa_mensal": "0.0199", "prazo_meses": 24,
            "data_liberacao": "2026-06-01", "primeiro_vencimento": "2026-07-01",
            "incluir_iof": False,
        },
    )).json()
    r = await client.get(
        f"/api/v1/simulations/{created['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["proposal_id"] is None


@pytest.mark.asyncio
async def test_get_simulation_includes_proposal_id_when_exists(client, session):
    """GET /simulations/{id} returns the proposal UUID when a proposal exists."""
    token, _, _, cl, v = await _make_token(client, session)
    sim = (await client.post(
        "/api/v1/simulations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "client_id": str(cl.id),
            "vehicle_id": str(v.id),
            "valor_veiculo": "50000.00", "valor_entrada": "10000.00",
            "taxa_mensal": "0.0199", "prazo_meses": 24,
            "data_liberacao": "2026-06-01", "primeiro_vencimento": "2026-07-01",
            "incluir_iof": False,
        },
    )).json()
    proposal = (await client.post(
        "/api/v1/proposals",
        headers={"Authorization": f"Bearer {token}"},
        json={"simulation_id": sim["id"]},
    )).json()
    assert proposal.get("id") is not None
    r = await client.get(
        f"/api/v1/simulations/{sim['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json()["proposal_id"] == proposal["id"]


@pytest.mark.asyncio
async def test_archive_simulation(client, session):
    token, _, _, cl, v = await _make_token(client, session)
    sim = (await client.post(
        "/api/v1/simulations",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "client_id": str(cl.id),
            "vehicle_id": str(v.id),
            "valor_veiculo": "50000.00", "valor_entrada": "10000.00",
            "taxa_mensal": "0.0199", "prazo_meses": 24,
            "data_liberacao": "2026-06-01", "primeiro_vencimento": "2026-07-01",
            "incluir_iof": False,
        },
    )).json()
    resp = await client.post(
        f"/api/v1/simulations/{sim['id']}/archive",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "arquivado"
