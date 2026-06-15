import uuid
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.data.models import Role, Tenant, Client, ClientType, User, PasswordResetToken, NotificationsOutbox
from finacialsim_saas.settings import get_settings
from sqlalchemy import select


@pytest_asyncio.fixture
async def tenant(session: AsyncSession) -> Tenant:
    t = Tenant(name="TestInviteCo", slug=f"test-invite-{uuid.uuid4().hex[:6]}")
    session.add(t)
    await session.commit()
    return t


@pytest_asyncio.fixture
async def admin_user(session: AsyncSession, tenant: Tenant) -> User:
    svc = AuthService(session, get_settings())
    user = await svc.register_user(
        tenant_id=tenant.id, email=f"admin-{uuid.uuid4().hex[:6]}@test.com",
        password="pass", name="Admin", role=Role.admin,
    )
    await session.commit()
    return user


@pytest_asyncio.fixture
async def client_record(session: AsyncSession, tenant: Tenant, admin_user: User) -> Client:
    c = Client(
        tenant_id=tenant.id,
        nome="João Silva",
        cpf_cnpj=f"111.222.333-{uuid.uuid4().int % 100:02d}",
        tipo=ClientType.pf,
        email=f"joao-{uuid.uuid4().hex[:6]}@example.com",
        criado_por=admin_user.id,
    )
    session.add(c)
    await session.commit()
    return c


@pytest.mark.asyncio
async def test_invite_customer_creates_user_and_token(session, tenant, client_record, admin_user):
    ctx = RequestContext(user_id=admin_user.id, tenant_id=tenant.id, role=Role.admin, iat=0.0)
    svc = AuthService(session, get_settings())
    proposal_id = uuid.uuid4()

    user = await svc.invite_customer(client_record.id, ctx, proposal_id=proposal_id)
    await session.commit()

    assert user.role == Role.customer
    assert user.client_id == client_record.id

    token_result = await session.execute(
        select(PasswordResetToken).where(PasswordResetToken.user_id == user.id)
    )
    token = token_result.scalar_one_or_none()
    assert token is not None
    assert token.used_at is None

    outbox_result = await session.execute(
        select(NotificationsOutbox)
        .where(
            NotificationsOutbox.tenant_id == tenant.id,
            NotificationsOutbox.template_key == "portal.customer_invite",
        )
    )
    entry = outbox_result.scalars().first()
    assert entry is not None
    assert entry.payload_json["user_name"] == user.name
    assert entry.payload_json["proposal_id"] == str(proposal_id)


@pytest.mark.asyncio
async def test_invite_customer_idempotent(session, tenant, client_record, admin_user):
    ctx = RequestContext(user_id=admin_user.id, tenant_id=tenant.id, role=Role.admin, iat=0.0)
    svc = AuthService(session, get_settings())

    user1 = await svc.invite_customer(client_record.id, ctx)
    await session.commit()
    user2 = await svc.invite_customer(client_record.id, ctx)
    await session.commit()

    assert user1.id == user2.id


@pytest.mark.asyncio
async def test_re_invite_invalidates_old_token(session, tenant, client_record, admin_user):
    ctx = RequestContext(user_id=admin_user.id, tenant_id=tenant.id, role=Role.admin, iat=0.0)
    svc = AuthService(session, get_settings())

    user = await svc.invite_customer(client_record.id, ctx)
    await session.commit()

    tok1 = await session.scalar(
        select(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
    )
    assert tok1 is not None
    old_token_id = tok1.id

    await svc.re_invite(client_record.id, ctx)
    await session.commit()

    await session.refresh(tok1)
    assert tok1.used_at is not None

    new_tok = await session.scalar(
        select(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
    )
    assert new_tok is not None
    assert new_tok.id != old_token_id


@pytest.mark.asyncio
async def test_customer_can_authenticate(session, tenant, client_record, admin_user):
    ctx = RequestContext(user_id=admin_user.id, tenant_id=tenant.id, role=Role.admin, iat=0.0)
    svc = AuthService(session, get_settings())

    user = await svc.invite_customer(client_record.id, ctx)
    await session.commit()

    user.password_hash = svc._hash_pw("customer-pass")
    await session.commit()

    auth_user = await svc.authenticate(user.email, "customer-pass")
    assert auth_user.id == user.id
    assert auth_user.role == Role.customer
