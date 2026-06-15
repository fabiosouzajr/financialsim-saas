import pytest
import pytest_asyncio
from decimal import Decimal
from uuid import uuid4
from datetime import date

from finacialsim_saas.data.models import Tenant, Role, Client, ClientType, Vehicle, VehicleStatus


@pytest_asyncio.fixture
async def tenant(session):
    t = Tenant(name="Test Co", slug=f"test-{uuid4().hex[:6]}")
    session.add(t)
    await session.flush()
    return t


@pytest_asyncio.fixture
async def user(session, tenant):
    from finacialsim_saas.auth.service import AuthService
    from finacialsim_saas.settings import get_settings
    svc = AuthService(session, get_settings())
    u = await svc.register_user(
        tenant_id=tenant.id, email=f"u-{uuid4().hex[:6]}@test.com",
        password="password123", name="Test User", role=Role.user,
    )
    await session.flush()
    return u


@pytest_asyncio.fixture
async def rules_seeded(session, tenant):
    from finacialsim_saas.cli.main import _seed_business_rules
    await _seed_business_rules(session, tenant.id)
    await session.flush()


@pytest_asyncio.fixture
async def client_and_vehicle(session, tenant, user, rules_seeded):
    cl = Client(
        tenant_id=tenant.id, nome="Test Client", cpf_cnpj="52998224725",
        tipo=ClientType.pf, criado_por=user.id,
    )
    session.add(cl)
    v = Vehicle(
        tenant_id=tenant.id, fonte="fipe_parallelum", tipo="carro",
        marca="Toyota", modelo="Corolla", ano_modelo=2023,
        status=VehicleStatus.ativo, criado_por=user.id,
    )
    session.add(v)
    await session.flush()
    return cl, v


@pytest.mark.asyncio
async def test_get_rules_returns_all_21_keys(session, tenant, rules_seeded):
    from finacialsim_saas.services.rules_service import RulesService
    svc = RulesService(session)
    rules = await svc.get_rules(tenant.id)
    assert "entrada_minima_pct" in rules
    assert "taxa_por_prazo_curva" in rules
    assert "ipva_pct_carro" in rules
    assert "emplacamento_valor_moto" in rules
    assert rules["pix_validade_apos_vencimento_dias"] == 60
    assert len(rules) == 21


@pytest.mark.asyncio
async def test_get_rules_returns_defaults_when_unseeded(session, tenant):
    from finacialsim_saas.services.rules_service import RulesService, _RULE_DEFAULTS
    svc = RulesService(session)
    rules = await svc.get_rules(tenant.id)
    assert set(rules.keys()) == set(_RULE_DEFAULTS.keys())
    assert rules["ipva_pct_carro"] == _RULE_DEFAULTS["ipva_pct_carro"][0]


def _make_preview_payload():
    from finacialsim_saas.schemas.simulations import SimulationPreviewRequest
    return SimulationPreviewRequest(
        valor_veiculo="50000.00",
        valor_entrada="10000.00",
        taxa_mensal="0.0199",
        prazo_meses=24,
        data_liberacao=date(2026, 6, 1),
        primeiro_vencimento=date(2026, 7, 1),
        incluir_iof=False,
    )


@pytest.mark.asyncio
async def test_preview_returns_schedule_rows(session, tenant, rules_seeded):
    from finacialsim_saas.services.simulation_service import SimulationService
    from finacialsim_saas.auth.deps import RequestContext
    from finacialsim_saas.data.models import Role
    ctx = RequestContext(user_id=uuid4(), tenant_id=tenant.id, role=Role.user, iat=0.0)
    svc = SimulationService(session)
    result = await svc.preview(_make_preview_payload(), ctx)
    assert len(result.rows) == 24
    assert result.summary.valor_financiado == Decimal("40000.00")


@pytest.mark.asyncio
async def test_preview_no_iof_iof_total_is_zero(session, tenant, rules_seeded):
    from finacialsim_saas.services.simulation_service import SimulationService
    from finacialsim_saas.auth.deps import RequestContext
    from finacialsim_saas.data.models import Role
    ctx = RequestContext(user_id=uuid4(), tenant_id=tenant.id, role=Role.user, iat=0.0)
    svc = SimulationService(session)
    result = await svc.preview(_make_preview_payload(), ctx)
    assert result.summary.iof_total == Decimal("0.00")


