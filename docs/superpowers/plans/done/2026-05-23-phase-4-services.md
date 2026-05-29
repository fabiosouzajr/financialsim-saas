# Phase 4 — Serviços (orquestração)

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans`.

**Goal:** Implement the `services/` layer — orchestration between `core`, `data`, and `integrations`. UI will consume only these services.

**Architecture:** Each service takes a `Session` (or session factory) plus dependencies. Services are stateless modules that compose lower-layer operations. All persistence happens here; the `core` stays pure.

**Tech Stack:** SQLAlchemy `Session`, Pydantic v2 models for service inputs/outputs, bcrypt for PINs.

**Dependencies:** Phases 1, 2, 3 complete.

**Login UX contract:** The UI presents a name picker (`AuthService.list_users()`) then a PIN entry. `login(user_id, pin)` takes the selected user's id — not a username string. First-login PIN change enforcement is deferred to Phase 5 (detect `ultimo_login is None` in UI).

---

## Task 1: `AuditService` and audit decorator

**Files:**
- Create: `app/services/__init__.py` (empty)
- Create: `app/services/audit_service.py`
- Create: `tests/unit/services/__init__.py`
- Create: `tests/unit/services/test_audit_service.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/services/test_audit_service.py`:
```python
import json
import tempfile
from pathlib import Path

import pytest

from app.data.database import Base, create_engine_for_sqlite, get_session_factory
from app.data.models import AuditLog
from app.services.audit_service import AuditService


@pytest.fixture()
def session():
    with tempfile.TemporaryDirectory() as tmp:
        engine = create_engine_for_sqlite(Path(tmp) / "test.db")
        Base.metadata.create_all(engine)
        SessionLocal = get_session_factory(engine)
        with SessionLocal() as s:
            yield s


def test_log_creates_audit_entry(session):
    svc = AuditService(session)
    svc.log(usuario_id=None, acao="login", entidade="users", entidade_id=1,
            diff={"new": "value"})
    rows = session.query(AuditLog).all()
    assert len(rows) == 1
    assert rows[0].acao == "login"
    assert json.loads(rows[0].diff_json) == {"new": "value"}


def test_log_without_diff_stores_none(session):
    svc = AuditService(session)
    svc.log(usuario_id=1, acao="config_alterada")
    rows = session.query(AuditLog).all()
    assert rows[0].diff_json is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/services/test_audit_service.py -v`
Expected: FAIL.

- [ ] **Step 3: Write implementation**

`app/services/audit_service.py`:
```python
"""AuditService - business-event log persisted to audit_log table."""

from __future__ import annotations

import json
import socket
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.data.models import AuditLog


class AuditService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def log(
        self,
        acao: str,
        usuario_id: int | None = None,
        entidade: str | None = None,
        entidade_id: int | None = None,
        diff: dict[str, Any] | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            timestamp=datetime.utcnow(),
            usuario_id=usuario_id,
            acao=acao,
            entidade=entidade,
            entidade_id=entidade_id,
            diff_json=json.dumps(diff) if diff is not None else None,
            ip=None,
            hostname=socket.gethostname(),
        )
        self.session.add(entry)
        self.session.commit()
        return entry
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/services/test_audit_service.py -v`
Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/ tests/unit/services/
git commit -m "feat(services): AuditService"
```

---

## Task 2: `AuthService` — login, lockout, PIN change, user list

**Files:**
- Create: `app/services/auth_service.py`
- Create: `tests/unit/services/test_auth_service.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/services/test_auth_service.py`:
```python
import tempfile
from pathlib import Path

import pytest

from app.data.database import Base, create_engine_for_sqlite, get_session_factory
from app.services.auth_service import AuthError, AuthService, hash_pin


@pytest.fixture()
def session():
    with tempfile.TemporaryDirectory() as tmp:
        engine = create_engine_for_sqlite(Path(tmp) / "test.db")
        Base.metadata.create_all(engine)
        SessionLocal = get_session_factory(engine)
        with SessionLocal() as s:
            yield s


def test_create_user_and_login(session):
    svc = AuthService(session)
    u = svc.create_user(nome="Joao", pin="123456", perfil="vendedor")
    assert u.id is not None
    logged = svc.login(user_id=u.id, pin="123456")
    assert logged.id == u.id


def test_login_wrong_pin_raises(session):
    svc = AuthService(session)
    u = svc.create_user(nome="A", pin="123456", perfil="vendedor")
    with pytest.raises(AuthError):
        svc.login(user_id=u.id, pin="000000")


def test_change_pin_works_with_old_pin(session):
    svc = AuthService(session)
    u = svc.create_user(nome="A", pin="111111", perfil="vendedor")
    svc.change_pin(user_id=u.id, old_pin="111111", new_pin="222222")
    svc.login(user_id=u.id, pin="222222")  # should not raise


def test_list_users_returns_active_only(session):
    svc = AuthService(session)
    svc.create_user(nome="Ativo", pin="123456", perfil="vendedor")
    u2 = svc.create_user(nome="Inativo", pin="123456", perfil="vendedor")
    from app.data.repositories import UserRepository
    UserRepository(session).deactivate(u2.id)
    users = svc.list_users()
    assert len(users) == 1
    assert users[0].nome == "Ativo"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/services/test_auth_service.py -v`
Expected: FAIL.

- [ ] **Step 3: Write implementation**

`app/services/auth_service.py`:
```python
"""AuthService - PIN-based authentication with bcrypt and lockout."""

from __future__ import annotations

from datetime import datetime, timedelta

import bcrypt
from sqlalchemy.orm import Session

from app.data.models import User
from app.data.repositories import UserRepository
from app.services.audit_service import AuditService


class AuthError(Exception):
    """Raised on login failure or PIN-related issues."""


_LOCKOUT_ATTEMPTS = 5
_LOCKOUT_MINUTES = 5

# In-memory failed-attempts tracker (process-local).
# Resets on restart — acceptable for single-PC kiosk threat model.
_failed: dict[int, list[datetime]] = {}


def hash_pin(pin: str) -> str:
    if not (4 <= len(pin) <= 6) or not pin.isdigit():
        raise AuthError("PIN must be 4 to 6 digits")
    return bcrypt.hashpw(pin.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_pin(pin: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pin.encode(), hashed.encode())
    except (ValueError, TypeError):
        return False


def _check_lockout(user_id: int) -> None:
    now = datetime.utcnow()
    recent = [t for t in _failed.get(user_id, []) if t > now - timedelta(minutes=_LOCKOUT_MINUTES)]
    _failed[user_id] = recent
    if len(recent) >= _LOCKOUT_ATTEMPTS:
        raise AuthError(f"Conta bloqueada por {_LOCKOUT_MINUTES} minutos apos falhas consecutivas")


def _record_failure(user_id: int) -> None:
    _failed.setdefault(user_id, []).append(datetime.utcnow())


class AuthService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.audit = AuditService(session)

    def list_users(self) -> list[User]:
        return self.users.list_active()

    def create_user(self, nome: str, pin: str, perfil: str) -> User:
        if perfil not in {"vendedor", "gerente", "admin"}:
            raise AuthError(f"Perfil invalido: {perfil}")
        u = self.users.create(nome=nome, pin_hash=hash_pin(pin), perfil=perfil)
        self.audit.log(usuario_id=u.id, acao="usuario_criado", entidade="users", entidade_id=u.id)
        return u

    def login(self, user_id: int, pin: str) -> User:
        _check_lockout(user_id)
        u = self.users.get(user_id)
        if u is None or not u.ativo:
            _record_failure(user_id)
            raise AuthError("Usuario nao encontrado ou inativo")
        if not verify_pin(pin, u.pin_hash):
            _record_failure(user_id)
            raise AuthError("PIN incorreto")
        u.ultimo_login = datetime.utcnow()
        self.session.commit()
        _failed.pop(user_id, None)
        self.audit.log(usuario_id=u.id, acao="login")
        return u

    def change_pin(self, user_id: int, old_pin: str, new_pin: str) -> None:
        u = self.users.get(user_id)
        if u is None:
            raise AuthError("Usuario nao encontrado")
        if not verify_pin(old_pin, u.pin_hash):
            raise AuthError("PIN atual incorreto")
        u.pin_hash = hash_pin(new_pin)
        self.session.commit()
        self.audit.log(usuario_id=u.id, acao="pin_alterado")
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/services/test_auth_service.py -v`
Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/auth_service.py tests/unit/services/test_auth_service.py
git commit -m "feat(services): AuthService with bcrypt PIN, lockout, and list_users"
```

---

## Task 3: `ClientService` with CPF/CNPJ validation

**Files:**
- Create: `app/services/client_service.py`
- Create: `app/utils/__init__.py` (empty)
- Create: `app/utils/document_validation.py`
- Create: `tests/unit/services/test_client_service.py`
- Create: `tests/unit/utils/__init__.py`
- Create: `tests/unit/utils/test_document_validation.py`

- [ ] **Step 1: Write doc validation tests**

`tests/unit/utils/test_document_validation.py`:
```python
import pytest

