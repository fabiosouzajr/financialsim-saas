import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
async def client(engine):
    """FastAPI test client wired to the testcontainers Postgres engine."""
    from finacialsim_saas.main import app, app_state

    app_state["engine"] = engine
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_healthz_returns_ok(client):
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok"}


@pytest.mark.asyncio
async def test_version_has_expected_keys(client):
    response = await client.get("/version")
    assert response.status_code == 200
    data = response.json()
    assert "git_sha" in data
    assert "app_env" in data
    assert "build_time" in data


@pytest.mark.asyncio
async def test_app_error_handler_returns_structured_json(client):
    from fastapi import APIRouter

    from finacialsim_saas.errors import NotFoundError
    from finacialsim_saas.main import app

    test_router = APIRouter()

    @test_router.get("/_test/not-found")
    async def raise_not_found():
        raise NotFoundError("thing not found")

    app.include_router(test_router)
    response = await client.get("/_test/not-found")
    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "not_found"
    assert body["message"] == "thing not found"
    assert "request_id" in body
