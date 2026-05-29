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
