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
