"""Dashboard page."""

from __future__ import annotations

from decimal import Decimal

from nicegui import ui

from app.data.database import get_session_factory
from app.data.models import Simulation
from app.ui.components.kpi_card import KpiCard
from app.ui.layout import shell
from app.ui.router import get_logged_user_id
from app.utils.br_format import format_brl


def build_dashboard_page(engine) -> None:
    SessionLocal = get_session_factory(engine)

    @ui.page("/dashboard")
    def page() -> None:
        def content() -> None:
            with SessionLocal() as session:
                sims = session.query(Simulation).order_by(Simulation.criado_em.desc()).limit(10).all()
                count = len(sims)
                ticket_medio = (sum((s.valor_financiado for s in sims), start=Decimal("0")) / count) if count else Decimal("0")
                taxa_media = (sum((s.taxa_juros_mes for s in sims), start=Decimal("0")) / count) if count else Decimal("0")

            with ui.row().classes("w-full gap-4"):
                KpiCard("Simulacoes", str(count))
                KpiCard("Ticket medio", format_brl(ticket_medio))
                KpiCard("Taxa media a.m.", f"{taxa_media * 100:.2f}%")
            ui.label("Simulacoes recentes").classes("text-lg mt-6")
            ui.table(columns=[
                {"name": "codigo", "label": "Codigo", "field": "codigo"},
                {"name": "veiculo", "label": "Veiculo", "field": "veiculo"},
                {"name": "valor", "label": "Financiado", "field": "valor"},
                {"name": "parcela", "label": "Parcela", "field": "parcela"},
            ], rows=[
                {
                    "codigo": s.codigo,
                    "veiculo": str(s.veiculo_id),
                    "valor": format_brl(s.valor_financiado),
                    "parcela": format_brl(s.valor_parcela),
                } for s in sims
            ])

        shell(content)