from app.utils.document_validation import is_valid_cnpj, is_valid_cpf


def test_known_valid_cpf():
    assert is_valid_cpf("52998224725") is True


def test_known_invalid_cpf():
    assert is_valid_cpf("11111111111") is False
    assert is_valid_cpf("123") is False


def test_known_valid_cnpj():
    assert is_valid_cnpj("11444777000161") is True


def test_known_invalid_cnpj():
    assert is_valid_cnpj("00000000000000") is False
```

- [ ] **Step 2: Implement `document_validation.py`**

`app/utils/document_validation.py`:
```python
"""CPF and CNPJ validation (modulo-11 checks)."""

from __future__ import annotations


def _only_digits(s: str) -> str:
    return "".join(ch for ch in s if ch.isdigit())


def is_valid_cpf(cpf: str) -> bool:
    cpf = _only_digits(cpf)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    digits = [int(c) for c in cpf]
    for j in range(9, 11):
        s = sum(digits[i] * (j + 1 - i) for i in range(j))
        dv = (s * 10) % 11
        if dv == 10:
            dv = 0
        if dv != digits[j]:
            return False
    return True


def is_valid_cnpj(cnpj: str) -> bool:
    cnpj = _only_digits(cnpj)
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False
    digits = [int(c) for c in cnpj]
    weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    weights2 = [6] + weights1
    for j, weights in [(12, weights1), (13, weights2)]:
        s = sum(digits[i] * weights[i] for i in range(j))
        dv = s % 11
        dv = 0 if dv < 2 else 11 - dv
        if dv != digits[j]:
            return False
    return True
```

- [ ] **Step 3: Run doc tests**

Run: `pytest tests/unit/utils/ -v`
Expected: 4 tests PASS.

- [ ] **Step 4: Write client service test**

`tests/unit/services/test_client_service.py`:
```python
import tempfile
from pathlib import Path

import pytest

from app.data.database import Base, create_engine_for_sqlite, get_session_factory
from app.services.auth_service import AuthService
from app.services.client_service import ClientService, ClientServiceError


@pytest.fixture()
def session():
    with tempfile.TemporaryDirectory() as tmp:
        engine = create_engine_for_sqlite(Path(tmp) / "test.db")
        Base.metadata.create_all(engine)
        SessionLocal = get_session_factory(engine)
        with SessionLocal() as s:
            yield s


def test_create_client_with_valid_cpf(session):
    u = AuthService(session).create_user("admin", "123456", "admin")
    svc = ClientService(session)
    c = svc.create_pf(
        nome="Joao Silva", cpf="529.982.247-25",
        criado_por=u.id, telefone="11999999999",
    )
    assert c.cpf_cnpj == "52998224725"


def test_create_client_invalid_cpf_raises(session):
    u = AuthService(session).create_user("admin", "123456", "admin")
    svc = ClientService(session)
    with pytest.raises(ClientServiceError):
        svc.create_pf(nome="X", cpf="00000000000", criado_por=u.id)
