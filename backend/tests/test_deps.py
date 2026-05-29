import uuid
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
import jwt


def _token(user_id: str, tenant_id: str, role: str, secret: str = "test-secret") -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {"sub": user_id, "tenant_id": tenant_id, "role": role,
         "iat": now, "exp": now + timedelta(minutes=15)},
        secret, algorithm="HS256",
    )


@pytest.mark.asyncio
async def test_parse_bearer_valid_token(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    from finacialsim_saas.auth.deps import _parse_bearer
    uid, tid = str(uuid.uuid4()), str(uuid.uuid4())
    req = MagicMock()
    req.headers = {"Authorization": f"Bearer {_token(uid, tid, 'admin')}"}
    ctx = await _parse_bearer(req)
    assert ctx is not None and str(ctx.user_id) == uid


@pytest.mark.asyncio
async def test_parse_bearer_no_header_returns_none(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    from finacialsim_saas.auth.deps import _parse_bearer
    req = MagicMock()
    req.headers = {}
    assert await _parse_bearer(req) is None


@pytest.mark.asyncio
async def test_require_role_wrong_role_raises():
    from finacialsim_saas.auth.deps import RequestContext, require_role
    from finacialsim_saas.data.models import Role
    from finacialsim_saas.errors import TenantAccessError
    ctx = RequestContext(user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), role=Role.user, iat=0.0)
    with pytest.raises(TenantAccessError):
        await require_role("admin")(ctx)


@pytest.mark.asyncio
async def test_require_role_correct_role_passes():
    from finacialsim_saas.auth.deps import RequestContext, require_role
    from finacialsim_saas.data.models import Role
    ctx = RequestContext(user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), role=Role.admin, iat=0.0)
    result = await require_role("admin")(ctx)
    assert result.role == Role.admin
