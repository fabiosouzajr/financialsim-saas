"""Amortizacao extraordinaria page."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from nicegui import ui

from app.core.amortization import AmortizationMode
from app.data.database import get_session_factory
from app.data.models import Simulation
from app.services.amortization_service import AmortizationService, ExtraPaymentDTO
from app.ui.components.currency_input import CurrencyInput
from app.ui.layout import shell
from app.utils.br_format import format_brl


def build_amortizacao_page(engine) -> None:
    SessionLocal = get_session_factory(engine)

    @ui.page("/amortizacao")
    def page() -> None:
        def content() -> None:
            with SessionLocal() as session:
                sims = session.query(Simulation).order_by(Simulation.criado_em.desc()).limit(50).all()
                options = {s.id: s.codigo for s in sims}

            sim_sel = ui.select(options=options, label="Simulacao base")
            data_in = ui.date(value=date.today().isoformat())
            valor = CurrencyInput("Valor pago", Decimal("0"))
            modo = ui.select(["reduzir_parcela", "reduzir_prazo"], value="reduzir_parcela", label="Modo")
            output = ui.column()

            def aplicar() -> None:
                output.clear()
                if not sim_sel.value or valor.value <= 0:
                    return
                with SessionLocal() as session:
                    new_sched = AmortizationService(session).apply(
                        simulation_id=sim_sel.value,
                        pagamentos=[ExtraPaymentDTO(
                            data=date.fromisoformat(data_in.value),
                            valor=valor.value,
                            modo=AmortizationMode(modo.value),
                        )],
                    )
                with output:
                    ui.label(f"Nova PMT: {format_brl(new_sched.pmt)}")
                    ui.label(f"Total pago apos amortizacao: {format_brl(new_sched.total_pago)}")
                    ui.label(f"Parcelas restantes: {len(new_sched.rows)}")

            ui.button("Aplicar amortizacao", on_click=aplicar)

        shell(content)