```

- [ ] **Step 5: Implement `client_service.py`**

`app/services/client_service.py`:
```python
"""ClientService - validated client CRUD."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.data.models import Client
from app.data.repositories import ClientRepository
from app.services.audit_service import AuditService
from app.utils.document_validation import is_valid_cnpj, is_valid_cpf


class ClientServiceError(Exception):
    pass


def _only_digits(s: str) -> str:
    return "".join(ch for ch in s if ch.isdigit())


class ClientService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = ClientRepository(session)
        self.audit = AuditService(session)

    def create_pf(
        self,
        nome: str,
        cpf: str,
        criado_por: int,
        rg: str | None = None,
        data_nasc: date | None = None,
        profissao: str | None = None,
        renda: Decimal | None = None,
        telefone: str | None = None,
        email: str | None = None,
        endereco_json: str | None = None,
        observacoes: str | None = None,
    ) -> Client:
        cpf_d = _only_digits(cpf)
        if not is_valid_cpf(cpf_d):
            raise ClientServiceError(f"CPF invalido: {cpf}")
        c = self.repo.create(
            nome=nome, cpf_cnpj=cpf_d, tipo="PF", criado_por=criado_por,
            rg=rg, data_nasc=data_nasc, profissao=profissao, renda=renda,
            telefone=telefone, email=email, endereco_json=endereco_json,
            observacoes=observacoes,
        )
        self.audit.log(usuario_id=criado_por, acao="client_created",
                       entidade="clients", entidade_id=c.id)
        return c

    def create_pj(
        self,
        razao_social: str,
        cnpj: str,
        criado_por: int,
        telefone: str | None = None,
        email: str | None = None,
        endereco_json: str | None = None,
        observacoes: str | None = None,
    ) -> Client:
        cnpj_d = _only_digits(cnpj)
        if not is_valid_cnpj(cnpj_d):
            raise ClientServiceError(f"CNPJ invalido: {cnpj}")
        c = self.repo.create(
            nome=razao_social, cpf_cnpj=cnpj_d, tipo="PJ", criado_por=criado_por,
            telefone=telefone, email=email, endereco_json=endereco_json,
            observacoes=observacoes,
        )
        self.audit.log(usuario_id=criado_por, acao="client_created",
                       entidade="clients", entidade_id=c.id)
        return c

    def find(self, query: str) -> list[Client]:
        return self.repo.search(query)
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/unit/services/test_client_service.py tests/unit/utils/ -v`
Expected: All PASS.

- [ ] **Step 7: Commit**

```bash
git add app/services/client_service.py app/utils/ tests/unit/services/test_client_service.py tests/unit/utils/
git commit -m "feat(services): ClientService with CPF/CNPJ validation"
```

---

## Task 4: `SimulationService` — the main service

**Files:**
- Create: `app/services/simulation_service.py`
- Create: `tests/unit/services/test_simulation_service.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/services/test_simulation_service.py`:
```python
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.core.extras import Extra, ExtraModalidade
from app.data.database import Base, create_engine_for_sqlite, get_session_factory
from app.services.auth_service import AuthService
from app.services.simulation_service import (
    SimulationInputDTO,
    SimulationService,
    SimulationServiceError,
)


@pytest.fixture()
def session():
    with tempfile.TemporaryDirectory() as tmp:
        engine = create_engine_for_sqlite(Path(tmp) / "test.db")
        Base.metadata.create_all(engine)
        SessionLocal = get_session_factory(engine)
        with SessionLocal() as s:
            yield s


def _make_vehicle(session):
    from app.data.models import Vehicle
    v = Vehicle(
        fonte="manual", tipo="carro", marca="Fiat", modelo="Mobi",
        ano_modelo=2024, combustivel="Gasolina",
        valor_referencia=Decimal("50000"),
    )
    session.add(v)
    session.commit()
    return v


def test_run_simulation_persists_and_returns(session):
    user = AuthService(session).create_user("vendedor", "123456", "vendedor")
    v = _make_vehicle(session)
    svc = SimulationService(session)
    sim = svc.run_and_save(
        SimulationInputDTO(
            criado_por=user.id,
            cliente_id=None,
            veiculo_id=v.id,
            valor_veiculo=Decimal("50000"),
            valor_entrada=Decimal("10000"),
            prazo_meses=24,
            taxa_mensal=Decimal("0.015"),
            data_liberacao=date(2026, 1, 1),
            data_primeiro_venc=date(2026, 1, 31),
            incluir_iof=True,
            tarifas=[],
            extras=[],
        )
    )
    assert sim.id is not None
    assert sim.codigo.startswith("SIM-")
    assert sim.valor_parcela > Decimal("0")
    assert sim.cet_mes > Decimal("0")
    # IOF was applied
    assert sim.iof_total > Decimal("0")
    # Amortization rows persisted
    from app.data.models import AmortizationRow
    rows = session.query(AmortizationRow).filter_by(simulation_id=sim.id).all()
    assert len(rows) == 24


def test_run_simulation_with_extras_persists_extras_total(session):
    user = AuthService(session).create_user("vendedor", "123456", "vendedor")
    v = _make_vehicle(session)
    svc = SimulationService(session)
    sim = svc.run_and_save(
        SimulationInputDTO(
            criado_por=user.id, cliente_id=None, veiculo_id=v.id,
            valor_veiculo=Decimal("50000"), valor_entrada=Decimal("10000"),
            prazo_meses=24, taxa_mensal=Decimal("0.015"),
            data_liberacao=date(2026, 1, 1), data_primeiro_venc=date(2026, 1, 31),
            incluir_iof=False,
            tarifas=[],
            extras=[
                Extra("ipva", "IPVA", Decimal("1200"), ExtraModalidade.RATEIO_MESES, 12, 1),
            ],
        )
    )
    # 12 first parcelas of 100 each = 1200
    assert sim.extras_total_acumulado == Decimal("1200.00")
    # First amortization row parcela_total includes 100
    from app.data.models import AmortizationRow
    rows = session.query(AmortizationRow).filter_by(simulation_id=sim.id).order_by(AmortizationRow.numero_parcela).all()
    assert rows[0].extras_total == Decimal("100.0000")
    assert rows[12].extras_total == Decimal("0.0000")


def test_validation_error_raises_simulation_service_error(session):
    user = AuthService(session).create_user("vendedor", "123456", "vendedor")
    v = _make_vehicle(session)
    svc = SimulationService(session)
    with pytest.raises(SimulationServiceError) as exc_info:
        svc.run_and_save(
            SimulationInputDTO(
                criado_por=user.id, cliente_id=None, veiculo_id=v.id,
                valor_veiculo=Decimal("50000"),
                valor_entrada=Decimal("100"),   # below 10% minimum
                prazo_meses=24, taxa_mensal=Decimal("0.015"),
                data_liberacao=date(2026, 1, 1), data_primeiro_venc=date(2026, 1, 31),
                incluir_iof=False, tarifas=[], extras=[],
            )
        )
    assert exc_info.value.issues
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/services/test_simulation_service.py -v`
Expected: FAIL.

- [ ] **Step 3: Write implementation**

`app/services/simulation_service.py`:
```python
"""SimulationService - orchestrates calculation + persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.cet import compute_cet
from app.core.extras import Extra, compute_extras_per_parcela
from app.core.iof import IofConfig, compute_financed_amount_with_iof
from app.core.money import quantize_brl
from app.core.validators import (
    ValidationLevel,
    ValidationRules,
    SimulationInput,
    validate_simulation,
)
from app.data.models import (
    AmortizationRow,
    BusinessRule,
    Simulation,
    SimulationExtra,
    SimulationFee,
    User,
)
from app.services.audit_service import AuditService


class SimulationServiceError(Exception):
    def __init__(self, issues: list) -> None:
        self.issues = issues
        super().__init__(str([i.message for i in issues]))


@dataclass
class Tarifa:
    nome: str
    valor: Decimal
    incluir_no_principal: bool = True


@dataclass
class SimulationInputDTO:
    criado_por: int
    cliente_id: int | None
    veiculo_id: int
    valor_veiculo: Decimal
    valor_entrada: Decimal
    prazo_meses: int
    taxa_mensal: Decimal
    data_liberacao: date
    data_primeiro_venc: date
    incluir_iof: bool
    tarifas: list[Tarifa]
    extras: list[Extra]


def _get_decimal_rule(session: Session, chave: str, default: Decimal) -> Decimal:
    row = session.query(BusinessRule).filter_by(chave=chave).first()
    if row is None:
        return default
    return Decimal(row.valor_json)


def _get_int_rule(session: Session, chave: str, default: int) -> int:
    row = session.query(BusinessRule).filter_by(chave=chave).first()
    if row is None:
        return default
    return int(row.valor_json)


def _next_codigo(session: Session, prefix: str) -> str:
    year = date.today().year
    count = session.query(Simulation).filter(Simulation.codigo.like(f"{prefix}-{year}-%")).count()
    return f"{prefix}-{year}-{count + 1:05d}"


