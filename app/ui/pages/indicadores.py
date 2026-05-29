"""Indicadores economicos page."""

from __future__ import annotations

from datetime import date, timedelta

from nicegui import ui

from app.data.database import get_session_factory
from app.data.repositories import IndicatorRepository
from app.integrations.factory import build_bacen_chain
from app.services.indicators_service import IndicatorsService
from app.ui.components.kpi_card import KpiCard
from app.ui.layout import shell
from app.utils.br_format import format_date_br, format_pct


CODIGOS = ["SELIC_META", "CDI", "IPCA", "TX_BACEN_VEIC"]


def build_indicadores_page(engine) -> None:
    SessionLocal = get_session_factory(engine)
    chain = build_bacen_chain(SessionLocal)

    @ui.page("/indicadores")
    def page() -> None:
        def content() -> None:
            with ui.row().classes("w-full items-center justify-between mb-2"):
                ui.label("Indicadores").classes("text-xl font-bold text-slate-800")
                status = ui.label("").classes("text-sm text-slate-500")

                async def update_all() -> None:
                    status.text = "Atualizando..."
                    status.update()
                    svc = IndicatorsService(SessionLocal, chain)
                    today = date.today()
                    inicio = today - timedelta(days=90)
                    for cod in CODIGOS:
                        await svc.update_indicator(cod, inicio, today)
                    status.text = "Atualizado"
                    status.update()
                    ui.navigate.reload()

                ui.button("Atualizar", icon="refresh", on_click=update_all).props("color=primary outline dense")

            with ui.row().classes("w-full gap-4"):
                with SessionLocal() as session:
                    repo = IndicatorRepository(session)
                    for codigo in CODIGOS:
                        row = repo.get_latest(codigo)
                        if row:
                            KpiCard(codigo, format_pct(row.valor),
                                    f"em {format_date_br(row.data_referencia)} ({row.fonte})")
                        else:
                            KpiCard(codigo, "n/d", "sem coleta")

        shell(content)
