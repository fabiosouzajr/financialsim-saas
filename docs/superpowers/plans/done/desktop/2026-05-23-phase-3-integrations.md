# Phase 3 — Integrações FIPE + BACEN

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans`.

**Goal:** Implement the `integrations/` layer — `Provider` protocol + `ProviderChain` with fallback, FIPE providers (Parallelum + BrasilAPI), BACEN providers (SGS + BrasilAPI), normalization, and caching.

**Architecture:** Each provider is an `async` class with `@retry` directly on `fetch`. `ProviderChain` tries providers in order, first `Ok` wins. Cache wrappers wrap providers transparently. All providers share a `get_json` HTTP helper.

**Tech Stack:** `httpx.AsyncClient`, `tenacity`, `respx` (test HTTP mocking), plain `@dataclass` schemas.

**Dependencies:** Phase 1 (for `Decimal`) + Phase 2 (for `fipe_cache` table and `IndicatorRepository`).

**Design decisions from grill session:**

- `@retry` with `retry_error_callback` on `fetch` (not on internal helpers); `httpx.HTTPError` re-raised for tenacity, logic errors return `Err` immediately without retry
- Portuguese canonical `tipo` vocabulary (`"carro"`, `"moto"`, `"caminhao"`) at chain level; each provider translates internally via `TIPO_MAP`
- Cache key absent fields use `""` not `None`; upsert (check-then-update) not blind `session.add()`
- `FipeCache` gains `acao` column — new migration required before Task 5
- `VehicleQuote` reconstructed from cache dict on price-query hits; raw list returned for list-query hits
- All list responses normalized to `[{"id": "...", "nome": "..."}]` canonical schema in each provider
- `ManualFipeProvider` available standalone only — not in the default chain
- `CachedBacenProvider` has TTL read-through: skips network when `data_final <= latest.data_referencia` and latest is within TTL
- `asyncio_mode = auto` in pytest.ini; no `@pytest.mark.asyncio` decorators in Phase 3 tests
- Shared `get_json(url, client)` helper in `app/integrations/http.py`; `http_err_callback` co-located

---

## Task 1: pytest.ini + `http.py` + `Result` + `Provider` + `ProviderChain`

**Files:**

- Modify: `pytest.ini`
- Create: `app/integrations/__init__.py` (empty)
- Create: `app/integrations/http.py`
- Create: `app/integrations/base.py`
- Create: `tests/unit/integrations/__init__.py` (empty)
- Create: `tests/unit/integrations/conftest.py`
- Create: `tests/unit/integrations/test_base.py`

- [ ] **Step 1: Update pytest.ini**

```ini
[pytest]
testpaths = tests
addopts = -ra --strict-markers
asyncio_mode = auto
markers =
    slow: tests that take >1s
    integration: integration tests across modules
```

- [ ] **Step 2: Write `app/integrations/http.py`**

```python
"""Shared HTTP helper and tenacity callback for all providers."""

from __future__ import annotations

from typing import Any

import httpx

from app.integrations.base import Err


async def get_json(url: str, client: httpx.AsyncClient | None = None) -> Any:
    owned = client is None
    client = client or httpx.AsyncClient(timeout=8.0, headers={"User-Agent": "FinacialSim/0.1"})
    try:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.json()
    finally:
        if owned:
            await client.aclose()


def http_err_callback(retry_state) -> Err:
    """tenacity retry_error_callback — converts final HTTPError to Err."""
    return Err(f"http_error: {retry_state.outcome.exception()}")
```

- [ ] **Step 3: Write failing test**

`tests/unit/integrations/test_base.py`:

```python
import pytest

from app.integrations.base import Err, Ok, Provider, ProviderChain


class FakeProvider:
    def __init__(self, name: str, should_succeed: bool, payload: str = "ok"):
        self.name = name
        self.should_succeed = should_succeed
        self.payload = payload
        self.calls = 0

    async def fetch(self, query):
        self.calls += 1
        if self.should_succeed:
            return Ok(self.payload)
        return Err(f"{self.name} failed")


async def test_chain_first_provider_wins():
    p1 = FakeProvider("p1", True, "from-p1")
    p2 = FakeProvider("p2", True, "from-p2")
    chain = ProviderChain([p1, p2])
    result = await chain.fetch({"q": 1})
    assert result.is_ok
    assert result.value == "from-p1"
    assert p1.calls == 1
    assert p2.calls == 0


async def test_chain_falls_back_to_second():
    p1 = FakeProvider("p1", False)
    p2 = FakeProvider("p2", True, "from-p2")
    chain = ProviderChain([p1, p2])
    result = await chain.fetch({"q": 1})
    assert result.is_ok
    assert result.value == "from-p2"
    assert p1.calls == 1
    assert p2.calls == 1


async def test_chain_all_fail_returns_err():
    p1 = FakeProvider("p1", False)
    p2 = FakeProvider("p2", False)
    chain = ProviderChain([p1, p2])
    result = await chain.fetch({"q": 1})
    assert result.is_err
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/unit/integrations/test_base.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 5: Write `app/integrations/base.py`**

```python
"""Provider protocol, Result type, and ProviderChain."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, Protocol, TypeVar, runtime_checkable

T = TypeVar("T")


@dataclass(frozen=True)
class Ok(Generic[T]):
    value: T
    is_ok: bool = True
    is_err: bool = False


@dataclass(frozen=True)
class Err:
    error: str
    is_ok: bool = False
    is_err: bool = True


Result = Ok[T] | Err  # type: ignore[valid-type]


@runtime_checkable
class Provider(Protocol):
    name: str

    async def fetch(self, query: dict[str, Any]) -> "Ok[Any] | Err": ...


class ProviderChain:
    """Try each provider in order; first Ok wins."""

    def __init__(self, providers: list[Provider]) -> None:
        if not providers:
            raise ValueError("ProviderChain requires at least one provider")
        self.providers = providers

    async def fetch(self, query: dict[str, Any]) -> "Ok[Any] | Err":
        last_error = "no providers"
        for p in self.providers:
            result = await p.fetch(query)
            if result.is_ok:
                return result
            last_error = result.error  # type: ignore[union-attr]
        return Err(f"all_providers_failed: {last_error}")
```

- [ ] **Step 6: Write `tests/unit/integrations/conftest.py`**