class SimulationService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.audit = AuditService(session)

    def run_and_save(self, dto: SimulationInputDTO) -> Simulation:
        # 1. Carencia
        dias_carencia = (dto.data_primeiro_venc - dto.data_liberacao).days

        # 2. Validate against business rules (ERROR-level blocks; WARNING passes)
        rules = ValidationRules(
            entrada_minima_pct=_get_decimal_rule(self.session, "entrada_minima_pct", Decimal("0.10")),
            prazo_minimo_meses=_get_int_rule(self.session, "prazo_minimo_meses", 12),
            prazo_maximo_meses=_get_int_rule(self.session, "prazo_maximo_meses", 72),
            taxa_minima_mes=_get_decimal_rule(self.session, "taxa_minima_mes", Decimal("0.005")),
            taxa_maxima_mes=_get_decimal_rule(self.session, "taxa_maxima_mes", Decimal("0.05")),
            dias_max_carencia=_get_int_rule(self.session, "dias_max_carencia", 90),
            valor_minimo_financiado=_get_decimal_rule(self.session, "valor_minimo_financiado", Decimal("5000")),
        )
        sim_input = SimulationInput(
            valor_veiculo=dto.valor_veiculo,
            valor_entrada=dto.valor_entrada,
            prazo_meses=dto.prazo_meses,
            taxa_mensal=dto.taxa_mensal,
            dias_carencia=dias_carencia,
        )
        issues = validate_simulation(sim_input, rules)
        errors = [i for i in issues if i.level == ValidationLevel.ERROR]
        if errors:
            raise SimulationServiceError(errors)

        # 3. PV inicial = veiculo - entrada + tarifas incluidas no principal
        tarifas_no_principal = sum(
            (t.valor for t in dto.tarifas if t.incluir_no_principal),
            start=Decimal("0"),
        )
        tarifas_total = sum((t.valor for t in dto.tarifas), start=Decimal("0"))
        pv_inicial = dto.valor_veiculo - dto.valor_entrada + tarifas_no_principal

        # 4. IOF config from business_rules
        iof_config = IofConfig(
            fixo_pct=_get_decimal_rule(self.session, "iof_fixo_pct", Decimal("0.0038")),
            diario_pct=_get_decimal_rule(self.session, "iof_diario_pct", Decimal("0.000082")),
            max_dias=_get_int_rule(self.session, "iof_diario_max_dias", 365),
        )

        # 5. Run core calculation
        financed = compute_financed_amount_with_iof(
            pv_inicial=pv_inicial,
            taxa_mensal=dto.taxa_mensal,
            n=dto.prazo_meses,
            d1=dias_carencia,
            data_liberacao=dto.data_liberacao,
            config=iof_config,
            incluir_iof=dto.incluir_iof,
        )

        # 6. CET
        cet = compute_cet(
            valor_liberado=dto.valor_veiculo - dto.valor_entrada,
            schedule=financed.schedule,
            data_liberacao=dto.data_liberacao,
        )

        # 7. Extras
        extras_per_parcela = compute_extras_per_parcela(dto.extras, dto.prazo_meses)
        extras_total_acumulado = quantize_brl(sum(extras_per_parcela, start=Decimal("0")))

        # 8. Persist
        codigo = _next_codigo(self.session, "SIM")
        pct_entrada = (dto.valor_entrada / dto.valor_veiculo).quantize(Decimal("0.0001"))
        taxa_anual = ((Decimal("1") + dto.taxa_mensal) ** 12 - Decimal("1")).quantize(Decimal("0.00000001"))
        total_pago = quantize_brl(sum((r.parcela for r in financed.schedule.rows), start=Decimal("0")))
        total_juros = quantize_brl(sum((r.juros for r in financed.schedule.rows), start=Decimal("0")))
        pct_juros = (total_juros / dto.valor_veiculo).quantize(Decimal("0.0001"))

        rules_snapshot = {
            r.chave: r.valor_json for r in self.session.query(BusinessRule).all()
        }

        sim = Simulation(
            codigo=codigo,
            cliente_id=dto.cliente_id,
            veiculo_id=dto.veiculo_id,
            criado_por=dto.criado_por,
            valor_veiculo=dto.valor_veiculo,
            valor_entrada=dto.valor_entrada,
            pct_entrada=pct_entrada,
            prazo_meses=dto.prazo_meses,
            taxa_juros_mes=dto.taxa_mensal,
            taxa_juros_ano=taxa_anual,
            data_liberacao=dto.data_liberacao,
            data_primeiro_venc=dto.data_primeiro_venc,
            dias_carencia=dias_carencia,
            incluir_iof=dto.incluir_iof,
            iof_total=financed.iof.total,
            tarifas_total=tarifas_total,
            extras_total_acumulado=extras_total_acumulado,
            valor_financiado=financed.valor_financiado,
            valor_parcela=financed.schedule.pmt,
            total_pago=total_pago,
            total_juros=total_juros,
            pct_juros=pct_juros,
            cet_mes=cet.cet_mes,
            cet_ano=cet.cet_ano,
            status="finalizada",
            rules_snapshot_json=json.dumps(rules_snapshot),
        )
        self.session.add(sim)
        self.session.commit()

        # 9. Persist tarifas
        for t in dto.tarifas:
            self.session.add(SimulationFee(
                simulation_id=sim.id, nome=t.nome, valor=t.valor,
                incluir_no_principal=t.incluir_no_principal,
            ))

        # 10. Persist extras
        for e in dto.extras:
            self.session.add(SimulationExtra(
                simulation_id=sim.id,
                tipo=e.tipo, nome=e.nome,
                valor_total=e.valor_total, modalidade=e.modalidade.value,
                duracao_meses=e.duracao_meses,
                valor_por_parcela=(e.valor_total / Decimal(e.duracao_meses)).quantize(Decimal("0.0001")),
                ordem=e.ordem,
            ))

        # 11. Persist amortization rows
        for idx, row in enumerate(financed.schedule.rows):
            extras_total = extras_per_parcela[idx] if idx < len(extras_per_parcela) else Decimal("0")
            self.session.add(AmortizationRow(
                simulation_id=sim.id,
                numero_parcela=row.numero_parcela,
                data_vencimento=row.data_vencimento,
                dias_periodo=row.dias_periodo,
                saldo_anterior=row.saldo_anterior,
                juros=row.juros,
                amortizacao=row.amortizacao,
                parcela=row.parcela,
                saldo_devedor=row.saldo_devedor,
                extras_total=extras_total,
                parcela_total=row.parcela + extras_total,
                ajuste_arredondamento=row.ajuste_arredondamento,
            ))

        self.session.commit()
        self.audit.log(
            usuario_id=dto.criado_por, acao="sim_criada",
            entidade="simulations", entidade_id=sim.id,
        )
        return sim
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/services/test_simulation_service.py -v`
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/simulation_service.py tests/unit/services/test_simulation_service.py
git commit -m "feat(services): SimulationService - run, validation, IOF, extras, persistence"
```

---

## Task 5: `ComparisonService`

**Files:**
- Create: `app/services/comparison_service.py`
- Create: `tests/unit/services/test_comparison_service.py`

**Design note:** `diff()` is a read-only calculation the UI can call freely (e.g., while browsing). `save()` is a separate explicit action. They are intentionally independent.

- [ ] **Step 1: Write the failing test**

`tests/unit/services/test_comparison_service.py`:
```python
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.data.database import Base, create_engine_for_sqlite, get_session_factory
from app.services.auth_service import AuthService
from app.services.comparison_service import ComparisonService
from app.services.simulation_service import SimulationInputDTO, SimulationService


@pytest.fixture()
def session():
    with tempfile.TemporaryDirectory() as tmp:
        engine = create_engine_for_sqlite(Path(tmp) / "test.db")
        Base.metadata.create_all(engine)
        SessionLocal = get_session_factory(engine)
        with SessionLocal() as s:
            yield s


def test_compare_two_simulations(session):
    user = AuthService(session).create_user("vendedor", "123456", "vendedor")
    from app.data.models import Vehicle
    v = Vehicle(fonte="manual", tipo="carro", marca="Fiat", modelo="Mobi",
                ano_modelo=2024, combustivel="Gasolina", valor_referencia=Decimal("50000"))
    session.add(v); session.commit()

    sim_svc = SimulationService(session)
    sim_a = sim_svc.run_and_save(SimulationInputDTO(
        criado_por=user.id, cliente_id=None, veiculo_id=v.id,
        valor_veiculo=Decimal("50000"), valor_entrada=Decimal("10000"),
        prazo_meses=24, taxa_mensal=Decimal("0.015"),
        data_liberacao=date(2026, 1, 1), data_primeiro_venc=date(2026, 1, 31),
        incluir_iof=False, tarifas=[], extras=[],
    ))
    sim_b = sim_svc.run_and_save(SimulationInputDTO(
        criado_por=user.id, cliente_id=None, veiculo_id=v.id,
        valor_veiculo=Decimal("50000"), valor_entrada=Decimal("15000"),
        prazo_meses=24, taxa_mensal=Decimal("0.015"),
        data_liberacao=date(2026, 1, 1), data_primeiro_venc=date(2026, 1, 31),
        incluir_iof=False, tarifas=[], extras=[],
    ))

    comp_svc = ComparisonService(session)
    diff = comp_svc.diff(sim_a.id, sim_b.id)
    assert diff.delta_parcela < Decimal("0")  # B has higher entrada -> lower parcela
    assert diff.delta_total_pago < Decimal("0")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/services/test_comparison_service.py -v`
Expected: FAIL.

- [ ] **Step 3: Write implementation**

