"""Amortization table NiceGUI component (built from AmortizationRow rows)."""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from nicegui import ui

from app.utils.br_format import format_brl, format_date_br


def amortization_table(rows: Sequence) -> None:
    columns = [
        {"name": "n", "label": "#", "field": "n"},
        {"name": "venc", "label": "Vencimento", "field": "venc"},
        {"name": "juros", "label": "Juros", "field": "juros"},
        {"name": "amort", "label": "Amortizacao", "field": "amort"},
        {"name": "parcela", "label": "Parcela", "field": "parcela"},
        {"name": "extras", "label": "Extras", "field": "extras"},
        {"name": "total", "label": "Parcela total", "field": "total"},
        {"name": "saldo", "label": "Saldo devedor", "field": "saldo"},
    ]
    data = [
        {
            "n": r.numero_parcela,
            "venc": format_date_br(r.data_vencimento),
            "juros": format_brl(Decimal(str(r.juros))),
            "amort": format_brl(Decimal(str(r.amortizacao))),
            "parcela": format_brl(Decimal(str(r.parcela))),
            "extras": format_brl(Decimal(str(r.extras_total))),
            "total": format_brl(Decimal(str(r.parcela_total))),
            "saldo": format_brl(Decimal(str(r.saldo_devedor))),
        }
        for r in rows
    ]
    ui.table(columns=columns, rows=data, row_key="n").classes("w-full")