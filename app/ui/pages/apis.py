"""APIs page - provider health + manual refresh."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

from nicegui import ui

from app.data.database import get_session_factory
from app.integrations.factory import build_bacen_chain
from app.services.indicators_service import IndicatorsService
from app.ui.layout import shell


def build_apis_page(engine) -> None:
    SessionLocal = get_session_factory(engine)
    chain = build_bacen_chain(SessionLocal)

    @ui.page("/apis")
    def page() -> None:
        def content() -> None:
            status = ui.label("Pronto")

            async def update_all() -> None:
                status.text = "Atualizando..."
                status.update()
                svc = IndicatorsService(SessionLocal, chain)
                today = date.today()
                inicio = today - timedelta(days=90)
                for cod in ["SELIC_META", "CDI", "IPCA", "TX_BACEN_VEIC"]:
                    await svc.update_indicator(cod, inicio, today)
                status.text = "Indicadores atualizados"
                status.update()

            ui.button("Atualizar indicadores agora", on_click=update_all)

        shell(content)