"""Comparativo page - load 2 saved simulations and diff."""

from __future__ import annotations

from nicegui import ui

from app.data.database import get_session_factory
from app.data.models import Simulation
from app.services.comparison_service import ComparisonService
from app.ui.layout import shell
from app.utils.br_format import format_brl, format_pct


def build_comparativo_page(engine) -> None:
    SessionLocal = get_session_factory(engine)

    @ui.page("/comparativo")
    def page() -> None:
        def content() -> None:
            with SessionLocal() as session:
                sims = session.query(Simulation).order_by(Simulation.criado_em.desc()).limit(50).all()
                options = {s.id: s.codigo for s in sims}

            sel_a = ui.select(options=options, label="Simulacao A")
            sel_b = ui.select(options=options, label="Simulacao B")
            output = ui.column()

            def compare() -> None:
                output.clear()
                if not sel_a.value or not sel_b.value:
                    return
                with SessionLocal() as session:
                    diff = ComparisonService(session).diff(sel_a.value, sel_b.value)
                    a = session.get(Simulation, sel_a.value)
                    b = session.get(Simulation, sel_b.value)
                with output:
                    ui.table(
                        columns=[
                            {"name": "campo", "label": "Campo", "field": "campo"},
                            {"name": "a", "label": "A", "field": "a"},
                            {"name": "b", "label": "B", "field": "b"},
                            {"name": "delta", "label": "Diferenca", "field": "delta"},
                        ],
                        rows=[
                            {"campo": "Taxa", "a": format_pct(a.taxa_juros_mes),
                             "b": format_pct(b.taxa_juros_mes),
                             "delta": format_pct(diff.delta_taxa)},
                            {"campo": "Prazo", "a": f"{a.prazo_meses}m",
                             "b": f"{b.prazo_meses}m",
                             "delta": f"{diff.delta_prazo:+d}m"},
                            {"campo": "Entrada", "a": format_brl(a.valor_entrada),
                             "b": format_brl(b.valor_entrada),
                             "delta": format_brl(diff.delta_entrada)},
                            {"campo": "Parcela", "a": format_brl(a.valor_parcela),
                             "b": format_brl(b.valor_parcela),
                             "delta": format_brl(diff.delta_parcela)},
                            {"campo": "Juros totais", "a": format_brl(a.total_juros),
                             "b": format_brl(b.total_juros),
                             "delta": format_brl(diff.delta_juros_totais)},
                            {"campo": "Total pago", "a": format_brl(a.total_pago),
                             "b": format_brl(b.total_pago),
                             "delta": format_brl(diff.delta_total_pago)},
                        ],
                    )

            ui.button("Comparar", on_click=compare)

        shell(content)