```python
"""Shared test helpers for integration provider tests."""

import httpx


class FailingClient:
    """Raises httpx.ConnectError immediately. Inject to test error paths without respx."""

    async def get(self, url, **kw):
        raise httpx.ConnectError("stubbed failure")

    async def aclose(self):
        pass
```

- [ ] **Step 7: Run tests**

Run: `pytest tests/unit/integrations/test_base.py -v`
Expected: 3 tests PASS.

- [ ] **Step 8: Commit**

```bash
git add pytest.ini app/integrations/ tests/unit/integrations/
git commit -m "feat(integrations): Provider protocol + Result + ProviderChain + http helper"
```

---

## Task 2: FIPE `VehicleQuote` schema + Parallelum provider

**Files:**

- Create: `app/integrations/fipe/__init__.py` (empty)
- Create: `app/integrations/fipe/schema.py`
- Create: `app/integrations/fipe/parallelum.py`
- Create: `tests/unit/integrations/fipe/__init__.py` (empty)
- Create: `tests/unit/integrations/fipe/test_parallelum.py`

- [ ] **Step 1: Write failing test**

`tests/unit/integrations/fipe/test_parallelum.py`:

```python
from decimal import Decimal

import httpx
import pytest
import respx

from tests.unit.integrations.conftest import FailingClient
from app.integrations.fipe.parallelum import ParallelumFipeProvider


@respx.mock
async def test_get_brands_for_cars():
    respx.get("https://parallelum.com.br/fipe/api/v2/cars/brands").mock(
        return_value=httpx.Response(200, json=[
            {"code": "1", "name": "Acura"},
            {"code": "2", "name": "Agrale"},
        ])
    )
    p = ParallelumFipeProvider()
    result = await p.fetch({"action": "brands", "tipo": "carro"})
    assert result.is_ok
    brands = result.value
    assert len(brands) == 2
    assert brands[0] == {"id": "1", "nome": "Acura"}


@respx.mock
async def test_get_price_parses_to_vehicle_quote():
    respx.get("https://parallelum.com.br/fipe/api/v2/cars/brands/21/models/1234/years/2024-1").mock(
        return_value=httpx.Response(200, json={
            "price": "R$ 45.230,00",
            "brand": "Fiat",
            "model": "Mobi 1.0",
            "modelYear": 2024,
            "fuel": "Gasolina",
            "codeFipe": "001234-5",
            "referenceMonth": "maio de 2026",
        })
    )
    p = ParallelumFipeProvider()
    result = await p.fetch({
        "action": "price", "tipo": "carro",
        "brand_id": "21", "model_id": "1234", "year_id": "2024-1",
    })
    assert result.is_ok
    quote = result.value
    assert quote.valor == Decimal("45230.00")
    assert quote.marca == "Fiat"
    assert quote.codigo_fipe == "001234-5"
    assert quote.fonte == "fipe_parallelum"


async def test_returns_err_on_connect_error():
    p = ParallelumFipeProvider(client=FailingClient())
    result = await p.fetch({"action": "brands", "tipo": "carro"})
    assert result.is_err
    assert "http_error" in result.error
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/integrations/fipe/ -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Write `schema.py`**

`app/integrations/fipe/schema.py`:

```python
"""FIPE normalized schemas."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal


@dataclass(frozen=True)
class VehicleQuote:
    tipo: Literal["carro", "moto", "caminhao"]
    marca: str
    marca_id: str
    modelo: str
    modelo_id: str
    ano_modelo: int
    combustivel: str
    codigo_fipe: str
    valor: Decimal
    mes_referencia: str
    fonte: str
    raw_payload: dict[str, Any] = field(default_factory=dict)


def parse_brl_price(text: str) -> Decimal:
    """Parse 'R$ 45.230,00' -> Decimal('45230.00')."""
    cleaned = text.replace("R$", "").replace(".", "").replace(",", ".").strip()
    return Decimal(cleaned)
```

- [ ] **Step 4: Write `parallelum.py`**

`app/integrations/fipe/parallelum.py`:

```python
"""FIPE Parallelum primary provider."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.integrations.base import Err, Ok
from app.integrations.fipe.schema import VehicleQuote, parse_brl_price
from app.integrations.http import get_json, http_err_callback


BASE_URL = "https://parallelum.com.br/fipe/api/v2"
TIPO_MAP = {"carro": "cars", "moto": "motorcycles", "caminhao": "trucks"}


class ParallelumFipeProvider:
    name = "fipe_parallelum"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, max=2),
        retry=retry_if_exception_type(httpx.HTTPError),
        retry_error_callback=http_err_callback,
    )
    async def fetch(self, query: dict[str, Any]) -> Ok[Any] | Err:
        action = query.get("action")
        tipo_url = TIPO_MAP.get(query.get("tipo", ""), "cars")
        try:
            if action == "brands":
                data = await get_json(f"{BASE_URL}/{tipo_url}/brands", self._client)
                return Ok([{"id": d["code"], "nome": d["name"]} for d in data])
            if action == "models":
                brand_id = query["brand_id"]
                data = await get_json(
                    f"{BASE_URL}/{tipo_url}/brands/{brand_id}/models", self._client
                )
                models = data.get("models", data)
                return Ok([{"id": str(d["code"]), "nome": d["name"]} for d in models])
            if action == "years":
                brand_id = query["brand_id"]
                model_id = query["model_id"]
                data = await get_json(
                    f"{BASE_URL}/{tipo_url}/brands/{brand_id}/models/{model_id}/years",
                    self._client,
                )
                return Ok([{"id": d["code"], "nome": d["name"]} for d in data])
            if action == "price":
                brand_id = query["brand_id"]
                model_id = query["model_id"]
                year_id = query["year_id"]
                data = await get_json(
                    f"{BASE_URL}/{tipo_url}/brands/{brand_id}/models/{model_id}/years/{year_id}",
                    self._client,
                )
                quote = VehicleQuote(
                    tipo=query.get("tipo", "carro"),  # type: ignore[arg-type]
                    marca=data["brand"],
                    marca_id=str(brand_id),
                    modelo=data["model"],
                    modelo_id=str(model_id),
                    ano_modelo=int(data["modelYear"]),
                    combustivel=data.get("fuel", ""),
                    codigo_fipe=data.get("codeFipe", ""),
                    valor=parse_brl_price(data["price"]),
                    mes_referencia=data.get("referenceMonth", ""),
                    fonte="fipe_parallelum",
                    raw_payload=data,
                )
                return Ok(quote)
            return Err(f"unknown_action: {action}")
        except httpx.HTTPError:
            raise  # tenacity retries this
        except KeyError as e:
            return Err(f"missing_field: {e}")
        except Exception as e:
            return Err(f"unexpected: {e}")
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/unit/integrations/fipe/test_parallelum.py -v`
Expected: 3 tests PASS. Note: `test_returns_err_on_connect_error` triggers 3 tenacity retries (~1.5s total wait) — this is expected.

- [ ] **Step 6: Commit**

```bash
git add app/integrations/fipe/ tests/unit/integrations/fipe/
git commit -m "feat(integrations): FIPE Parallelum provider + normalized schema"
```

---

## Task 3: FIPE BrasilAPI fallback provider

**Files:**

- Create: `app/integrations/fipe/brasilapi.py`
- Create: `tests/unit/integrations/fipe/test_brasilapi.py`

- [ ] **Step 1: Write failing test**

`tests/unit/integrations/fipe/test_brasilapi.py`:

```python
from decimal import Decimal