`app/services/comparison_service.py`:
```python
"""ComparisonService - compute and persist comparisons between simulations."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from app.data.models import Comparison, Simulation


@dataclass(frozen=True)
class ComparisonResult:
    sim_a_id: int
    sim_b_id: int
    delta_taxa: Decimal
    delta_prazo: int
    delta_entrada: Decimal
    delta_parcela: Decimal
    delta_juros_totais: Decimal
    delta_total_pago: Decimal


class ComparisonService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def diff(self, sim_a_id: int, sim_b_id: int) -> ComparisonResult:
        a = self.session.get(Simulation, sim_a_id)
        b = self.session.get(Simulation, sim_b_id)
        if a is None or b is None:
            raise ValueError("simulation not found")
        return ComparisonResult(
            sim_a_id=a.id, sim_b_id=b.id,
            delta_taxa=b.taxa_juros_mes - a.taxa_juros_mes,
            delta_prazo=b.prazo_meses - a.prazo_meses,
            delta_entrada=b.valor_entrada - a.valor_entrada,
            delta_parcela=b.valor_parcela - a.valor_parcela,
            delta_juros_totais=b.total_juros - a.total_juros,
            delta_total_pago=b.total_pago - a.total_pago,
        )

    def save(self, sim_a_id: int, sim_b_id: int, criado_por: int) -> Comparison:
        c = Comparison(simulation_a_id=sim_a_id, simulation_b_id=sim_b_id, criado_por=criado_por)
        self.session.add(c)
        self.session.commit()
        return c
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/services/test_comparison_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/comparison_service.py tests/unit/services/test_comparison_service.py
git commit -m "feat(services): ComparisonService"
```

---

## Task 6: `AmortizationService` — extraordinary payments

**Files:**
- Create: `app/services/amortization_service.py`
- Create: `tests/unit/services/test_amortization_service.py`

**Design note:** Simulations are immutable — the original record is never updated after creation. `ExtraordinaryAmortization` rows are annotations on top. The UI reconstructs the current state by calling `apply()` with all recorded payments.

- [ ] **Step 1: Write the failing test**

`tests/unit/services/test_amortization_service.py`:
```python
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.core.amortization import AmortizationMode
from app.data.database import Base, create_engine_for_sqlite, get_session_factory
from app.services.amortization_service import AmortizationService, ExtraPaymentDTO
from app.services.auth_service import AuthService
from app.services.simulation_service import SimulationInputDTO, SimulationService


@pytest.fixture()
def session():
    with tempfile.TemporaryDirectory() as tmp:
        engine = create_engine_for_sqlite(Path(tmp) / "test.db")
        Base.metadata.create_all(engine)
        SessionLocal = get_session_factory(engine)
        with SessionLocal() as s:
            yield s


def test_apply_partial_quitacao_reduces_pmt(session):
    user = AuthService(session).create_user("v", "123456", "vendedor")
    from app.data.models import Vehicle
    v = Vehicle(fonte="manual", tipo="carro", marca="F", modelo="M",
                ano_modelo=2024, combustivel="G", valor_referencia=Decimal("50000"))
    session.add(v); session.commit()

    sim_svc = SimulationService(session)
    sim = sim_svc.run_and_save(SimulationInputDTO(
        criado_por=user.id, cliente_id=None, veiculo_id=v.id,
        valor_veiculo=Decimal("50000"), valor_entrada=Decimal("10000"),
        prazo_meses=24, taxa_mensal=Decimal("0.015"),
        data_liberacao=date(2026, 1, 1), data_primeiro_venc=date(2026, 1, 31),
        incluir_iof=False, tarifas=[], extras=[],
    ))

    svc = AmortizationService(session)
    new_schedule = svc.apply(
        simulation_id=sim.id,
        pagamentos=[ExtraPaymentDTO(
            data=date(2026, 6, 1), valor=Decimal("5000"),
            modo=AmortizationMode.REDUZIR_PARCELA,
        )],
    )
    assert new_schedule.pmt < sim.valor_parcela
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/services/test_amortization_service.py -v`
Expected: FAIL.

- [ ] **Step 3: Write implementation**

`app/services/amortization_service.py`:
```python
"""AmortizationService - applies extraordinary payments to a saved simulation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.amortization import AmortizationMode, ExtraPayment, apply_extraordinary_amortizations
from app.core.price_table import Schedule, ScheduleRow
from app.data.models import AmortizationRow, ExtraordinaryAmortization, Simulation
from app.services.audit_service import AuditService


@dataclass
class ExtraPaymentDTO:
    data: date
    valor: Decimal
    modo: AmortizationMode


class AmortizationService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.audit = AuditService(session)

    def _load_schedule(self, simulation_id: int) -> Schedule:
        rows_db = (
            self.session.query(AmortizationRow)
            .filter_by(simulation_id=simulation_id)
            .order_by(AmortizationRow.numero_parcela)
            .all()
        )
        rows = [
            ScheduleRow(
                numero_parcela=r.numero_parcela,
                data_vencimento=r.data_vencimento,
                dias_periodo=r.dias_periodo,
                saldo_anterior=r.saldo_anterior,
                juros=r.juros,
                amortizacao=r.amortizacao,
                parcela=r.parcela,
                saldo_devedor=r.saldo_devedor,
                ajuste_arredondamento=r.ajuste_arredondamento,
            )
            for r in rows_db
        ]
        sim = self.session.get(Simulation, simulation_id)
        assert sim is not None
        return Schedule(
            rows=rows,
            pmt=sim.valor_parcela,
            total_pago=sim.total_pago,
            total_juros=sim.total_juros,
        )

    def apply(
        self,
        simulation_id: int,
        pagamentos: list[ExtraPaymentDTO],
    ) -> Schedule:
        sim = self.session.get(Simulation, simulation_id)
        assert sim is not None
        original = self._load_schedule(simulation_id)
        extras = [
            ExtraPayment(data=p.data, valor=p.valor, modo=p.modo) for p in pagamentos
        ]
        novo = apply_extraordinary_amortizations(
            schedule_original=original,
            pagamentos=extras,
            taxa_mensal=sim.taxa_juros_mes,
            data_liberacao=sim.data_liberacao,
        )

        for p in pagamentos:
            self.session.add(ExtraordinaryAmortization(
                simulation_id=simulation_id,
                data=p.data, valor=p.valor, modo=p.modo.value,
                tipo="total" if p.valor >= sim.valor_financiado else "parcial",
            ))
        self.session.commit()
        self.audit.log(
            usuario_id=sim.criado_por, acao="amortizacao_extraordinaria",
            entidade="simulations", entidade_id=simulation_id,
            diff={"pagamentos_aplicados": len(pagamentos)},
        )
        return novo
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/services/test_amortization_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/amortization_service.py tests/unit/services/test_amortization_service.py
git commit -m "feat(services): AmortizationService"
```

---

## Task 7: `IndicatorsService` — facade over BACEN chain

**Files:**
- Create: `app/services/indicators_service.py`
- Create: `tests/unit/services/test_indicators_service.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/services/test_indicators_service.py`:
```python
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.data.database import Base, create_engine_for_sqlite, get_session_factory
from app.integrations.bacen.schema import IndicatorPoint
from app.integrations.base import Ok
from app.services.indicators_service import IndicatorsService


class FakeChain:
    async def fetch(self, query):
        return Ok([
            IndicatorPoint(
                codigo=query["codigo"],
                data_referencia=date(2026, 5, 23),
                valor_fracao=Decimal("0.1050"),
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


@pytest.mark.asyncio
async def test_update_indicator_persists(session_factory):
    svc = IndicatorsService(session_factory, bacen_chain=FakeChain())
    point = await svc.update_indicator("SELIC_META", date(2026, 5, 1), date(2026, 5, 31))
    assert point is not None
    assert point.valor_fracao == Decimal("0.1050")
    # check persisted
    from app.data.models import IndicatorHistory
    with session_factory() as s:
        row = s.query(IndicatorHistory).filter_by(codigo="SELIC_META").first()
        assert row is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/services/test_indicators_service.py -v`
Expected: FAIL.

- [ ] **Step 3: Write implementation**

