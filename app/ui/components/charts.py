"""Plotly chart factories for the simulation UI."""

from __future__ import annotations

from decimal import Decimal

import plotly.graph_objects as go


def composition_chart(
    juros: list[Decimal], amort: list[Decimal], extras: list[Decimal],
) -> go.Figure:
    n = list(range(1, len(juros) + 1))
    fig = go.Figure()
    fig.add_bar(name="Juros", x=n, y=[float(x) for x in juros], marker_color="#FB8C00")
    fig.add_bar(name="Amortizacao", x=n, y=[float(x) for x in amort], marker_color="#43A047")
    fig.add_bar(name="Extras", x=n, y=[float(x) for x in extras], marker_color="#26A69A")
    fig.update_layout(barmode="stack", height=240, margin=dict(l=10, r=10, t=30, b=10),
                      title="Composicao da parcela", legend=dict(orientation="h"))
    return fig


def saldo_devedor_chart(saldos: list[Decimal]) -> go.Figure:
    n = list(range(1, len(saldos) + 1))
    fig = go.Figure()
    fig.add_scatter(x=n, y=[float(s) for s in saldos], mode="lines+markers", name="Saldo")
    fig.update_layout(height=220, margin=dict(l=10, r=10, t=30, b=10),
                      title="Saldo devedor mes a mes")
    return fig


def parcela_total_chart(parcelas_total: list[Decimal]) -> go.Figure:
    n = list(range(1, len(parcelas_total) + 1))
    fig = go.Figure()
    fig.add_scatter(x=n, y=[float(p) for p in parcelas_total], mode="lines+markers",
                    name="Parcela total")
    fig.update_layout(height=200, margin=dict(l=10, r=10, t=30, b=10),
                      title="Parcela total (com extras)")
    return fig


def comparison_saldo_chart(saldos_a: list[Decimal], saldos_b: list[Decimal]) -> go.Figure:
    fig = go.Figure()
    fig.add_scatter(x=list(range(1, len(saldos_a) + 1)), y=[float(s) for s in saldos_a],
                    name="A", mode="lines")
    fig.add_scatter(x=list(range(1, len(saldos_b) + 1)), y=[float(s) for s in saldos_b],
                    name="B", mode="lines")
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=30, b=10),
                      title="Saldo devedor: A vs B")
    return fig