import httpx
import pytest
import respx

from tests.unit.integrations.conftest import FailingClient
from app.integrations.fipe.brasilapi import BrasilApiFipeProvider


@respx.mock
async def test_brasilapi_get_brands():
    respx.get("https://brasilapi.com.br/api/fipe/marcas/v1/carros").mock(
        return_value=httpx.Response(200, json=[
            {"valor": "1", "nome": "Acura"},
        ])
    )
    p = BrasilApiFipeProvider()
    result = await p.fetch({"action": "brands", "tipo": "carro"})
    assert result.is_ok
    assert result.value[0] == {"id": "1", "nome": "Acura"}


@respx.mock
async def test_brasilapi_get_price():
    respx.get("https://brasilapi.com.br/api/fipe/preco/v1/001234-5").mock(
        return_value=httpx.Response(200, json=[
            {
                "valor": "R$ 45.230,00",
                "marca": "Fiat",
                "modelo": "Mobi 1.0",
                "anoModelo": 2024,
                "combustivel": "Gasolina",
                "codigoFipe": "001234-5",
                "mesReferencia": "maio de 2026",
            }
        ])
    )
    p = BrasilApiFipeProvider()
    result = await p.fetch({
        "action": "price", "tipo": "carro", "codigo_fipe": "001234-5",
    })
    assert result.is_ok
    assert result.value.valor == Decimal("45230.00")
    assert result.value.fonte == "fipe_brasilapi"


async def test_returns_err_on_connect_error():
    p = BrasilApiFipeProvider(client=FailingClient())
    result = await p.fetch({"action": "brands", "tipo": "carro"})
    assert result.is_err
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/integrations/fipe/test_brasilapi.py -v`
Expected: FAIL.

- [ ] **Step 3: Write `brasilapi.py`**

`app/integrations/fipe/brasilapi.py`:

```python
"""FIPE BrasilAPI fallback provider."""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.integrations.base import Err, Ok
from app.integrations.fipe.schema import VehicleQuote, parse_brl_price
from app.integrations.http import get_json, http_err_callback


BASE_URL = "https://brasilapi.com.br/api/fipe"
TIPO_MAP = {"carro": "carros", "moto": "motos", "caminhao": "caminhoes"}


class BrasilApiFipeProvider:
    name = "fipe_brasilapi"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, max=2),
        retry=retry_if_exception_type(httpx.HTTPError),
        retry_error_callback=http_err_callback,
    )
    async def fetch(self, query: dict[str, Any]) -> Ok[Any] | Err:
        action = query.get("action")
        tipo = query.get("tipo", "carro")
        ba_tipo = TIPO_MAP.get(tipo, "carros")
        try:
            if action == "brands":
                data = await get_json(f"{BASE_URL}/marcas/v1/{ba_tipo}", self._client)
                return Ok([{"id": str(d["valor"]), "nome": d["nome"]} for d in data])
            if action == "price":
                codigo = query["codigo_fipe"]
                data = await get_json(f"{BASE_URL}/preco/v1/{codigo}", self._client)
                if not data:
                    return Err("empty_response")
                d = data[0]
                quote = VehicleQuote(
                    tipo=tipo,  # type: ignore[arg-type]
                    marca=d.get("marca", ""),
                    marca_id="",
                    modelo=d.get("modelo", ""),
                    modelo_id="",
                    ano_modelo=int(d.get("anoModelo", 0)),
                    combustivel=d.get("combustivel", ""),
                    codigo_fipe=d.get("codigoFipe", codigo),
                    valor=parse_brl_price(d["valor"]),
                    mes_referencia=d.get("mesReferencia", ""),
                    fonte="fipe_brasilapi",
                    raw_payload=d,
                )
                return Ok(quote)
            return Err(f"unsupported_action_for_brasilapi: {action}")
        except httpx.HTTPError:
            raise  # tenacity retries this
        except KeyError as e:
            return Err(f"missing_field: {e}")
        except Exception as e:
            return Err(f"unexpected: {e}")
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/integrations/fipe/ -v`
Expected: All FIPE tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/integrations/fipe/brasilapi.py tests/unit/integrations/fipe/test_brasilapi.py
git commit -m "feat(integrations): FIPE BrasilAPI fallback provider"
```

---

## Task 4: Migration — add `acao` column to `FipeCache`

**Files:**

- Modify: `app/data/models.py`
- Create: `app/data/migrations/versions/YYYYMMDD_XXXX_add_fipe_cache_acao.py`

- [ ] **Step 1: Update `FipeCache` in `models.py`**

Add `acao` column and update the unique constraint:

```python
class FipeCache(Base):
    __tablename__ = "fipe_cache"
    __table_args__ = (
        UniqueConstraint("tipo", "acao", "marca_id", "modelo_id", "ano_id", name="uq_fipe_cache_query"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    acao: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    marca_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    modelo_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ano_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    payload_json: Mapped[str] = mapped_column(String, nullable=False)
    coletado_em: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, nullable=False)
    ttl_horas: Mapped[int] = mapped_column(Integer, default=720, nullable=False)
```

- [ ] **Step 2: Generate migration**

Run: `alembic revision --autogenerate -m "add fipe_cache acao column"`