`app/services/indicators_service.py`:
```python
"""IndicatorsService - fetch + cache BACEN indicators."""

from __future__ import annotations

from datetime import date

from app.data.repositories import IndicatorRepository
from app.integrations.bacen.schema import IndicatorPoint


class IndicatorsService:
    def __init__(self, session_factory, bacen_chain) -> None:
        self.session_factory = session_factory
        self.chain = bacen_chain

    async def update_indicator(
        self, codigo: str, data_inicial: date, data_final: date,
    ) -> IndicatorPoint | None:
        result = await self.chain.fetch({
            "codigo": codigo,
            "data_inicial": data_inicial,
            "data_final": data_final,
        })
        if not result.is_ok or not result.value:
            return None
        points = result.value
        # Persist in case the chain doesn't auto-cache (defensive)
        with self.session_factory() as session:
            repo = IndicatorRepository(session)
            for pt in points:
                repo.upsert(
                    codigo=pt.codigo, data_referencia=pt.data_referencia,
                    valor=pt.valor_fracao, unidade=pt.unidade, fonte=pt.fonte,
                )
        return points[-1]

    def latest(self, codigo: str) -> IndicatorPoint | None:
        with self.session_factory() as session:
            row = IndicatorRepository(session).get_latest(codigo)
            if row is None:
                return None
            return IndicatorPoint(
                codigo=row.codigo, data_referencia=row.data_referencia,
                valor_fracao=row.valor, unidade=row.unidade, fonte=row.fonte,
            )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/services/test_indicators_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/indicators_service.py tests/unit/services/test_indicators_service.py
git commit -m "feat(services): IndicatorsService - update + latest"
```

---

## Task 8: `ProposalService` — generates Proposal snapshot (PDF deferred to Phase 6)

**Files:**
- Create: `app/services/proposal_service.py`
- Create: `tests/unit/services/test_proposal_service.py`

**Design note:** Clientless proposals are allowed (walk-in quotes). When `sim.cliente_id is None`, the snapshot contains `"cliente": null`. A `Proposal` becomes a formal document once a client is attached in Phase 5 UI.

- [ ] **Step 1: Write the failing test**

`tests/unit/services/test_proposal_service.py`:
```python
import json
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.data.database import Base, create_engine_for_sqlite, get_session_factory
from app.services.auth_service import AuthService
from app.services.client_service import ClientService
from app.services.proposal_service import ProposalService
from app.services.simulation_service import SimulationInputDTO, SimulationService


@pytest.fixture()
def session():
    with tempfile.TemporaryDirectory() as tmp:
        engine = create_engine_for_sqlite(Path(tmp) / "test.db")
        Base.metadata.create_all(engine)
        SessionLocal = get_session_factory(engine)
        with SessionLocal() as s:
            yield s


def test_create_proposal_persists_snapshot(session):
    user = AuthService(session).create_user("vendedor", "123456", "vendedor")
    client = ClientService(session).create_pf(
        nome="Maria", cpf="529.982.247-25", criado_por=user.id,
    )
    from app.data.models import Vehicle
    v = Vehicle(fonte="manual", tipo="carro", marca="F", modelo="M",
                ano_modelo=2024, combustivel="G", valor_referencia=Decimal("50000"))
    session.add(v); session.commit()
    sim = SimulationService(session).run_and_save(SimulationInputDTO(
        criado_por=user.id, cliente_id=client.id, veiculo_id=v.id,
        valor_veiculo=Decimal("50000"), valor_entrada=Decimal("10000"),
        prazo_meses=24, taxa_mensal=Decimal("0.015"),
        data_liberacao=date(2026, 1, 1), data_primeiro_venc=date(2026, 1, 31),
        incluir_iof=False, tarifas=[], extras=[],
    ))

    proposal = ProposalService(session).create(sim.id, gerado_por=user.id, validade_dias=7)
    assert proposal.codigo.startswith("PROP-")
    snap = json.loads(proposal.snapshot_json)
    assert snap["simulation"]["codigo"] == sim.codigo
    assert snap["simulation"]["valor_parcela"] is not None
    assert snap["cliente"]["nome"] == "Maria"


def test_create_clientless_proposal(session):
    user = AuthService(session).create_user("vendedor", "123456", "vendedor")
    from app.data.models import Vehicle
    v = Vehicle(fonte="manual", tipo="carro", marca="F", modelo="M",
                ano_modelo=2024, combustivel="G", valor_referencia=Decimal("50000"))
    session.add(v); session.commit()
    sim = SimulationService(session).run_and_save(SimulationInputDTO(
        criado_por=user.id, cliente_id=None, veiculo_id=v.id,
        valor_veiculo=Decimal("50000"), valor_entrada=Decimal("10000"),
        prazo_meses=24, taxa_mensal=Decimal("0.015"),
        data_liberacao=date(2026, 1, 1), data_primeiro_venc=date(2026, 1, 31),
        incluir_iof=False, tarifas=[], extras=[],
    ))

    proposal = ProposalService(session).create(sim.id, gerado_por=user.id)
    snap = json.loads(proposal.snapshot_json)
    assert snap["cliente"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/services/test_proposal_service.py -v`
Expected: FAIL.

- [ ] **Step 3: Write implementation**

`app/services/proposal_service.py`:
```python
"""ProposalService - builds Proposal record + snapshot JSON. PDF in Phase 6."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.data.models import (
    AmortizationRow,
    Client,
    Proposal,
    Simulation,
    SimulationExtra,
    SimulationFee,
    Vehicle,
)
from app.services.audit_service import AuditService


def _next_codigo(session: Session) -> str:
    year = date.today().year
    count = session.query(Proposal).filter(Proposal.codigo.like(f"PROP-{year}-%")).count()
    return f"PROP-{year}-{count + 1:05d}"


def _decimal_to_str(v: Decimal) -> str:
    return str(v)


class ProposalService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.audit = AuditService(session)

    def create(self, simulation_id: int, gerado_por: int, validade_dias: int = 7) -> Proposal:
        sim = self.session.get(Simulation, simulation_id)
        if sim is None:
            raise ValueError("simulation not found")

        cliente = self.session.get(Client, sim.cliente_id) if sim.cliente_id is not None else None
        veiculo = self.session.get(Vehicle, sim.veiculo_id)
        fees = self.session.query(SimulationFee).filter_by(simulation_id=sim.id).all()
        extras = self.session.query(SimulationExtra).filter_by(simulation_id=sim.id).order_by(SimulationExtra.ordem).all()
        rows = (
            self.session.query(AmortizationRow)
            .filter_by(simulation_id=sim.id)
            .order_by(AmortizationRow.numero_parcela)
            .all()
        )

        cliente_snap = None
        if cliente is not None:
            cliente_snap = {
                "nome": cliente.nome, "cpf_cnpj": cliente.cpf_cnpj, "tipo": cliente.tipo,
                "telefone": cliente.telefone, "email": cliente.email,
                "endereco_json": cliente.endereco_json,
            }

        snapshot = {
            "simulation": {
                "codigo": sim.codigo,
                "valor_veiculo": _decimal_to_str(sim.valor_veiculo),
                "valor_entrada": _decimal_to_str(sim.valor_entrada),
                "pct_entrada": _decimal_to_str(sim.pct_entrada),
                "prazo_meses": sim.prazo_meses,
                "taxa_juros_mes": _decimal_to_str(sim.taxa_juros_mes),
                "taxa_juros_ano": _decimal_to_str(sim.taxa_juros_ano),
                "data_liberacao": sim.data_liberacao.isoformat(),
                "data_primeiro_venc": sim.data_primeiro_venc.isoformat(),
                "incluir_iof": sim.incluir_iof,
                "iof_total": _decimal_to_str(sim.iof_total),
                "tarifas_total": _decimal_to_str(sim.tarifas_total),
                "extras_total_acumulado": _decimal_to_str(sim.extras_total_acumulado),
                "valor_financiado": _decimal_to_str(sim.valor_financiado),
                "valor_parcela": _decimal_to_str(sim.valor_parcela),
                "total_pago": _decimal_to_str(sim.total_pago),
                "total_juros": _decimal_to_str(sim.total_juros),
                "cet_mes": _decimal_to_str(sim.cet_mes),
                "cet_ano": _decimal_to_str(sim.cet_ano),
            },
            "cliente": cliente_snap,
            "veiculo": {
                "marca": veiculo.marca, "modelo": veiculo.modelo,
                "ano_modelo": veiculo.ano_modelo, "combustivel": veiculo.combustivel,
                "codigo_fipe": veiculo.codigo_fipe,
                "valor_fipe": _decimal_to_str(veiculo.valor_fipe) if veiculo.valor_fipe else None,
                "mes_referencia_fipe": veiculo.mes_referencia_fipe,
            },
            "tarifas": [
                {"nome": f.nome, "valor": _decimal_to_str(f.valor),
                 "incluir_no_principal": f.incluir_no_principal}
                for f in fees
            ],
            "extras": [
                {"tipo": e.tipo, "nome": e.nome,
                 "valor_total": _decimal_to_str(e.valor_total),
                 "modalidade": e.modalidade, "duracao_meses": e.duracao_meses,
                 "valor_por_parcela": _decimal_to_str(e.valor_por_parcela)}
                for e in extras
            ],
            "cronograma": [
                {"numero": r.numero_parcela, "venc": r.data_vencimento.isoformat(),
                 "juros": _decimal_to_str(r.juros), "amortizacao": _decimal_to_str(r.amortizacao),
                 "parcela": _decimal_to_str(r.parcela), "extras": _decimal_to_str(r.extras_total),
                 "parcela_total": _decimal_to_str(r.parcela_total),
                 "saldo": _decimal_to_str(r.saldo_devedor)}
                for r in rows
            ],
        }

        proposal = Proposal(
            codigo=_next_codigo(self.session),
            simulation_id=sim.id,
            cliente_id=cliente.id if cliente else None,
            gerado_por=gerado_por,
            snapshot_json=json.dumps(snapshot),
            pdf_path=None,
            validade_dias=validade_dias,
        )
        self.session.add(proposal)
        self.session.commit()
        self.audit.log(
            usuario_id=gerado_por, acao="proposta_gerada",
            entidade="proposals", entidade_id=proposal.id,
        )
        return proposal
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/services/test_proposal_service.py -v`
Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/proposal_service.py tests/unit/services/test_proposal_service.py
git commit -m "feat(services): ProposalService with snapshot JSON, clientless support"
```

---

## Task 9: `RulesService` — typed access to `business_rules` table

**Files:**
- Create: `app/services/rules_service.py`
- Create: `tests/unit/services/test_rules_service.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/services/test_rules_service.py`:
```python
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

