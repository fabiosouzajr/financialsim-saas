"""Simulacao page - the central tab."""

from __future__ import annotations

import math
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from loguru import logger
from nicegui import app as ng_app
from nicegui import ui

from app.core.extras import Extra, ExtraModalidade
from app.data.database import get_session_factory
from app.data.models import Vehicle
from app.data.repositories import IndicatorRepository
from app.integrations.factory import build_fipe_chain
from app.services.client_service import ClientService
from app.services.rules_service import RulesService
from app.services.simulation_service import (
    SimulationInputDTO,
    SimulationService,
    SimulationServiceError,
    SimulationSummary,
)
from app.services.vehicle_service import VehicleService
from app.ui.components.fipe_picker import build_fipe_picker
from app.ui.components.charts import (
    composition_chart,
    parcela_total_chart,
    saldo_devedor_chart,
)
from app.ui.components.currency_input import CurrencyInput
from app.ui.components.kpi_card import KpiCard
from app.ui.components.percent_input import PercentInput
from app.ui.error_handler import handle_unexpected
from app.ui.layout import shell
from app.ui.router import get_logged_user_id
from app.utils.br_format import format_brl, format_pct


def build_simulacao_page(engine, data_dir: Path) -> None:
    SessionLocal = get_session_factory(engine)
    fipe_chain = build_fipe_chain(SessionLocal)

    @ui.page("/simulacao")
    def page() -> None:
        def content() -> None:
            user_id = get_logged_user_id() or 0

            with SessionLocal() as _page_session:
                entrada_minima_pct = Decimal(
                    RulesService(_page_session).get_raw("entrada_minima_pct") or "0.10"
                )
                _taxa_row = IndicatorRepository(_page_session).get_latest("TX_BACEN_VEIC")
                taxa_bacen_val: Decimal | None = _taxa_row.valor if _taxa_row else None
                clients = ClientService(_page_session).find("")

            last_sim_id: dict[str, int | None] = {"id": None}
            last_proposal_id: dict[str, int | None] = {"id": None}
            _actions: dict = {}
            selected_vehicle_id: dict[str, int | None] = {"id": None}

            # ── Load existing simulation (from /veiculos link) ────────
            _open_sim_id = ng_app.storage.user.pop("open_simulation_id", None)
            _loaded_sim: dict = {"sim": None}

            if _open_sim_id:
                from app.data.models import Simulation as _Sim
                with SessionLocal() as _s:
                    _sim = _s.get(_Sim, _open_sim_id)
                    if _sim:
                        _loaded_sim["sim"] = {
                            "valor_veiculo": _sim.valor_veiculo,
                            "valor_entrada": _sim.valor_entrada,
                            "prazo": _sim.prazo_meses,
                            "taxa": _sim.taxa_juros_mes,
                            "incluir_iof": _sim.incluir_iof,
                            "data_liberacao": _sim.data_liberacao.isoformat(),
                            "data_venc": _sim.data_primeiro_venc.isoformat(),
                            "veiculo_id": _sim.veiculo_id,
                            "codigo": _sim.codigo,
                            "cliente_id": _sim.cliente_id,
                        }

            # ── Header: title left, action buttons right ─────────────────
            with ui.row().classes("w-full items-center justify-between mb-2"):
                ui.label("Simulação").classes("text-xl font-bold text-slate-800")
                with ui.row().classes("gap-2"):
                    ui.button("Abrir", icon="folder_open",
                              on_click=lambda: _actions["abrir_sim"]()
                              ).props("color=secondary outline")
                    btn_simular = ui.button("Simular", icon="play_arrow",
                                            on_click=lambda: _actions["simular"]()
                                            ).props("color=primary")

                    with ui.row().classes("gap-2 items-center") as loaded_row:
                        _codigo = _loaded_sim["sim"]["codigo"] if _loaded_sim["sim"] else ""
                        ui.label(f"Carregado: {_codigo}").classes("text-xs text-slate-400 self-center")
                        ui.button(
                            "Nova simulação com esses dados", icon="content_copy",
                            on_click=lambda: _actions["nova_a_partir"](),
                        ).props("color=primary outline")

                    # Set initial visibility based on load mode
                    is_loaded = bool(_loaded_sim["sim"])
                    btn_simular.set_visibility(not is_loaded)
                    loaded_row.set_visibility(is_loaded)
                    ui.button("Gerar PDF", icon="picture_as_pdf",
                              on_click=lambda: _actions["gerar_pdf"]()
                              ).props("color=primary outline")
                    btn_carne = ui.button("Gerar Carnê", icon="receipt_long",
                                          on_click=lambda: _actions["gerar_carne"]()
                                          ).props("color=secondary outline")
                    btn_carne.disable()

            # ── Main layout: narrow form | wide results ───────────────────
            with ui.row().classes("w-full gap-4 items-start"):

                # ── Left: Entrada form ────────────────────────────────────
                with ui.column().classes("gap-3").style("width: 290px; flex-shrink: 0"):
                    ui.label("Entrada").classes(
                        "text-xs font-semibold text-slate-500 uppercase tracking-widest"
                    )

                    ui.label("Cliente").classes(
                        "text-xs font-semibold text-slate-500 uppercase tracking-widest"
                    )
                    _cliente_options: dict[int, str] = {0: "— sem cliente —"}
                    _cliente_options.update(
                        {c.id: f"{c.nome}  ({c.cpf_cnpj})" for c in clients}
                    )
                    cliente_sel = ui.select(
                        _cliente_options,
                        value=0,
                        label="Cliente",
                        with_input=True,
                    ).classes("w-full")

                    # ── Seção Veículo ─────────────────────────────────────────
                    ui.label("Veículo").classes(
                        "text-xs font-semibold text-slate-500 uppercase tracking-widest"
                    )

                    picker_row = ui.column().classes("w-full gap-1")
                    chips_row = ui.row().classes("gap-2 flex-wrap")
                    chips_row.set_visibility(False)
                    fipe_panel = ui.column().classes("w-full gap-2")
                    fipe_panel.set_visibility(False)

                    def _build_picker() -> None:
                        picker_row.clear()
                        with SessionLocal() as _s:
                            opts = VehicleService(_s).list_active()
                        options = {
                            v.id: (
                                f"{v.marca} {v.modelo} {v.ano_modelo}"
                                + (f" · {v.placa}" if v.placa else "")
                                + (f" · {v.cor}" if v.cor else "")
                            )
                            for v in opts
                        }
                        options[0] = "— sem veículo —"
                        with picker_row:
                            ui.select(
                                options, value=selected_vehicle_id["id"] or 0,
                                label="Veículo do estoque",
                                on_change=lambda e: _on_picker_change(e.value),
                            ).classes("w-full")

                    def _on_picker_change(vid: int) -> None:
                        if vid == 0:
                            selected_vehicle_id["id"] = None
                            chips_row.set_visibility(False)
                            return
                        selected_vehicle_id["id"] = vid
                        _show_chips(vid)

                    def _show_chips(vid: int) -> None:
                        chips_row.clear()
                        with SessionLocal() as _s:
                            v = _s.get(Vehicle, vid)
                            if v is None:
                                return
                            vf = v.valor_fipe
                            vr = v.valor_referencia
                        chips_row.set_visibility(True)
                        with chips_row:
                            if vf:
                                ui.button(
                                    f"FIPE  {format_brl(vf)}",
                                    on_click=lambda vf=vf: _set_valor_veiculo(vf),
                                ).props("outline dense no-caps color=positive size=sm")
                            if vr:
                                ui.button(
                                    f"Ref.  {format_brl(vr)}",
                                    on_click=lambda vr=vr: _set_valor_veiculo(vr),
                                ).props("outline dense no-caps color=primary size=sm")

                    def _set_valor_veiculo(val: Decimal) -> None:
                        valor_veiculo.value = val
                        if not entrada_modified["v"]:
                            valor_entrada.value = (
                                entrada_minima_pct * val
                            ).quantize(Decimal("0.01"))
                            _update_pct_label()

                    _build_picker()

                    def _toggle_fipe_panel() -> None:
                        visible = not fipe_panel.visible
                        fipe_panel.set_visibility(visible)
                        if visible:
                            fipe_panel.clear()
                            with fipe_panel:
                                def _on_vehicle_created(v) -> None:
                                    selected_vehicle_id["id"] = v.id
                                    valor_veiculo.value = v.valor_referencia
                                    fipe_panel.set_visibility(False)
                                    _build_picker()
                                    _show_chips(v.id)
                                    ui.notify("Veículo cadastrado e selecionado!", type="positive")
                                build_fipe_picker(
                                    fipe_chain, SessionLocal, user_id, _on_vehicle_created,
                                    button_label="+ Cadastrar e usar este veículo",
                                    button_icon=None,
                                )

                    ui.button(
                        "🔍 Buscar na FIPE e cadastrar",
                        on_click=_toggle_fipe_panel,
                    ).props("flat dense no-caps size=sm").classes("text-blue-600 text-xs self-start")

                    ui.separator().classes("my-1")
                    # ── fim seção Veículo ─────────────────────────────────────

                    valor_veiculo = CurrencyInput("Valor do veículo", Decimal("50000"))
                    _entrada_default = (
                        entrada_minima_pct * Decimal("50000")
                    ).quantize(Decimal("0.01"))
                    valor_entrada = CurrencyInput("Entrada (R$)", _entrada_default)
                    pct_label = ui.label("").classes("text-xs text-slate-400")
                    entrada_modified: dict[str, bool] = {"v": False}
                    prazo = ui.number(label="Prazo (meses)", value=48, min=12, max=72).classes("w-full")
                    def _annual_to_monthly(r: Decimal) -> Decimal:
                        return Decimal(str((1 + float(r)) ** (1 / 12) - 1))

                    _taxa_initial = _annual_to_monthly(taxa_bacen_val) if taxa_bacen_val is not None else Decimal("0")
                    taxa = PercentInput("Taxa mensal", _taxa_initial)
                    if taxa_bacen_val is not None:
                        bacen_hint = ui.label(
                            f"BACEN TX_VEIC: {_taxa_initial * 100:.2f}% a.m."
                        ).classes("text-xs italic text-slate-400")
                    else:
                        bacen_hint = ui.label(
                            "sem dados BACEN — informe manualmente"
                        ).classes("text-xs italic text-amber-500")
                    taxa_modified: dict[str, bool] = {"v": False}
                    incluir_iof = ui.checkbox("Incluir IOF", value=True)

                    # Custos adicionais above calendars
                    with ui.expansion("Custos adicionais").classes("w-full"):
                        protecao = CurrencyInput("Proteção veicular (R$/mês)", Decimal("0"))
                        ipva_total = CurrencyInput("IPVA anual (R$)", Decimal("0"))
                        empl_total = CurrencyInput("Emplacamento anual (R$)", Decimal("0"))

                    # Date pickers side by side (popup style)
                    ui.label("Datas").classes(
                        "text-xs font-semibold text-slate-500 uppercase tracking-widest mt-1"
                    )
                    with ui.row().classes("gap-2 w-full"):
                        with ui.column().classes("flex-1 gap-1"):
                            ui.label("Início").classes("text-xs text-slate-400 font-medium")
                            with ui.input(value=date.today().isoformat()).classes("w-full") as inp_lib:
                                with inp_lib.add_slot("append"):
                                    ui.icon("edit_calendar").on(
                                        "click", lambda: menu_lib.open()
                                    ).classes("cursor-pointer text-slate-400")
                                with ui.menu() as menu_lib:
                                    _lib_date = ui.date(
                                        mask="YYYY-MM-DD", value=date.today().isoformat()
                                    )
                                    _lib_date.bind_value(inp_lib)

                        with ui.column().classes("flex-1 gap-1"):
                            _venc_def = (date.today() + timedelta(days=30)).isoformat()
                            ui.label("Término").classes("text-xs text-slate-400 font-medium")
                            with ui.input(value=_venc_def).classes("w-full") as inp_venc:
                                with inp_venc.add_slot("append"):
                                    ui.icon("edit_calendar").on(
                                        "click", lambda: menu_venc.open()
                                    ).classes("cursor-pointer text-slate-400")
                                with ui.menu() as menu_venc:
                                    _venc_date = ui.date(mask="YYYY-MM-DD", value=_venc_def)
                                    _venc_date.bind_value(inp_venc)

                    # ── Pre-fill if loading existing simulation ────────
                    if _loaded_sim["sim"]:
                        _d = _loaded_sim["sim"]
                        valor_veiculo.value = _d["valor_veiculo"]
                        valor_entrada.value = _d["valor_entrada"]
                        prazo.set_value(_d["prazo"])
                        taxa.value = _d["taxa"]
                        incluir_iof.set_value(_d["incluir_iof"])
                        inp_lib.set_value(_d["data_liberacao"])
                        inp_venc.set_value(_d["data_venc"])
                        selected_vehicle_id["id"] = _d["veiculo_id"]
                        if _d["veiculo_id"]:
                            _build_picker()
                            _show_chips(_d["veiculo_id"])
                        cliente_sel.value = _d["cliente_id"] or 0

                # ── Right: Resultado KPIs + Charts ────────────────────────
                with ui.column().classes("flex-1 gap-3 min-w-0"):

                    # KPI cards — grouped, compact
                    ui.label("Resultado").classes(
                        "text-xs font-semibold text-slate-500 uppercase tracking-widest"
                    )

                    ui.label("Parcelas").classes("kpi-group-label")
                    with ui.row().classes("gap-2 w-full"):
                        with ui.element("div").classes("flex-1"):
                            card_parcela = KpiCard("Parcela financiamento", "R$ 0,00", compact=True)
                        with ui.element("div").classes("flex-1"):
                            card_total_apos = KpiCard("Valor da parcela", "R$ 0,00", compact=True)

                    ui.label("Financiamento").classes("kpi-group-label mt-1")
                    with ui.row().classes("gap-2 w-full"):
                        with ui.element("div").classes("flex-1"):
                            card_financiado = KpiCard("Valor financiado", "R$ 0,00", compact=True)
                        with ui.element("div").classes("flex-1"):
                            card_total_pago = KpiCard("Total pago", "R$ 0,00", compact=True)
                        with ui.element("div").classes("flex-1"):
                            card_cet = KpiCard("CET", "0,00% a.m.", compact=True)

                    # Charts — composition + saldo side by side, parcela_total full width
                    with ui.row().classes("gap-2 w-full"):
                        chart_comp = ui.plotly(composition_chart([], [], [])).classes("flex-1")
                        chart_saldo = ui.plotly(saldo_devedor_chart([])).classes("flex-1")
                    chart_total = ui.plotly(parcela_total_chart([])).classes("w-full")

            # ── Callbacks (bound after UI built via _actions) ─────────────
            def _update_pct_label() -> None:
                if valor_veiculo.value == 0:
                    pct_label.set_visibility(False)
                    return
                pct_label.set_visibility(True)
                pct = valor_entrada.value / valor_veiculo.value
                pct_label.set_text(
                    f"{pct * 100:.1f}%  (min. {entrada_minima_pct * 100:.0f}%)"
                )
                if pct < entrada_minima_pct:
                    pct_label.classes(remove="text-slate-400", add="text-amber-500")
                else:
                    pct_label.classes(remove="text-amber-500", add="text-slate-400")

            valor_veiculo.input.on("blur", lambda _: _update_pct_label())
            valor_entrada.input.on("blur", lambda _: _update_pct_label())
            valor_entrada.input.on("blur", lambda _: entrada_modified.__setitem__("v", True))
            _update_pct_label()

            taxa.input.on("blur", lambda _: taxa_modified.__setitem__("v", True))

            def _poll_bacen() -> None:
                with SessionLocal() as _s:
                    _row = IndicatorRepository(_s).get_latest("TX_BACEN_VEIC")
                    new_val: Decimal | None = _row.valor if _row else None
                if new_val is None:
                    return
                new_monthly = _annual_to_monthly(new_val)
                bacen_hint.set_text(f"BACEN TX_VEIC: {new_monthly * 100:.2f}% a.m.")
                bacen_hint.style("color: rgb(148 163 184)")
                bacen_hint.update()
                if not taxa_modified["v"]:
                    taxa.value = new_monthly
                    taxa.input.update()

            ui.timer(60, _poll_bacen)

            def simular() -> None:
                try:
                    with SessionLocal() as session:
                        if selected_vehicle_id["id"]:
                            v = session.get(Vehicle, selected_vehicle_id["id"])
                            if v is None:
                                ui.notify("Veículo selecionado não encontrado.", type="negative")
                                return
                        else:
                            # veiculo_id is required FK; placeholder stays hidden via list_active/list_all filters
                            v = Vehicle(
                                fonte="manual", tipo="carro", marca="Manual", modelo="Veiculo",
                                ano_modelo=date.today().year, combustivel="Gasolina",
                                valor_referencia=valor_veiculo.value,
                            )
                            session.add(v)
                            session.flush()

                        extras = []
                        prazo_int = int(prazo.value or 48)
                        num_anos = math.ceil(prazo_int / 12)
                        if protecao.value > 0:
                            extras.append(Extra("protecao_veicular", "Plano de protecao",
                                                protecao.value, ExtraModalidade.MENSAL_CONTINUO,
                                                prazo_int, 1))
                        if ipva_total.value > 0:
                            extras.append(Extra("ipva", "IPVA", ipva_total.value * num_anos,
                                                ExtraModalidade.RATEIO_MESES,
                                                prazo_int, 2))
                        if empl_total.value > 0:
                            extras.append(Extra("emplacamento", "Emplacamento", empl_total.value * num_anos,
                                                ExtraModalidade.RATEIO_MESES,
                                                prazo_int, 3))

                        sim = SimulationService(session).run_and_save(SimulationInputDTO(
                            criado_por=user_id,
                            cliente_id=cliente_sel.value if cliente_sel.value != 0 else None,
                            veiculo_id=v.id,
                            valor_veiculo=valor_veiculo.value, valor_entrada=valor_entrada.value,
                            prazo_meses=prazo_int, taxa_mensal=taxa.value,
                            data_liberacao=date.fromisoformat(inp_lib.value or date.today().isoformat()),
                            data_primeiro_venc=date.fromisoformat(
                                inp_venc.value or (date.today() + timedelta(days=30)).isoformat()
                            ),
                            incluir_iof=bool(incluir_iof.value), tarifas=[], extras=extras,
                        ))
                        last_sim_id["id"] = sim.id
                        session.refresh(sim)

                        from app.data.models import AmortizationRow
                        rows = (
                            session.query(AmortizationRow).filter_by(simulation_id=sim.id)
                            .order_by(AmortizationRow.numero_parcela).all()
                        )

                    card_parcela.set(format_brl(sim.valor_parcela))
                    if rows:
                        last_idx = min(12, len(rows) - 1)
                        card_total_apos.set(format_brl(rows[last_idx].parcela_total))
                    card_financiado.set(format_brl(sim.valor_financiado))
                    total_pago_cliente = (
                        sum((Decimal(str(r.parcela_total)) for r in rows), start=Decimal("0"))
                        + valor_entrada.value
                    )
                    card_total_pago.set(format_brl(total_pago_cliente))
                    card_cet.set(f"{format_pct(sim.cet_mes)} a.m.", f"{format_pct(sim.cet_ano)} a.a.")

                    juros = [Decimal(str(r.juros)) for r in rows]
                    amort = [Decimal(str(r.amortizacao)) for r in rows]
                    extras_arr = [Decimal(str(r.extras_total)) for r in rows]
                    saldos = [Decimal(str(r.saldo_devedor)) for r in rows]
                    totals = [Decimal(str(r.parcela_total)) for r in rows]
                    chart_comp.update_figure(composition_chart(juros, amort, extras_arr))
                    chart_saldo.update_figure(saldo_devedor_chart(saldos))
                    chart_total.update_figure(parcela_total_chart(totals))

                except SimulationServiceError as e:
                    for issue in e.issues:
                        ui.notify(issue.message, type="negative", timeout=0)
                except Exception as exc:
                    handle_unexpected(exc, "simular")

            def gerar_pdf() -> None:
                if last_sim_id["id"] is None:
                    ui.notify("Simule antes de gerar PDF", type="warning")
                    return
                from app.ui.pages._proposal_helper import generate_and_open_pdf
                try:
                    with SessionLocal() as session:
                        pid = generate_and_open_pdf(
                            session, last_sim_id["id"], user_id, data_dir
                        )
                    last_proposal_id["id"] = pid
                    btn_carne.enable()
                except Exception as exc:
                    logger.exception("PDF generation failed")
                    ui.notify(f"Erro ao gerar PDF: {exc}", type="negative")

            def gerar_carne() -> None:
                if last_proposal_id["id"] is None:
                    ui.notify("Gere o PDF da proposta antes de gerar o carnê", type="warning")
                    return
                from app.ui.pages._proposal_helper import generate_and_open_carne
                try:
                    with SessionLocal() as session:
                        generate_and_open_carne(
                            session, last_proposal_id["id"], data_dir
                        )
                except Exception as exc:
                    logger.exception("Carne generation failed")
                    ui.notify(f"Erro ao gerar carnê: {exc}", type="negative")

            def nova_a_partir() -> None:
                _loaded_sim["sim"] = None
                loaded_row.set_visibility(False)
                btn_simular.set_visibility(True)
                ui.notify(
                    "Dados carregados. Ajuste o que quiser e clique em Simular.",
                    type="info",
                )

            def abrir_sim() -> None:
                with SessionLocal() as _s:
                    summaries = SimulationService(_s).find_recent()

                dlg = ui.dialog()
                with dlg, ui.card().classes("w-full max-w-3xl"):
                    with ui.row().classes("w-full items-center justify-between mb-2"):
                        ui.label("Abrir simulação").classes("text-lg font-bold")
                        ui.button(icon="close", on_click=dlg.close).props("flat round dense")
                    with ui.row().classes(
                        "w-full border-b pb-1 text-xs font-semibold text-slate-500 uppercase"
                    ):
                        ui.label("Código").classes("w-32")
                        ui.label("Veículo").classes("flex-1")
                        ui.label("Cliente").classes("w-40")
                        ui.label("Valor").classes("w-28 text-right")
                        ui.label("Prazo").classes("w-16 text-right")
                        ui.label("Data").classes("w-24")

                    def _do_load(s: SimulationSummary) -> None:
                        valor_veiculo.value = s.valor_veiculo
                        valor_entrada.value = s.valor_entrada
                        prazo.set_value(s.prazo_meses)
                        taxa.value = s.taxa_juros_mes
                        incluir_iof.set_value(s.incluir_iof)
                        inp_lib.set_value(s.data_liberacao.isoformat())
                        inp_venc.set_value(s.data_primeiro_venc.isoformat())
                        selected_vehicle_id["id"] = s.veiculo_id
                        if s.veiculo_id:
                            _build_picker()
                            _show_chips(s.veiculo_id)
                        cliente_sel.value = s.cliente_id or 0
                        last_sim_id["id"] = None
                        last_proposal_id["id"] = None
                        btn_carne.disable()
                        loaded_row.set_visibility(False)
                        btn_simular.set_visibility(True)
                        dlg.close()
                        ui.notify(f"Simulação {s.codigo} carregada", type="positive")

                    with ui.scroll_area().classes("h-96 w-full"):
                        if not summaries:
                            ui.label("Nenhuma simulação encontrada.").classes(
                                "text-sm text-slate-400 p-4"
                            )
                        for s in summaries:
                            with ui.row().classes(
                                "w-full border-b py-2 cursor-pointer hover:bg-slate-50 items-center"
                            ).on("click", lambda s=s: _do_load(s)):
                                ui.label(s.codigo).classes("w-32 text-sm font-mono")
                                ui.label(s.veiculo_label).classes("flex-1 text-sm")
                                ui.label(s.cliente_nome).classes("w-40 text-sm")
                                ui.label(format_brl(s.valor_veiculo)).classes("w-28 text-sm text-right")
                                ui.label(f"{s.prazo_meses}x").classes("w-16 text-sm text-right")
                                ui.label(s.criado_em.strftime("%d/%m/%Y")).classes("w-24 text-sm text-slate-400")
                    ui.button("Fechar", on_click=dlg.close).props("flat").classes("mt-2")
                dlg.open()

            _actions["simular"] = simular
            _actions["abrir_sim"] = abrir_sim
            _actions["gerar_pdf"] = gerar_pdf
            _actions["gerar_carne"] = gerar_carne
            _actions["nova_a_partir"] = nova_a_partir

        shell(content)
