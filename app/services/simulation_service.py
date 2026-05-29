"""SimulationService - orchestrates calculation + persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
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
class SimulationSummary:
    codigo: str
    veiculo_label: str
    cliente_nome: str
    valor_veiculo: Decimal
    valor_entrada: Decimal
    prazo_meses: int
    taxa_juros_mes: Decimal
    incluir_iof: bool
    data_liberacao: date
    data_primeiro_venc: date
    veiculo_id: int
    cliente_id: int | None
    criado_em: datetime


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

    def find_recent(self, limit: int = 100) -> list[SimulationSummary]:
        from app.data.models import Client, Vehicle
        sims = (
            self.session.query(Simulation)
            .order_by(Simulation.criado_em.desc())
            .limit(limit)
            .all()
        )
        result = []
        for s in sims:
            v = self.session.get(Vehicle, s.veiculo_id)
            c = self.session.get(Client, s.cliente_id) if s.cliente_id else None
            result.append(SimulationSummary(
                codigo=s.codigo,
                veiculo_label=f"{v.marca} {v.modelo} {v.ano_modelo}" if v else "—",
                cliente_nome=c.nome if c else "—",
                valor_veiculo=s.valor_veiculo,
                valor_entrada=s.valor_entrada,
                prazo_meses=s.prazo_meses,
                taxa_juros_mes=s.taxa_juros_mes,
                incluir_iof=s.incluir_iof,
                data_liberacao=s.data_liberacao,
                data_primeiro_venc=s.data_primeiro_venc,
                veiculo_id=s.veiculo_id,
                cliente_id=s.cliente_id,
                criado_em=s.criado_em,
            ))
        return result

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

        # 6. CET — note: no data_liberacao param
        cet = compute_cet(
            valor_liberado=dto.valor_veiculo - dto.valor_entrada,
            schedule=financed.schedule,
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