from app.data.database import Base, create_engine_for_sqlite, get_session_factory
from app.data.repositories import BusinessRuleRepository
from app.services.rules_service import RulesService


@pytest.fixture()
def session():
    with tempfile.TemporaryDirectory() as tmp:
        engine = create_engine_for_sqlite(Path(tmp) / "test.db")
        Base.metadata.create_all(engine)
        SessionLocal = get_session_factory(engine)
        with SessionLocal() as s:
            # seed required rule
            BusinessRuleRepository(s).set("entrada_minima_pct", "0.10")
            BusinessRuleRepository(s).set("iof_fixo_pct", "0.0038")
            BusinessRuleRepository(s).set("incluir_iof_default", "true")
            yield s


def test_decimal_default_value_when_missing(session):
    svc = RulesService(session)
    val = svc.get_decimal("nao_existe", default=Decimal("99"))
    assert val == Decimal("99")


def test_bool_value(session):
    svc = RulesService(session)
    val = svc.get_bool("incluir_iof_default", default=False)
    assert val is True


def test_decimal_value(session):
    svc = RulesService(session)
    val = svc.get_decimal("iof_fixo_pct", default=Decimal("0"))
    assert val == Decimal("0.0038")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/services/test_rules_service.py -v`
Expected: FAIL.

- [ ] **Step 3: Write implementation**

`app/services/rules_service.py`:
```python
"""RulesService - typed access to business_rules."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.data.repositories import BusinessRuleRepository
from app.services.audit_service import AuditService


class RulesService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repo = BusinessRuleRepository(session)
        self.audit = AuditService(session)

    def get_raw(self, chave: str) -> str | None:
        return self.repo.get(chave)

    def get_decimal(self, chave: str, default: Decimal) -> Decimal:
        raw = self.get_raw(chave)
        if raw is None:
            return default
        return Decimal(raw)

    def get_int(self, chave: str, default: int) -> int:
        raw = self.get_raw(chave)
        if raw is None:
            return default
        return int(raw)

    def get_bool(self, chave: str, default: bool) -> bool:
        raw = self.get_raw(chave)
        if raw is None:
            return default
        return raw.lower() in {"true", "1", "yes"}

    def get_json(self, chave: str, default: Any) -> Any:
        raw = self.get_raw(chave)
        if raw is None:
            return default
        return json.loads(raw)

    def set(self, chave: str, value: Any, user_id: int | None = None) -> None:
        old = self.get_raw(chave)
        valor_json = json.dumps(value) if not isinstance(value, str) else value
        self.repo.set(chave, valor_json, user_id=user_id)
        self.audit.log(
            usuario_id=user_id, acao="config_alterada",
            entidade="business_rules",
            diff={"chave": chave, "old": old, "new": valor_json},
        )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/services/test_rules_service.py -v`
Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/rules_service.py tests/unit/services/test_rules_service.py
git commit -m "feat(services): RulesService - typed access to business_rules"
```

---

## Task 10: `BackupService` thin wrapper for UI

**Files:**
- Create: `app/services/backup_service.py`
- Create: `tests/unit/services/test_backup_service.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/services/test_backup_service.py`:
```python
import tempfile
from pathlib import Path

import pytest

from app.data.database import Base, create_engine_for_sqlite
from app.services.backup_service import BackupService


def test_backup_now_creates_file():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        db = tmp_path / "test.db"
        engine = create_engine_for_sqlite(db)
        Base.metadata.create_all(engine)
        engine.dispose()

        svc = BackupService(db_path=db, backup_dir=tmp_path / "backups")
        path = svc.backup_now()
        assert path.exists()
        backups = svc.list()
        assert len(backups) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/services/test_backup_service.py -v`
Expected: FAIL.

- [ ] **Step 3: Write implementation**

`app/services/backup_service.py`:
```python
"""BackupService - thin facade over app.data.backup for UI/scheduler."""

from __future__ import annotations

from pathlib import Path

from app.data.backup import backup_sqlite, list_backups, prune_backups, restore_sqlite


class BackupService:
    def __init__(self, db_path: Path, backup_dir: Path) -> None:
        self.db_path = db_path
        self.backup_dir = backup_dir

    def backup_now(self) -> Path:
        return backup_sqlite(self.db_path, self.backup_dir)

    def list(self) -> list[Path]:
        return list_backups(self.backup_dir)

    def prune(self, keep_days: int) -> int:
        return prune_backups(self.backup_dir, keep_days=keep_days)

    def restore(self, backup_file: Path) -> None:
        restore_sqlite(backup_file, self.db_path)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/services/test_backup_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/backup_service.py tests/unit/services/test_backup_service.py
git commit -m "feat(services): BackupService facade"
```

---

## Task 11: Integration test — full end-to-end

**Files:**
- Create: `tests/integration/test_full_flow.py`

- [ ] **Step 1: Write integration test**

`tests/integration/test_full_flow.py`:
```python
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.core.extras import Extra, ExtraModalidade
from app.data.database import Base, create_engine_for_sqlite, get_session_factory
from app.services.auth_service import AuthService
from app.services.client_service import ClientService
from app.services.proposal_service import ProposalService
from app.services.simulation_service import SimulationInputDTO, SimulationService


@pytest.mark.integration
def test_complete_flow_user_client_sim_proposal():
    with tempfile.TemporaryDirectory() as tmp:
        engine = create_engine_for_sqlite(Path(tmp) / "e2e.db")
        Base.metadata.create_all(engine)
        SessionLocal = get_session_factory(engine)
        with SessionLocal() as session:
            # 1. Vendedor cadastrado
            vendedor = AuthService(session).create_user("Joao", "123456", "vendedor")

            # 2. Cliente cadastrado
            client = ClientService(session).create_pf(
                nome="Maria", cpf="529.982.247-25", criado_por=vendedor.id,
            )

            # 3. Veiculo
            from app.data.models import Vehicle
            v = Vehicle(
                fonte="manual", tipo="carro", marca="Fiat", modelo="Mobi",
                ano_modelo=2024, combustivel="Gasolina", valor_referencia=Decimal("50000"),
            )
            session.add(v); session.commit()

            # 4. Simulacao com IOF + extras
            sim = SimulationService(session).run_and_save(SimulationInputDTO(
                criado_por=vendedor.id,
                cliente_id=client.id,
                veiculo_id=v.id,
                valor_veiculo=Decimal("50000"),
                valor_entrada=Decimal("10000"),
                prazo_meses=48,
                taxa_mensal=Decimal("0.0189"),
                data_liberacao=date(2026, 1, 1),
                data_primeiro_venc=date(2026, 1, 31),
                incluir_iof=True,
                tarifas=[],
                extras=[
                    Extra("ipva", "IPVA", Decimal("1800"),
                          ExtraModalidade.RATEIO_MESES, 12, 1),
                    Extra("protecao_veicular", "Protecao", Decimal("80"),
                          ExtraModalidade.MENSAL_CONTINUO, 48, 2),
                ],
            ))

            # 5. Proposta
            proposal = ProposalService(session).create(sim.id, gerado_por=vendedor.id)

            # Asserts
            assert sim.iof_total > Decimal("0")
            assert sim.cet_mes > Decimal("0.0189")  # CET > taxa due to IOF
            assert sim.extras_total_acumulado == Decimal("5640.00")  # 1800 + 80*48
            assert proposal.snapshot_json is not None
            import json
            snap = json.loads(proposal.snapshot_json)
            assert len(snap["cronograma"]) == 48
            assert len(snap["extras"]) == 2
            assert snap["cliente"]["nome"] == "Maria"
```

- [ ] **Step 2: Run test**

Run: `pytest tests/integration/test_full_flow.py -v -m integration`
Expected: PASS.

- [ ] **Step 3: Run full Phase 4 suite + mypy + ruff**

Run:
```bash
pytest tests/unit/services/ tests/integration/ -v
mypy app/services/
ruff check app/services/ tests/unit/services/
```

Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_full_flow.py
git commit -m "test(services): full end-to-end flow integration test"
```

---

## Task 12: `scheduler.py` — background jobs (indicators + backup)

**Files:**
- Create: `app/services/scheduler.py`
- Create: `tests/unit/services/test_scheduler.py`

**Design decisions:**
- APScheduler `BackgroundScheduler` (sync); async indicator job wrapped with `asyncio.run()` in a background thread (safe since NiceGUI's event loop runs in the main thread).
- Job times read from `business_rules` at startup only. Dynamic rescheduling deferred to Phase 5.
- BACEN codes hardcoded: `SELIC_META`, `CDI`, `IPCA`, `TX_BACEN_VEICULOS`.
- Date range for indicators: yesterday → today.
- `_run_indicators_update` and `_run_backup` are module-level functions — testable without APScheduler.
- `# TODO(Phase 5): centralize db_path/backup_dir in app/config.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/services/test_scheduler.py`:
```python
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.data.database import Base, create_engine_for_sqlite, get_session_factory
from app.integrations.bacen.schema import IndicatorPoint
from app.integrations.base import Ok
from app.services.scheduler import _BACEN_CODES, _run_backup, _run_indicators_update


class FakeChain:
    def __init__(self):
        self.fetched: list[str] = []

    async def fetch(self, query):
        self.fetched.append(query["codigo"])
        return Ok([
            IndicatorPoint(
                codigo=query["codigo"],
                data_referencia=date.today(),
                valor_fracao=Decimal("0.1050"),
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


@pytest.mark.asyncio
async def test_run_indicators_update_fetches_all_codes(session_factory):
    chain = FakeChain()
    await _run_indicators_update(session_factory, chain)
    assert set(chain.fetched) == set(_BACEN_CODES)


def test_run_backup_creates_file(session_factory):
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        db = tmp_path / "app.db"
        engine = create_engine_for_sqlite(db)
        Base.metadata.create_all(engine)
        engine.dispose()
        sf = get_session_factory(engine)
        backup_dir = tmp_path / "backups"
        _run_backup(db, backup_dir, sf)
        assert backup_dir.exists()
        assert any(backup_dir.iterdir())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/services/test_scheduler.py -v`
Expected: FAIL.

- [ ] **Step 3: Write implementation**

`app/services/scheduler.py`:
```python
"""Scheduler - APScheduler wiring for background jobs (indicators + backup).