Then verify the generated migration contains:

- `op.add_column("fipe_cache", sa.Column("acao", sa.String(40), nullable=False, server_default=""))`
- drop + recreate of `uq_fipe_cache_query` with new column list

If autogenerate misses the constraint change, write it manually:

```python
def upgrade() -> None:
    op.add_column(
        "fipe_cache",
        sa.Column("acao", sa.String(40), nullable=False, server_default=""),
    )
    op.drop_constraint("uq_fipe_cache_query", "fipe_cache", type_="unique")
    op.create_unique_constraint(
        "uq_fipe_cache_query", "fipe_cache",
        ["tipo", "acao", "marca_id", "modelo_id", "ano_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_fipe_cache_query", "fipe_cache", type_="unique")
    op.drop_column("fipe_cache", "acao")
    op.create_unique_constraint(
        "uq_fipe_cache_query", "fipe_cache",
        ["tipo", "marca_id", "modelo_id", "ano_id"],
    )
```

- [ ] **Step 3: Apply migration**

Run: `alembic upgrade head`
Expected: migration applies without errors.

- [ ] **Step 4: Verify existing tests still pass**

Run: `pytest tests/unit/data/ tests/integration/ -v`
Expected: all PASS (unit tests use `Base.metadata.create_all` which picks up the new column automatically).

- [ ] **Step 5: Commit**

```bash
git add app/data/models.py app/data/migrations/versions/
git commit -m "feat(data): add acao column to fipe_cache + update unique constraint"
```

---

## Task 5: FIPE manual provider + FIPE cache layer

**Files:**

- Create: `app/integrations/fipe/manual.py`
- Create: `app/integrations/fipe/cache.py`
- Create: `tests/unit/integrations/fipe/test_manual.py`
- Create: `tests/unit/integrations/fipe/test_cache.py`

- [ ] **Step 1: Write `manual.py`**

`app/integrations/fipe/manual.py`:

```python
"""Manual FIPE provider — constructs a VehicleQuote from operator-supplied input."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from app.integrations.base import Err, Ok
from app.integrations.fipe.schema import VehicleQuote

_VALID_TIPOS = {"carro", "moto", "caminhao"}


class ManualFipeProvider:
    name = "fipe_manual"

    async def fetch(self, query: dict[str, Any]) -> Ok[Any] | Err:
        if query.get("action") != "price":
            return Err("manual_only_supports_price")
        tipo = query.get("tipo", "carro")
        if tipo not in _VALID_TIPOS:
            return Err(f"invalid_tipo: {tipo!r}. Must be one of {sorted(_VALID_TIPOS)}")
        try:
            quote = VehicleQuote(
                tipo=tipo,  # type: ignore[arg-type]
                marca=query["marca"],
                marca_id=str(query.get("marca_id", "manual")),
                modelo=query["modelo"],
                modelo_id=str(query.get("modelo_id", "manual")),
                ano_modelo=int(query["ano_modelo"]),
                combustivel=query.get("combustivel", ""),
                codigo_fipe=query.get("codigo_fipe", ""),
                valor=Decimal(str(query["valor"])),
                mes_referencia=query.get("mes_referencia", "manual"),
                fonte="manual",
                raw_payload={},
            )
            return Ok(quote)
        except KeyError as e:
            return Err(f"missing_field: {e}")
        except InvalidOperation as e:
            return Err(f"invalid_valor: {e}")
```

- [ ] **Step 2: Write test for manual**

`tests/unit/integrations/fipe/test_manual.py`:

```python
from decimal import Decimal

from app.integrations.fipe.manual import ManualFipeProvider


async def test_manual_constructs_quote():
    p = ManualFipeProvider()
    r = await p.fetch({
        "action": "price", "tipo": "carro",
        "marca": "Custom", "modelo": "X", "ano_modelo": 2023, "valor": "30000.00",
    })
    assert r.is_ok
    assert r.value.valor == Decimal("30000.00")
    assert r.value.fonte == "manual"


async def test_manual_missing_field_returns_err():
    p = ManualFipeProvider()
    r = await p.fetch({"action": "price", "tipo": "carro"})
    assert r.is_err


async def test_manual_invalid_tipo_returns_err():
    p = ManualFipeProvider()
    r = await p.fetch({
        "action": "price", "tipo": "trucks",
        "marca": "X", "modelo": "Y", "ano_modelo": 2020, "valor": "10000",
    })
    assert r.is_err
    assert "invalid_tipo" in r.error


async def test_manual_non_price_action_returns_err():
    p = ManualFipeProvider()
    r = await p.fetch({"action": "brands", "tipo": "carro"})
    assert r.is_err
```

- [ ] **Step 3: Write `cache.py`**

`app/integrations/fipe/cache.py`:

```python
"""Cache layer for FIPE providers using the fipe_cache table."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.data.models import FipeCache
from app.integrations.base import Err, Ok, Provider
from app.integrations.fipe.schema import VehicleQuote


class CachedFipeProvider:
    """Wraps any FIPE Provider with read-through cache.

    Price queries: TTL in hours (default 24).
    List queries: TTL in hours (default 720 = 30 days).
    Absent key fields are stored as "" — never None — to avoid SQLite NULL uniqueness quirks.
    """

    def __init__(
        self,
        wrapped: Provider,
        session_factory,
        listas_ttl_horas: int = 720,
        preco_ttl_horas: int = 24,
    ) -> None:
        self.wrapped = wrapped
        self.session_factory = session_factory
        self.listas_ttl = listas_ttl_horas
        self.preco_ttl = preco_ttl_horas
        self.name = f"cached({wrapped.name})"

    def _key(self, query: dict[str, Any]) -> tuple[str, str, str, str, str]:
        """Return (tipo, acao, marca_id, modelo_id, ano_id) with "" for absent fields."""
        tipo = query.get("tipo", "")
        action = query.get("action", "")
        if action == "brands":
            return (tipo, "brands", "", "", "")
        if action == "models":
            return (tipo, "models", str(query.get("brand_id", "")), "", "")
        if action == "years":
            return (
                tipo, "years",
                str(query.get("brand_id", "")),
                str(query.get("model_id", "")),
                "",
            )
        if action == "price":
            return (
                tipo, "price",
                str(query.get("brand_id", query.get("codigo_fipe", ""))),
                str(query.get("model_id", "")),
                str(query.get("year_id", "")),
            )
        return (tipo, action, "", "", "")

    def _ttl(self, query: dict[str, Any]) -> int:
        return self.preco_ttl if query.get("action") == "price" else self.listas_ttl

    def _deserialize(self, acao: str, payload_json: str) -> Any:
        data = json.loads(payload_json)
        if acao == "price" and isinstance(data, dict):
            return VehicleQuote(
                tipo=data["tipo"],  # type: ignore[arg-type]
                marca=data["marca"],
                marca_id=data["marca_id"],
                modelo=data["modelo"],
                modelo_id=data["modelo_id"],
                ano_modelo=data["ano_modelo"],
                combustivel=data["combustivel"],
                codigo_fipe=data["codigo_fipe"],
                valor=Decimal(data["valor"]),
                mes_referencia=data["mes_referencia"],
                fonte=data["fonte"],
                raw_payload=data.get("raw_payload", {}),
            )
        return data

    async def fetch(self, query: dict[str, Any]) -> Ok[Any] | Err:
        tipo, acao, marca_id, modelo_id, ano_id = self._key(query)
        with self.session_factory() as session:
            row = session.query(FipeCache).filter_by(
                tipo=tipo, acao=acao, marca_id=marca_id, modelo_id=modelo_id, ano_id=ano_id,
            ).first()
            if row is not None:
                age = datetime.utcnow() - row.coletado_em
                if age < timedelta(hours=row.ttl_horas):
                    return Ok(self._deserialize(acao, row.payload_json))

        result = await self.wrapped.fetch(query)
        if result.is_ok:
            payload = result.value
            serialized = json.dumps(
                asdict(payload) if hasattr(payload, "__dataclass_fields__") else payload,
                default=str,
            )
            with self.session_factory() as session:
                row = session.query(FipeCache).filter_by(
                    tipo=tipo, acao=acao, marca_id=marca_id, modelo_id=modelo_id, ano_id=ano_id,
                ).first()
                if row is not None:
                    row.payload_json = serialized
                    row.coletado_em = datetime.utcnow()
                    row.ttl_horas = self._ttl(query)
                else:
                    row = FipeCache(
                        tipo=tipo, acao=acao, marca_id=marca_id,
                        modelo_id=modelo_id, ano_id=ano_id,
                        payload_json=serialized, ttl_horas=self._ttl(query),
                    )
                    session.add(row)
                session.commit()
        return result
```

- [ ] **Step 4: Write test for cache**

`tests/unit/integrations/fipe/test_cache.py`:

```python
import tempfile
from decimal import Decimal
from pathlib import Path

from app.data.database import Base, create_engine_for_sqlite, get_session_factory
from app.integrations.base import Ok
from app.integrations.fipe.cache import CachedFipeProvider
from app.integrations.fipe.schema import VehicleQuote


class FakeListProvider:
    name = "fake_list"
    calls = 0

    async def fetch(self, query):
        self.calls += 1
        return Ok([{"id": "1", "nome": "Acura"}])


class FakePriceProvider:
    name = "fake_price"
    calls = 0

    async def fetch(self, query):
        self.calls += 1
        return Ok(VehicleQuote(
            tipo="carro", marca="Fiat", marca_id="21", modelo="Mobi", modelo_id="1234",
            ano_modelo=2024, combustivel="Gasolina", codigo_fipe="001234-5",
            valor=Decimal("45230.00"), mes_referencia="maio de 2026",
            fonte="fake_price",
        ))


import pytest


@pytest.fixture()
def session_factory():
    with tempfile.TemporaryDirectory() as tmp:
        engine = create_engine_for_sqlite(Path(tmp) / "test.db")
        Base.metadata.create_all(engine)
        yield get_session_factory(engine)


async def test_list_cache_hits_after_first_call(session_factory):
    inner = FakeListProvider()
    cached = CachedFipeProvider(inner, session_factory)
    r1 = await cached.fetch({"action": "brands", "tipo": "carro"})
    r2 = await cached.fetch({"action": "brands", "tipo": "carro"})
    assert r1.is_ok and r2.is_ok
    assert r1.value == r2.value
    assert inner.calls == 1


async def test_price_cache_returns_vehicle_quote(session_factory):
    inner = FakePriceProvider()
    cached = CachedFipeProvider(inner, session_factory)
    q = {"action": "price", "tipo": "carro", "brand_id": "21", "model_id": "1234", "year_id": "2024-1"}
    r1 = await cached.fetch(q)
    r2 = await cached.fetch(q)
    assert r1.is_ok and r2.is_ok
    assert isinstance(r2.value, VehicleQuote)
    assert r2.value.valor == Decimal("45230.00")
    assert inner.calls == 1
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/unit/integrations/fipe/ -v`
Expected: All PASS.

- [ ] **Step 6: Commit**

```bash
git add app/integrations/fipe/manual.py app/integrations/fipe/cache.py \
        tests/unit/integrations/fipe/test_manual.py tests/unit/integrations/fipe/test_cache.py
git commit -m "feat(integrations): FIPE manual provider + cache layer (acao key, upsert, VehicleQuote reconstruction)"
```

---

## Task 6: BACEN `IndicatorPoint` schema + SGS provider

**Files:**

- Create: `app/integrations/bacen/__init__.py` (empty)
- Create: `app/integrations/bacen/schema.py`
- Create: `app/integrations/bacen/sgs.py`
- Create: `tests/unit/integrations/bacen/__init__.py` (empty)
- Create: `tests/unit/integrations/bacen/test_sgs.py`

- [ ] **Step 1: Write failing test**

`tests/unit/integrations/bacen/test_sgs.py`:

```python
from datetime import date
from decimal import Decimal

import httpx
import respx

from tests.unit.integrations.conftest import FailingClient
from app.integrations.bacen.sgs import BcbSgsProvider


@respx.mock
async def test_fetch_selic_meta_normalized_to_fraction():
    respx.get("https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados").mock(
        return_value=httpx.Response(200, json=[
            {"data": "23/05/2026", "valor": "10.50"},
        ])
    )
    p = BcbSgsProvider()
    result = await p.fetch({
        "codigo": "SELIC_META",
        "data_inicial": date(2026, 5, 1),
        "data_final": date(2026, 5, 31),
    })
    assert result.is_ok
    points = result.value
    assert len(points) == 1
    assert points[0].valor_fracao == Decimal("0.10500000")
    assert points[0].unidade == "pct_aa"
    assert points[0].fonte == "bcb_sgs"


async def test_unknown_codigo_returns_err():
    p = BcbSgsProvider()
    result = await p.fetch({
        "codigo": "INVALID",
        "data_inicial": date(2026, 5, 1),
        "data_final": date(2026, 5, 31),
    })
    assert result.is_err


async def test_returns_err_on_connect_error():
    p = BcbSgsProvider(client=FailingClient())
    result = await p.fetch({
        "codigo": "SELIC_META",
        "data_inicial": date(2026, 5, 1),
        "data_final": date(2026, 5, 31),
    })
    assert result.is_err
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/integrations/bacen/ -v`
Expected: FAIL.

- [ ] **Step 3: Write `schema.py`**

`app/integrations/bacen/schema.py`:

```python
"""BACEN normalized indicator schema."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal


Unidade = Literal["pct_aa", "pct_am", "pct_ad"]


@dataclass(frozen=True)
class IndicatorPoint:
    codigo: str
    data_referencia: date
    valor_fracao: Decimal
    unidade: Unidade
    fonte: str
```

- [ ] **Step 4: Write `sgs.py`**

`app/integrations/bacen/sgs.py`:

```python
"""BACEN SGS primary provider for SELIC, CDI, IPCA, Tx BACEN veículos."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.integrations.bacen.schema import IndicatorPoint, Unidade
from app.integrations.base import Err, Ok
from app.integrations.http import get_json, http_err_callback


BASE_URL = "https://api.bcb.gov.br/dados/serie"

# (sgs_codigo, unidade)
CODIGOS: dict[str, tuple[int, Unidade]] = {
    "SELIC_META": (432, "pct_aa"),
    "SELIC_DIARIA": (11, "pct_ad"),
    "CDI": (12, "pct_ad"),
    "IPCA": (433, "pct_am"),
    "TX_BACEN_VEIC": (20714, "pct_am"),
}


class BcbSgsProvider:
    name = "bcb_sgs"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, max=2),
        retry=retry_if_exception_type(httpx.HTTPError),
        retry_error_callback=http_err_callback,
    )
    async def fetch(self, query: dict[str, Any]) -> Ok[Any] | Err:
        codigo = query.get("codigo", "")
        if codigo not in CODIGOS:
            return Err(f"unknown_codigo: {codigo}")
        sgs_code, unidade = CODIGOS[codigo]
        di: date = query["data_inicial"]
        df: date = query["data_final"]
        url = (
            f"{BASE_URL}/bcdata.sgs.{sgs_code}/dados"
            f"?formato=json&dataInicial={di.strftime('%d/%m/%Y')}"
            f"&dataFinal={df.strftime('%d/%m/%Y')}"
        )
        try:
            raw = await get_json(url, self._client)
            points: list[IndicatorPoint] = []
            for entry in raw:
                d_parts = entry["data"].split("/")
                ref_date = date(int(d_parts[2]), int(d_parts[1]), int(d_parts[0]))
                pct = Decimal(entry["valor"])
                if pct < 0 or pct > 100:
                    return Err(f"invalid_value_out_of_range: {pct}")
                fracao = (pct / Decimal("100")).quantize(Decimal("0.00000001"))
                points.append(IndicatorPoint(
                    codigo=codigo,
                    data_referencia=ref_date,
                    valor_fracao=fracao,
                    unidade=unidade,
                    fonte="bcb_sgs",
                ))
            return Ok(points)
        except httpx.HTTPError:
            raise  # tenacity retries this
        except (KeyError, ValueError) as e:
            return Err(f"parse_error: {e}")
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/unit/integrations/bacen/ -v`
Expected: 3 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app/integrations/bacen/ tests/unit/integrations/bacen/
git commit -m "feat(integrations): BACEN SGS provider with normalization"
```

---

## Task 7: BACEN BrasilAPI fallback + conversions

**Files:**

- Create: `app/integrations/bacen/brasilapi.py`
- Create: `app/integrations/bacen/conversions.py`
- Create: `tests/unit/integrations/bacen/test_brasilapi.py`
- Create: `tests/unit/integrations/bacen/test_conversions.py`

- [ ] **Step 1: Write `conversions.py`**

`app/integrations/bacen/conversions.py`:

```python
"""Conversions between rate periodicities."""

from __future__ import annotations

from decimal import Decimal


def mensal_para_anual(taxa_mensal: Decimal) -> Decimal:
    f = float(taxa_mensal)
    return Decimal(str((1.0 + f) ** 12 - 1.0)).quantize(Decimal("0.00000001"))


def anual_para_mensal(taxa_anual: Decimal) -> Decimal:
    f = float(taxa_anual)
    return Decimal(str((1.0 + f) ** (1.0 / 12.0) - 1.0)).quantize(Decimal("0.00000001"))


def diaria_252_para_anual(taxa_diaria: Decimal) -> Decimal:
    f = float(taxa_diaria)
    return Decimal(str((1.0 + f) ** 252 - 1.0)).quantize(Decimal("0.00000001"))


def diaria_252_para_mensal(taxa_diaria: Decimal) -> Decimal:
    f = float(taxa_diaria)
    return Decimal(str((1.0 + f) ** 21 - 1.0)).quantize(Decimal("0.00000001"))
