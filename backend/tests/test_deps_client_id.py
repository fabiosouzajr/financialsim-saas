import uuid
import jwt
import pytest


@pytest.mark.asyncio
async def test_parse_bearer_includes_client_id(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    from finacialsim_saas.auth.deps import _parse_bearer
    from finacialsim_saas.settings import get_settings

    cfg = get_settings()
    client_id = uuid.uuid4()
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "tenant_id": str(uuid.uuid4()),
            "role": "customer",
            "iat": 0,
            "exp": 9999999999,
            "client_id": str(client_id),
        },
        cfg.jwt_secret_key,
        algorithm="HS256",
    )

    class _Req:
        headers = {"Authorization": f"Bearer {token}"}

    ctx = await _parse_bearer(_Req())
    assert ctx is not None
    assert ctx.client_id == client_id


@pytest.mark.asyncio
async def test_parse_bearer_no_client_id_for_staff(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    from finacialsim_saas.auth.deps import _parse_bearer
    from finacialsim_saas.settings import get_settings

    cfg = get_settings()
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "tenant_id": str(uuid.uuid4()),
            "role": "admin",
            "iat": 0,
            "exp": 9999999999,
        },
        cfg.jwt_secret_key,
        algorithm="HS256",
    )

    class _Req:
        headers = {"Authorization": f"Bearer {token}"}

    ctx = await _parse_bearer(_Req())
    assert ctx is not None
    assert ctx.client_id is None