# TODO(Phase 5): centralize db_path/backup_dir in app/config.py
"""

from __future__ import annotations

import asyncio
import json
from datetime import date, timedelta
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler

from app.data.repositories import BusinessRuleRepository
from app.services.backup_service import BackupService
from app.services.indicators_service import IndicatorsService

_BACEN_CODES = ["SELIC_META", "CDI", "IPCA", "TX_BACEN_VEICULOS"]

_scheduler: BackgroundScheduler | None = None


async def _run_indicators_update(session_factory, bacen_chain) -> None:
    svc = IndicatorsService(session_factory, bacen_chain)
    today = date.today()
    yesterday = today - timedelta(days=1)
    for codigo in _BACEN_CODES:
        await svc.update_indicator(codigo, yesterday, today)


def _run_backup(db_path: Path, backup_dir: Path, session_factory) -> None:
    svc = BackupService(db_path=db_path, backup_dir=backup_dir)
    svc.backup_now()
    with session_factory() as s:
        raw = BusinessRuleRepository(s).get("backup_retencao_dias")
        keep_days = int(raw) if raw else 30
    svc.prune(keep_days=keep_days)


def _indicators_job(session_factory, bacen_chain) -> None:
    asyncio.run(_run_indicators_update(session_factory, bacen_chain))


def _read_time(session_factory, chave: str, fallback: str) -> tuple[int, int]:
    with session_factory() as s:
        raw = BusinessRuleRepository(s).get(chave)
    time_str = json.loads(raw) if raw else fallback
    hour, minute = (int(x) for x in time_str.split(":"))
    return hour, minute


def start_scheduler(
    session_factory,
    bacen_chain,
    db_path: Path,
    backup_dir: Path,
) -> None:
    global _scheduler
    ind_hour, ind_min = _read_time(session_factory, "update_indicadores_horario", "09:00")
    bak_hour, bak_min = _read_time(session_factory, "backup_diario_horario", "23:00")

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        _indicators_job,
        trigger="cron",
        hour=ind_hour,
        minute=ind_min,
        id="indicators_update",
        args=[session_factory, bacen_chain],
    )
    _scheduler.add_job(
        _run_backup,
        trigger="cron",
        hour=bak_hour,
        minute=bak_min,
        id="daily_backup",
        args=[db_path, backup_dir, session_factory],
    )
    _scheduler.start()


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown()
        _scheduler = None
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/services/test_scheduler.py -v`
Expected: 2 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/scheduler.py tests/unit/services/test_scheduler.py
git commit -m "feat(services): scheduler - daily indicators update + backup via APScheduler"
```

---

## Phase 4 — Definition of Done

- [ ] All 12 tasks committed
- [ ] `pytest tests/unit/services/ tests/integration/` all green
- [ ] `mypy app/services/` 0 errors
- [ ] `ruff check app/services/` clean
- [ ] End-to-end test runs: user → client → simulation (with IOF + extras) → proposal
- [ ] All AuditLog entries created at the right points (verifiable by querying)
- [ ] Scheduler job functions (`_run_indicators_update`, `_run_backup`) tested with fakes
