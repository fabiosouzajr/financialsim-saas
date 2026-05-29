import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.data.models import Role, Tenant
from finacialsim_saas.settings import Settings


def _settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://u:p@localhost/db",  # type: ignore[arg-type]
        jwt_secret_key="unit-test-secret",
    )


@pytest.fixture
async def tenant(session: AsyncSession) -> Tenant:
    t = Tenant(name="SvcTest", slug=f"svc-{uuid.uuid4().hex[:6]}")
    session.add(t)
    await session.flush()
    return t


@pytest.mark.asyncio
async def test_register_and_authenticate(session: AsyncSession, tenant: Tenant):
    from finacialsim_saas.auth.service import AuthService
    svc = AuthService(session, _settings())
    user = await svc.register_user(
        tenant_id=tenant.id, email="a@test.com", password="secret",
        name="A", role=Role.admin,
    )
    await session.flush()
    assert user.id is not None
    assert user.password_hash != "secret"
    authed = await svc.authenticate("a@test.com", "secret")
    assert authed.id == user.id


@pytest.mark.asyncio
async def test_authenticate_wrong_password_raises(session: AsyncSession, tenant: Tenant):
    from finacialsim_saas.auth.service import AuthService
    from finacialsim_saas.errors import AuthError
    svc = AuthService(session, _settings())
    await svc.register_user(
        tenant_id=tenant.id, email="b@test.com", password="correct",
        name="B", role=Role.user,
    )
    await session.flush()
    with pytest.raises(AuthError):
        await svc.authenticate("b@test.com", "wrong")


@pytest.mark.asyncio
async def test_issue_tokens_returns_valid_jwt(session: AsyncSession, tenant: Tenant):
    import jwt as pyjwt
    from finacialsim_saas.auth.service import AuthService
    settings = _settings()
    svc = AuthService(session, settings)
    user = await svc.register_user(
        tenant_id=tenant.id, email="c@test.com", password="pw",
        name="C", role=Role.manager,
    )
    await session.flush()
    access, refresh = await svc.issue_tokens(user)
    payload = pyjwt.decode(access, settings.jwt_secret_key, algorithms=["HS256"])
    assert payload["sub"] == str(user.id)
    assert payload["tenant_id"] == str(tenant.id)
    assert payload["role"] == "manager"
    assert len(refresh) > 20


@pytest.mark.asyncio
async def test_rotate_refresh_issues_new_tokens(session: AsyncSession, tenant: Tenant):
    from finacialsim_saas.auth.service import AuthService
    svc = AuthService(session, _settings())
    user = await svc.register_user(
        tenant_id=tenant.id, email="d@test.com", password="pw", name="D", role=Role.user,
    )
    await session.flush()
    _, refresh1 = await svc.issue_tokens(user)
    await session.flush()
    returned_user, access2, refresh2 = await svc.rotate_refresh(refresh1)
    assert returned_user.id == user.id
    assert access2 != ""
    assert refresh2 != refresh1


@pytest.mark.asyncio
async def test_rotate_refresh_reuse_revokes_family(session: AsyncSession, tenant: Tenant):
    from finacialsim_saas.auth.service import AuthService
    from finacialsim_saas.errors import AuthError
    svc = AuthService(session, _settings())
    user = await svc.register_user(
        tenant_id=tenant.id, email="e@test.com", password="pw", name="E", role=Role.user,
    )
    await session.flush()
    _, refresh1 = await svc.issue_tokens(user)
    await session.flush()
    await svc.rotate_refresh(refresh1)   # first use — ok
    await session.flush()
    with pytest.raises(AuthError):
        await svc.rotate_refresh(refresh1)   # reuse → AuthError + family revoked


@pytest.mark.asyncio
async def test_revoke_all_sets_tokens_revoked_at(session: AsyncSession, tenant: Tenant):
    from finacialsim_saas.auth.service import AuthService
    svc = AuthService(session, _settings())
    user = await svc.register_user(
        tenant_id=tenant.id, email="f@test.com", password="pw", name="F", role=Role.user,
    )
    await session.flush()
    assert user.tokens_revoked_at is None
    await svc.revoke_all(user)
    assert user.tokens_revoked_at is not None