@pytest.mark.asyncio
async def test_preview_total_pago_pelo_cliente_includes_entrada(session, tenant, rules_seeded):
    from finacialsim_saas.services.simulation_service import SimulationService
    from finacialsim_saas.auth.deps import RequestContext
    from finacialsim_saas.data.models import Role
    ctx = RequestContext(user_id=uuid4(), tenant_id=tenant.id, role=Role.user, iat=0.0)
    svc = SimulationService(session)
    result = await svc.preview(_make_preview_payload(), ctx)
    expected = result.summary.total_pago + Decimal("10000.00")
    assert result.summary.total_pago_pelo_cliente == expected


@pytest.mark.asyncio
async def test_create_persists_simulation_and_rows(session, tenant, user, rules_seeded, client_and_vehicle):
    from finacialsim_saas.services.simulation_service import SimulationService
    from finacialsim_saas.auth.deps import RequestContext
    from finacialsim_saas.data.models import Role
    from finacialsim_saas.schemas.simulations import SimulationCreate
    cl, v = client_and_vehicle
    ctx = RequestContext(user_id=user.id, tenant_id=tenant.id, role=Role.user, iat=0.0)
    svc = SimulationService(session)
    payload = SimulationCreate(
        client_id=cl.id,
        vehicle_id=v.id,
        valor_veiculo="50000.00",
        valor_entrada="10000.00",
        taxa_mensal="0.0199",
        prazo_meses=24,
        data_liberacao=date(2026, 6, 1),
        primeiro_vencimento=date(2026, 7, 1),
        incluir_iof=False,
    )
    sim = await svc.create(payload, ctx)
    await session.commit()

    fetched = await svc.get(sim.id, ctx)
    assert fetched.id == sim.id
    assert len(fetched.rows) == 24
    assert fetched.status == "confirmado"
    assert fetched.codigo.startswith("SIM-")


@pytest.mark.asyncio
async def test_preview_and_create_agree_on_valor_financiado(session, tenant, user, rules_seeded, client_and_vehicle):
    from finacialsim_saas.services.simulation_service import SimulationService
    from finacialsim_saas.auth.deps import RequestContext
    from finacialsim_saas.data.models import Role
    from finacialsim_saas.schemas.simulations import SimulationCreate
    cl, v = client_and_vehicle
    ctx = RequestContext(user_id=user.id, tenant_id=tenant.id, role=Role.user, iat=0.0)
    svc = SimulationService(session)

    preview_req = _make_preview_payload()
    preview = await svc.preview(preview_req, ctx)

    create_req = SimulationCreate(
        client_id=cl.id,
        vehicle_id=v.id,
        valor_veiculo=preview_req.valor_veiculo,
        valor_entrada=preview_req.valor_entrada,
        taxa_mensal=preview_req.taxa_mensal,
        prazo_meses=preview_req.prazo_meses,
        data_liberacao=preview_req.data_liberacao,
        primeiro_vencimento=preview_req.primeiro_vencimento,
        incluir_iof=preview_req.incluir_iof,
    )
    sim = await svc.create(create_req, ctx)
    await session.commit()
    fetched = await svc.get(sim.id, ctx)

    assert preview.summary.valor_financiado == fetched.valor_financiado
    assert len(preview.rows) == len(fetched.rows)
    for pr, fr in zip(preview.rows, fetched.rows):
        assert pr.parcela == fr.parcela
        assert pr.saldo_devedor == fr.saldo_devedor


@pytest.mark.asyncio
async def test_create_idempotency_key_returns_same_id(session, tenant, user, rules_seeded, client_and_vehicle):
    from finacialsim_saas.services.simulation_service import SimulationService
    from finacialsim_saas.auth.deps import RequestContext
    from finacialsim_saas.data.models import Role
    from finacialsim_saas.schemas.simulations import SimulationCreate
    cl, v = client_and_vehicle
    ctx = RequestContext(user_id=user.id, tenant_id=tenant.id, role=Role.user, iat=0.0)
    svc = SimulationService(session)
    key = f"idem-{uuid4().hex}"
    payload = SimulationCreate(
        client_id=cl.id,
        vehicle_id=v.id,
        valor_veiculo="50000.00", valor_entrada="10000.00",
        taxa_mensal="0.0199", prazo_meses=24,
        data_liberacao=date(2026, 6, 1), primeiro_vencimento=date(2026, 7, 1),
        incluir_iof=False, idempotency_key=key,
    )
    sim1 = await svc.create(payload, ctx)
    await session.commit()
    sim2 = await svc.create(payload, ctx)
    assert sim1.id == sim2.id