```

- [ ] **Step 2: Write `brasilapi.py`**

`app/integrations/bacen/brasilapi.py`:

```python
"""BACEN fallback — BrasilAPI rates endpoint (single latest value)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.integrations.bacen.schema import IndicatorPoint
from app.integrations.base import Err, Ok
from app.integrations.http import get_json, http_err_callback


BASE_URL = "https://brasilapi.com.br/api/taxas/v1"
ALIAS = {"SELIC_META": "Selic", "CDI": "CDI", "IPCA": "IPCA"}


class BrasilApiBacenProvider:
    name = "bacen_brasilapi"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, max=2),
        retry=retry_if_exception_type(httpx.HTTPError),
        retry_error_callback=http_err_callback,
    )
    async def fetch(self, query: dict[str, Any]) -> Ok[Any] | Err:
        codigo = query.get("codigo", "")
        alias = ALIAS.get(codigo)
        if alias is None:
            return Err(f"unsupported_codigo_brasilapi: {codigo}")
        try:
            data = await get_json(f"{BASE_URL}/{alias}", self._client)
            valor_pct = Decimal(str(data["valor"]))
            if valor_pct < 0 or valor_pct > 100:
                return Err(f"invalid_value: {valor_pct}")
            point = IndicatorPoint(
                codigo=codigo,
                data_referencia=date.today(),
                valor_fracao=(valor_pct / Decimal("100")).quantize(Decimal("0.00000001")),
                unidade="pct_aa" if codigo == "SELIC_META" else "pct_am",
                fonte="brasilapi",
            )
            return Ok([point])
        except httpx.HTTPError:
            raise  # tenacity retries this
        except (KeyError, ValueError) as e:
            return Err(f"parse_error: {e}")
```

- [ ] **Step 3: Write tests**

`tests/unit/integrations/bacen/test_conversions.py`:

```python
from decimal import Decimal

from app.integrations.bacen.conversions import anual_para_mensal, mensal_para_anual


def test_mensal_to_anual_roundtrip():
    m = Decimal("0.015")
    a = mensal_para_anual(m)
    back = anual_para_mensal(a)
    assert abs(back - m) < Decimal("0.000001")


def test_one_pct_mensal_approx_12_68_pct_anual():
    a = mensal_para_anual(Decimal("0.01"))
    assert abs(a - Decimal("0.12682503")) < Decimal("0.0001")
```

`tests/unit/integrations/bacen/test_brasilapi.py`:

```python
from decimal import Decimal

import httpx
import respx

from tests.unit.integrations.conftest import FailingClient
from app.integrations.bacen.brasilapi import BrasilApiBacenProvider


@respx.mock
async def test_brasilapi_selic_returns_point():
    respx.get("https://brasilapi.com.br/api/taxas/v1/Selic").mock(
        return_value=httpx.Response(200, json={"nome": "Selic", "valor": 10.5})
    )
    p = BrasilApiBacenProvider()
    r = await p.fetch({"codigo": "SELIC_META"})
    assert r.is_ok
    assert r.value[0].valor_fracao == Decimal("0.10500000")


async def test_returns_err_on_connect_error():
    p = BrasilApiBacenProvider(client=FailingClient())
    r = await p.fetch({"codigo": "SELIC_META"})
    assert r.is_err
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/integrations/bacen/ -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/integrations/bacen/brasilapi.py app/integrations/bacen/conversions.py \
        tests/unit/integrations/bacen/test_brasilapi.py tests/unit/integrations/bacen/test_conversions.py
git commit -m "feat(integrations): BACEN BrasilAPI fallback + conversions"
```

---

## Task 8: BACEN cache with TTL read-through

**Files:**

- Create: `app/integrations/bacen/cached.py`

- Create: `tests/unit/integrations/bacen/test_cached.py`

- [ ] **Step 1: Write `cached.py`**

`app/integrations/bacen/cached.py`:

```python
"""BACEN cache — persists fetched points to indicators_history; read-through with TTL."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from app.data.models import IndicatorHistory
from app.data.repositories import IndicatorRepository
from app.integrations.bacen.schema import IndicatorPoint
from app.integrations.base import Err, Ok, Provider


class CachedBacenProvider:
    """Wraps a BACEN Provider.

    Read-through: skips the network call when
      - query has a data_final, AND
      - the latest cached entry covers data_final (data_final <= latest.data_referencia), AND
      - that entry is within TTL (latest.data_referencia >= today - ttl_horas/24)

    Write-through: on a cache miss, persists all returned IndicatorPoints to indicators_history.
    """

    def __init__(self, wrapped: Provider, session_factory, ttl_horas: int = 24) -> None:
        self.wrapped = wrapped
        self.session_factory = session_factory
        self.ttl_horas = ttl_horas
        self.name = f"cached({wrapped.name})"

    async def fetch(self, query: dict[str, Any]) -> Ok[Any] | Err:
        codigo = query.get("codigo", "")
        data_final: date | None = query.get("data_final")
        data_inicial: date | None = query.get("data_inicial")

        if data_final is not None:
            with self.session_factory() as session:
                repo = IndicatorRepository(session)
                latest = repo.get_latest(codigo)
                if latest is not None:
                    cutoff = date.today() - timedelta(hours=self.ttl_horas / 24)
                    if data_final <= latest.data_referencia and latest.data_referencia >= cutoff:
                        rows = (
                            session.query(IndicatorHistory)
                            .filter(
                                IndicatorHistory.codigo == codigo,
                                IndicatorHistory.data_referencia >= data_inicial,
                                IndicatorHistory.data_referencia <= data_final,
                            )
                            .all()
                        )
                        points = [
                            IndicatorPoint(
                                codigo=r.codigo,
                                data_referencia=r.data_referencia,
                                valor_fracao=r.valor,
                                unidade=r.unidade,  # type: ignore[arg-type]
                                fonte=r.fonte,
                            )
                            for r in rows
                        ]
                        return Ok(points)

        result = await self.wrapped.fetch(query)
        if result.is_ok:
            with self.session_factory() as session:
                repo = IndicatorRepository(session)
                for pt in result.value:
                    repo.upsert(
                        codigo=pt.codigo,
                        data_referencia=pt.data_referencia,
                        valor=pt.valor_fracao,
                        unidade=pt.unidade,
                        fonte=pt.fonte,
                    )
        return result
```

- [ ] **Step 2: Write test**

`tests/unit/integrations/bacen/test_cached.py`:

```python
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.data.database import Base, create_engine_for_sqlite, get_session_factory
from app.data.repositories import IndicatorRepository
from app.integrations.bacen.cached import CachedBacenProvider
from app.integrations.bacen.schema import IndicatorPoint
from app.integrations.base import Ok


class FakeBacen:
    name = "fake"
    calls = 0

    async def fetch(self, query):
        self.calls += 1
        return Ok([
            IndicatorPoint(
                codigo="SELIC_META",
                data_referencia=date.today(),
                valor_fracao=Decimal("0.10500000"),
                unidade="pct_aa",
                fonte="fake",
            )
        ])


@pytest.fixture()
def session_factory():
    with tempfile.TemporaryDirectory() as tmp:
        engine = create_engine_for_sqlite(Path(tmp) / "test.db")
        Base.metadata.create_all(engine)
        yield get_session_factory(engine)


