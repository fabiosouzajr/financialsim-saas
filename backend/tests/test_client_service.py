import pytest
import pytest_asyncio
import uuid
from finacialsim_saas.services.client_service import ClientService
from finacialsim_saas.schemas.clients import ClientIn
from finacialsim_saas.errors import ValidationError, ConflictError, NotFoundError, TenantAccessError
from finacialsim_saas.data.models import Role, User, Tenant
from finacialsim_saas.auth.deps import RequestContext


@pytest_asyncio.fixture
async def ctx_and_session(session):
    tenant = Tenant(name="T1", slug=f"t1-{uuid.uuid4().hex[:6]}")
    session.add(tenant)
    await session.flush()
    user = User(
        tenant_id=tenant.id, email=f"u-{uuid.uuid4().hex[:6]}@t.com",
        name="U", password_hash="x", role=Role.user
    )
    session.add(user)
    await session.flush()
    ctx = RequestContext(tenant_id=tenant.id, user_id=user.id, role=Role.user, iat=0.0)
    yield ctx, session


@pytest.mark.asyncio
async def test_create_pf_client_valid_cpf(ctx_and_session):
    ctx, session = ctx_and_session
    body = ClientIn(nome="João Silva", cpf_cnpj="529.982.247-25", tipo="pf")
    svc = ClientService(session)
    out = await svc.create(body, ctx)
    assert out.nome == "João Silva"
    assert out.tipo == "pf"
    assert out.tenant_id == ctx.tenant_id


@pytest.mark.asyncio
async def test_create_pf_client_invalid_cpf_raises(ctx_and_session):
    ctx, session = ctx_and_session
    body = ClientIn(nome="X", cpf_cnpj="111.111.111-11", tipo="pf")
    svc = ClientService(session)
    with pytest.raises(ValidationError, match="CPF"):
        await svc.create(body, ctx)


@pytest.mark.asyncio
async def test_create_pj_client_valid_cnpj(ctx_and_session):
    ctx, session = ctx_and_session
    body = ClientIn(nome="Empresa X", cpf_cnpj="11.222.333/0001-81", tipo="pj")
    svc = ClientService(session)
    out = await svc.create(body, ctx)
    assert out.tipo == "pj"


@pytest.mark.asyncio
async def test_duplicate_cpf_cnpj_raises_conflict(ctx_and_session):
    ctx, session = ctx_and_session
    body = ClientIn(nome="A", cpf_cnpj="529.982.247-25", tipo="pf")
    svc = ClientService(session)
    await svc.create(body, ctx)
    with pytest.raises(ConflictError):
        await svc.create(ClientIn(nome="B", cpf_cnpj="529.982.247-25", tipo="pf"), ctx)


@pytest.mark.asyncio
async def test_cross_tenant_get_raises_403(ctx_and_session, session):
    ctx, _ = ctx_and_session
    other_tenant = Tenant(name="T2", slug=f"t2-{uuid.uuid4().hex[:6]}")
    session.add(other_tenant)
    await session.flush()
    other_user = User(
        tenant_id=other_tenant.id, email=f"o-{uuid.uuid4().hex[:6]}@t.com",
        name="O", password_hash="x", role=Role.user
    )
    session.add(other_user)
    await session.flush()

    body = ClientIn(nome="A", cpf_cnpj="529.982.247-25", tipo="pf")
    svc_a = ClientService(session)
    created = await svc_a.create(body, ctx)

    other_ctx = RequestContext(tenant_id=other_tenant.id, user_id=other_user.id, role=Role.user, iat=0.0)
    svc_b = ClientService(session)
    with pytest.raises(TenantAccessError):
        await svc_b.get(created.id, other_ctx)


@pytest.mark.asyncio
async def test_deactivate_client(ctx_and_session):
    ctx, session = ctx_and_session
    body = ClientIn(nome="A", cpf_cnpj="529.982.247-25", tipo="pf")
    svc = ClientService(session)
    created = await svc.create(body, ctx)
    out = await svc.deactivate(created.id, ctx)
    assert out.is_active is False
