import uuid
from decimal import Decimal
from datetime import date
from unittest.mock import MagicMock

import pytest

from finacialsim_saas.data.models import (
    AmortizationRow, Client, ClientType, Simulation,
    SimulationExtra, SimulationFee, SimulationStatus, Tenant, User, Role,
)
from finacialsim_saas.schemas.proposals import PropostaSnapshot, build_snapshot


def _make_sim() -> Simulation:
    s = MagicMock(spec=Simulation)
    s.tenant_id = uuid.uuid4()
    s.id = uuid.uuid4()
    s.client_id = None
    s.vehicle_id = None
    s.valor_veiculo = Decimal("85000.00")
    s.valor_entrada = Decimal("17000.00")
    s.valor_financiado = Decimal("68000.00")
    s.taxa_mensal = Decimal("0.012900")
    s.prazo_meses = 48
    s.data_liberacao = date(2026, 6, 1)
    s.primeiro_vencimento = date(2026, 7, 1)
    s.incluir_iof = True
    s.iof_total = Decimal("1224.00")
    s.parcela_financiamento = Decimal("1987.34")
    s.total_pago = Decimal("95392.32")
    s.total_juros = Decimal("27392.32")
    s.cet_mensal = Decimal("0.013500")
    s.cet_anual = Decimal("0.174500")
    s.status = SimulationStatus.confirmado
    return s


def _make_tenant() -> Tenant:
    t = MagicMock(spec=Tenant)
    t.id = uuid.uuid4()
    t.name = "Financiadora Teste"
    t.cnpj = None
    t.telefone = None
    t.endereco = None
    t.logo_key = None
    return t


def _make_user() -> User:
    u = MagicMock(spec=User)
    u.id = uuid.uuid4()
    u.name = "Vendedor Teste"
    u.role = Role.user
    return u


def _make_row(num: int) -> AmortizationRow:
    r = MagicMock(spec=AmortizationRow)
    r.numero_parcela = num
    r.data_vencimento = date(2026, 7, num)
    r.juros = Decimal("877.20")
    r.amortizacao = Decimal("1110.14")
    r.parcela = Decimal("1987.34")
    r.extras_total = Decimal("0.00")
    r.parcela_total = Decimal("1987.34")
    r.saldo_devedor = Decimal("68000.00") - num * Decimal("1110.14")
    return r


@pytest.fixture
def make_snapshot_deps():
    sim = _make_sim()
    fees: list = []
    extras: list = []
    rows = [_make_row(1)]
    client = None
    vehicle = None
    tenant = _make_tenant()
    user = _make_user()
    return sim, fees, extras, rows, client, vehicle, tenant, user


def test_build_snapshot_basic():
    snap = build_snapshot(
        sim=_make_sim(), fees=[], extras=[],
        rows=[_make_row(1), _make_row(2)],
        client=None, vehicle=None,
        tenant=_make_tenant(), user=_make_user(),
    )
    assert isinstance(snap, PropostaSnapshot)
    assert snap.loja.nome == "Financiadora Teste"
    assert snap.vendedor.nome == "Vendedor Teste"
    assert snap.cliente is None
    assert snap.veiculo is None
    assert snap.sim.prazo_meses == 48
    assert len(snap.cronograma) == 2
    assert snap.cronograma[0].venc == "2026-07-01"


def test_build_snapshot_tarifas_computed():
    fee = MagicMock(spec=SimulationFee)
    fee.valor = Decimal("300.00")
    fee2 = MagicMock(spec=SimulationFee)
    fee2.valor = Decimal("200.00")
    snap = build_snapshot(
        sim=_make_sim(), fees=[fee, fee2], extras=[],
        rows=[_make_row(1)], client=None, vehicle=None,
        tenant=_make_tenant(), user=_make_user(),
    )
    assert snap.sim.tarifas_total == "500.00"


def test_snapshot_rejects_extra_fields():
    with pytest.raises(Exception):
        PropostaSnapshot.model_validate({
            "loja": {"nome": "X", "unknown_field": "boom"},
            "vendedor": {"nome": "V"},
            "sim": {},
            "extras": [],
            "cronograma": [],
        })


def test_snapshot_roundtrip_json():
    snap = build_snapshot(
        sim=_make_sim(), fees=[], extras=[],
        rows=[_make_row(1)], client=None, vehicle=None,
        tenant=_make_tenant(), user=_make_user(),
    )
    dumped = snap.model_dump()
    restored = PropostaSnapshot.model_validate(dumped)
    assert restored.sim.prazo_meses == snap.sim.prazo_meses


def test_build_snapshot_includes_logo_key(make_snapshot_deps):
    """build_snapshot copies logo_key from Tenant into LojaSnap."""
    sim, fees, extras, rows, client, vehicle, tenant, user = make_snapshot_deps
    tenant.logo_key = "abc-tenant-id/logo/logo.png"
    tenant.cnpj = "12.345.678/0001-90"
    tenant.telefone = "11 99999-0000"
    tenant.endereco = "Rua Teste, 123"

    snap = build_snapshot(sim, fees, extras, rows, client, vehicle, tenant, user)

    assert snap.loja.logo_key == "abc-tenant-id/logo/logo.png"
    assert snap.loja.cnpj == "12.345.678/0001-90"
    assert snap.loja.telefone == "11 99999-0000"
    assert snap.loja.endereco == "Rua Teste, 123"


def test_build_snapshot_logo_key_none_when_unset(make_snapshot_deps):
    """logo_key is None when tenant has no logo."""
    sim, fees, extras, rows, client, vehicle, tenant, user = make_snapshot_deps
    tenant.logo_key = None
    snap = build_snapshot(sim, fees, extras, rows, client, vehicle, tenant, user)
    assert snap.loja.logo_key is None