@pytest.mark.asyncio
async def test_create_validates_against_rules(session, tenant, user, rules_seeded, client_and_vehicle):
    from finacialsim_saas.services.simulation_service import SimulationService
    from finacialsim_saas.auth.deps import RequestContext
    from finacialsim_saas.data.models import Role
    from finacialsim_saas.errors import ValidationError
    from finacialsim_saas.schemas.simulations import SimulationCreate
    cl, v = client_and_vehicle
    ctx = RequestContext(user_id=user.id, tenant_id=tenant.id, role=Role.user, iat=0.0)
    svc = SimulationService(session)
    payload = SimulationCreate(
        client_id=cl.id,
        vehicle_id=v.id,
        valor_veiculo="50000.00",
        valor_entrada="1000.00",  # 2% — below 10% minimum
        taxa_mensal="0.0199",
        prazo_meses=24,
        data_liberacao=date(2026, 6, 1),
        primeiro_vencimento=date(2026, 7, 1),
        incluir_iof=False,
    )
    with pytest.raises(ValidationError):
        await svc.create(payload, ctx)


@pytest.mark.asyncio
async def test_cross_tenant_get_raises_404(session, tenant, user, rules_seeded, client_and_vehicle):
    from finacialsim_saas.services.simulation_service import SimulationService
    from finacialsim_saas.auth.deps import RequestContext
    from finacialsim_saas.data.models import Role
    from finacialsim_saas.errors import NotFoundError
    from finacialsim_saas.schemas.simulations import SimulationCreate
    cl, v = client_and_vehicle
    ctx = RequestContext(user_id=user.id, tenant_id=tenant.id, role=Role.user, iat=0.0)
    svc = SimulationService(session)
    payload = SimulationCreate(
        client_id=cl.id,
        vehicle_id=v.id,
        valor_veiculo="50000.00", valor_entrada="10000.00",
        taxa_mensal="0.0199", prazo_meses=24,
        data_liberacao=date(2026, 6, 1), primeiro_vencimento=date(2026, 7, 1),
        incluir_iof=False,
    )
    sim = await svc.create(payload, ctx)
    await session.commit()

    other_tenant = Tenant(name="Other", slug=f"other-{uuid4().hex[:6]}")
    session.add(other_tenant)
    await session.flush()
    other_ctx = RequestContext(
        user_id=uuid4(), tenant_id=other_tenant.id, role=Role.user, iat=0.0
    )
    with pytest.raises(NotFoundError):
        await svc.get(sim.id, other_ctx)


@pytest.mark.asyncio
async def test_clone_creates_rascunho(session, tenant, user, rules_seeded, client_and_vehicle):
    from finacialsim_saas.services.simulation_service import SimulationService
    from finacialsim_saas.auth.deps import RequestContext
    from finacialsim_saas.data.models import Role
    from finacialsim_saas.schemas.simulations import SimulationCreate
    cl, v = client_and_vehicle
    ctx = RequestContext(user_id=user.id, tenant_id=tenant.id, role=Role.user, iat=0.0)
    svc = SimulationService(session)
    payload = SimulationCreate(
        client_id=cl.id,
        vehicle_id=v.id,
        valor_veiculo="50000.00", valor_entrada="10000.00",
        taxa_mensal="0.0199", prazo_meses=24,
        data_liberacao=date(2026, 6, 1), primeiro_vencimento=date(2026, 7, 1),
        incluir_iof=False,
    )
    original = await svc.create(payload, ctx)
    await session.commit()
    cloned = await svc.clone(original.id, ctx)
    await session.commit()

    assert cloned.id != original.id
    assert cloned.status == "rascunho"
    assert cloned.codigo != original.codigo
    assert cloned.valor_veiculo == original.valor_veiculo
