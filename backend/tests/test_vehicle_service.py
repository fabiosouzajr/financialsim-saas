import pytest
import pytest_asyncio
import uuid

from finacialsim_saas.services.vehicle_service import VehicleService
from finacialsim_saas.schemas.vehicles import VehicleIn
from finacialsim_saas.errors import ValidationError, TenantAccessError
from finacialsim_saas.data.models import Role, User, Tenant
from finacialsim_saas.auth.deps import RequestContext


@pytest_asyncio.fixture
async def ctx_and_session(session):
    tenant = Tenant(name="T", slug=f"tv-{uuid.uuid4().hex[:6]}")
    session.add(tenant)
    await session.flush()
    user = User(
        tenant_id=tenant.id, email=f"vu-{uuid.uuid4().hex[:6]}@t.com",
        name="U", password_hash="x", role=Role.user
    )
    session.add(user)
    await session.flush()
    yield RequestContext(tenant_id=tenant.id, user_id=user.id, role=Role.user, iat=0.0), session


def _fipe_body(**kwargs) -> VehicleIn:
    return VehicleIn(
        fonte="fipe_parallelum",
        tipo="carro",
        marca="Toyota",
        modelo="Corolla",
        ano_modelo=2023,
        codigo_fipe="005004-4",
        valor_fipe="120000.00",
        mes_referencia_fipe="maio/2026",
        snapshot_json={"marca_id": "21", "modelo_id": "4591", "year_id": "2023-1"},
        **kwargs,
    )


@pytest.mark.asyncio
async def test_create_vehicle_defaults_to_ativo(ctx_and_session):
    ctx, session = ctx_and_session
    out = await VehicleService(session).create(_fipe_body(), ctx)
    assert out.status == "ativo"
    assert out.tenant_id == ctx.tenant_id


@pytest.mark.asyncio
async def test_set_status_ativo_to_reservado(ctx_and_session):
    ctx, session = ctx_and_session
    svc = VehicleService(session)
    v = await svc.create(_fipe_body(), ctx)
    out = await svc.set_status(v.id, "reservado", ctx)
    assert out.status == "reservado"


@pytest.mark.asyncio
async def test_set_status_vendido_to_ativo_raises(ctx_and_session):
    ctx, session = ctx_and_session
    svc = VehicleService(session)
    v = await svc.create(_fipe_body(), ctx)
    await svc.set_status(v.id, "reservado", ctx)
    await svc.set_status(v.id, "vendido", ctx)
    with pytest.raises(ValidationError, match="Transição"):
        await svc.set_status(v.id, "ativo", ctx)


@pytest.mark.asyncio
async def test_refresh_fipe_manual_vehicle_raises(ctx_and_session):
    ctx, session = ctx_and_session
    body = VehicleIn(
        fonte="manual", tipo="carro", marca="Honda", modelo="Fit", ano_modelo=2020
    )
    svc = VehicleService(session)
    v = await svc.create(body, ctx)
    with pytest.raises(ValidationError, match="manual"):
        await svc.refresh_fipe(v.id, ctx)


@pytest.mark.asyncio
async def test_cross_tenant_access_raises(ctx_and_session, session):
    ctx, _ = ctx_and_session
    other_tenant = Tenant(name="T2", slug=f"tv2-{uuid.uuid4().hex[:6]}")
    session.add(other_tenant)
    await session.flush()
    other_user = User(
        tenant_id=other_tenant.id, email=f"vu2-{uuid.uuid4().hex[:6]}@t.com",
        name="U2", password_hash="x", role=Role.user
    )
    session.add(other_user)
    await session.flush()

    svc_a = VehicleService(session)
    v = await svc_a.create(_fipe_body(), ctx)

    other_ctx = RequestContext(
        tenant_id=other_tenant.id, user_id=other_user.id, role=Role.user, iat=0.0
    )
    with pytest.raises(TenantAccessError):
        await VehicleService(session).get(v.id, other_ctx)