async def test_cached_writes_to_indicators_history(session_factory):
    cached = CachedBacenProvider(FakeBacen(), session_factory)
    r = await cached.fetch({"codigo": "SELIC_META"})
    assert r.is_ok
    with session_factory() as session:
        repo = IndicatorRepository(session)
        latest = repo.get_latest("SELIC_META")
        assert latest is not None
        assert latest.valor == Decimal("0.10500000")


async def test_cached_read_through_skips_network(session_factory):
    inner = FakeBacen()
    cached = CachedBacenProvider(inner, session_factory, ttl_horas=24)
    today = date.today()
    q = {"codigo": "SELIC_META", "data_inicial": today, "data_final": today}
    r1 = await cached.fetch(q)
    r2 = await cached.fetch(q)
    assert r1.is_ok and r2.is_ok
    assert inner.calls == 1  # second call served from indicators_history
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/integrations/bacen/ -v`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add app/integrations/bacen/cached.py tests/unit/integrations/bacen/test_cached.py
git commit -m "feat(integrations): BACEN cache layer (TTL read-through + write-through to indicators_history)"
```

---

## Task 9: Chain composition helpers

**Files:**

- Create: `app/integrations/factory.py`
- Create: `tests/unit/integrations/test_factory.py`

- [ ] **Step 1: Write failing test**

`tests/unit/integrations/test_factory.py`:

```python
import tempfile
from pathlib import Path

import pytest

from app.data.database import Base, create_engine_for_sqlite, get_session_factory
from app.integrations.factory import build_bacen_chain, build_fipe_chain


@pytest.fixture()
def session_factory():
    with tempfile.TemporaryDirectory() as tmp:
        engine = create_engine_for_sqlite(Path(tmp) / "test.db")
        Base.metadata.create_all(engine)
        yield get_session_factory(engine)


def test_build_fipe_chain_has_two_providers(session_factory):
    chain = build_fipe_chain(session_factory)
    assert len(chain.providers) == 2


def test_build_bacen_chain_has_two_providers(session_factory):
    chain = build_bacen_chain(session_factory)
    assert len(chain.providers) == 2
```

- [ ] **Step 2: Write `factory.py`**

`app/integrations/factory.py`:

```python
"""Composition helpers — build default provider chains."""

from __future__ import annotations

from app.integrations.bacen.brasilapi import BrasilApiBacenProvider
from app.integrations.bacen.cached import CachedBacenProvider
from app.integrations.bacen.sgs import BcbSgsProvider
from app.integrations.base import ProviderChain
from app.integrations.fipe.brasilapi import BrasilApiFipeProvider
from app.integrations.fipe.cache import CachedFipeProvider
from app.integrations.fipe.parallelum import ParallelumFipeProvider


def build_fipe_chain(
    session_factory,
    listas_ttl_horas: int = 720,
    preco_ttl_horas: int = 24,
) -> ProviderChain:
    """Parallelum (primary) → BrasilAPI (fallback), both with cache."""
    parallelum = CachedFipeProvider(
        ParallelumFipeProvider(),
        session_factory,
        listas_ttl_horas=listas_ttl_horas,
        preco_ttl_horas=preco_ttl_horas,
    )
    brasilapi = CachedFipeProvider(
        BrasilApiFipeProvider(),
        session_factory,
        listas_ttl_horas=listas_ttl_horas,
        preco_ttl_horas=preco_ttl_horas,
    )
    return ProviderChain([parallelum, brasilapi])


def build_bacen_chain(session_factory, ttl_horas: int = 24) -> ProviderChain:
    """SGS (primary) → BrasilAPI (fallback), both with cache."""
    sgs = CachedBacenProvider(BcbSgsProvider(), session_factory, ttl_horas=ttl_horas)
    brasil = CachedBacenProvider(BrasilApiBacenProvider(), session_factory, ttl_horas=ttl_horas)
    return ProviderChain([sgs, brasil])
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/integrations/test_factory.py -v`
Expected: 2 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add app/integrations/factory.py tests/unit/integrations/test_factory.py
git commit -m "feat(integrations): default chains factory (FIPE + BACEN)"
```

---

## Task 10: Integration smoke tests (real HTTP — marked slow)

**Files:**

- Create: `tests/integration/test_providers_live.py`

- [ ] **Step 1: Write live tests**

`tests/integration/test_providers_live.py`:

```python
"""Smoke tests against real APIs. Disabled by default; run with -m slow."""

from datetime import date

import pytest

from app.integrations.bacen.sgs import BcbSgsProvider
from app.integrations.fipe.parallelum import ParallelumFipeProvider


@pytest.mark.slow
async def test_parallelum_brands_live():
    p = ParallelumFipeProvider()
    r = await p.fetch({"action": "brands", "tipo": "carro"})
    assert r.is_ok
    brands = r.value
    assert len(brands) > 10
    assert "id" in brands[0] and "nome" in brands[0]


@pytest.mark.slow
async def test_sgs_selic_live():
    p = BcbSgsProvider()
    r = await p.fetch({
        "codigo": "SELIC_META",
        "data_inicial": date(2026, 1, 1),
        "data_final": date.today(),
    })
    assert r.is_ok
    assert len(r.value) >= 1
```

- [ ] **Step 2: Verify mock-only tests still pass**

Run: `pytest tests/unit/integrations/ -v`
Expected: all PASS (live tests absent from this path).

- [ ] **Step 3: Optional — run live**

Run: `pytest tests/integration/test_providers_live.py -v -m slow`
Expected: PASS if internet available.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_providers_live.py
git commit -m "test(integrations): live smoke tests for FIPE and BACEN (slow)"
```

---

## Phase 3 — Definition of Done

- [ ] All 10 tasks completed and committed
- [ ] All mock-based tests pass: `pytest tests/unit/integrations/`
- [ ] Live tests work when internet available: `pytest -m slow`
- [ ] FIPE cache hit verified (second call does not increment inner provider counter)
- [ ] FIPE price cache returns `VehicleQuote` on cache hit (not raw dict)
- [ ] BACEN cache read-through skips network on second same-range query
- [ ] `mypy app/integrations/` passes
- [ ] `ruff check app/integrations/` clean
- [ ] `pytest tests/unit/data/ tests/integration/` still pass (no Phase 2 regressions)
