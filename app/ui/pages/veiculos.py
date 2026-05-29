# app/ui/pages/veiculos.py
"""Vehicle registry page."""
from __future__ import annotations

from decimal import Decimal
from nicegui import app as ng_app, ui

from app.data.database import get_session_factory
from app.integrations.factory import build_fipe_chain
from app.services.vehicle_service import VehicleService, VehicleServiceError
from app.ui.components.fipe_picker import build_fipe_picker
from app.ui.error_handler import handle_unexpected
from app.ui.layout import shell
from app.ui.router import get_logged_user_id
from app.utils.br_format import format_brl


_STATUS_STYLE = {
    "disponivel": ("background:#dcfce7;color:#166534", "Disponível"),
    "reservado":  ("background:#fef9c3;color:#854d0e", "Reservado"),
    "vendido":    ("background:#f1f5f9;color:#94a3b8",  "Vendido"),
}


def build_veiculos_page(engine) -> None:
    SessionLocal = get_session_factory(engine)
    chain = build_fipe_chain(SessionLocal)

    @ui.page("/veiculos")
    def page() -> None:
        def content() -> None:
            user_id = get_logged_user_id() or 0

            # State refs
            selected_id: dict[str, int | None] = {"id": None}
            # Tracks current panel mode; read in Tasks 7/8 to distinguish view/create/edit
            panel_mode: dict[str, str] = {"v": "hidden"}

            # ── Header ────────────────────────────────────────────────
            with ui.row().classes("w-full items-center justify-between mb-2"):
                ui.label("Veículos").classes("text-xl font-bold text-slate-800")
                ui.button("+ Novo Veículo", icon="add",
                          on_click=lambda: _show_panel("create")
                          ).props("color=primary")

            # ── Filters ───────────────────────────────────────────────
            with ui.row().classes("w-full gap-3 mb-3"):
                search_inp = ui.input(
                    placeholder="Buscar marca, modelo, placa, cor...",
                    on_change=lambda: _refresh_table(),
                ).classes("flex-1")
                status_sel = ui.select(
                    {"": "Todos", "disponivel": "Disponível",
                     "reservado": "Reservado", "vendido": "Vendido"},
                    value="",
                    on_change=lambda: _refresh_table(),
                ).classes("w-44")

            # ── Split layout ──────────────────────────────────────────
            with ui.row().classes("w-full gap-4 items-start"):

                # Left: table
                with ui.column().classes("gap-0").style("flex: 0 0 58%; min-width: 0"):
                    table_wrap = ui.column().classes("w-full")

                # Right: panel (initially hidden)
                with ui.column().classes("gap-3").style(
                    "flex: 1; border-left: 3px solid #3b82f6; "
                    "padding-left: 16px; min-width: 0"
                ) as panel_col:
                    panel_col.set_visibility(False)

                    # Panel header
                    with ui.row().classes("w-full items-center justify-between"):
                        panel_title = ui.label("").classes("font-bold text-slate-800")
                        with ui.row().classes("gap-2"):
                            btn_edit = ui.button("Editar", icon="edit",
                                                 on_click=lambda: _show_panel_edit()
                                                 ).props("flat dense color=primary size=sm")
                            btn_save = ui.button("Salvar", icon="save",
                                                 on_click=lambda: _save_edit()
                                                 ).props("color=primary dense size=sm")
                            btn_save.set_visibility(False)

                    # View/edit fields
                    panel_body = ui.column().classes("w-full gap-2")

                    # Simulations section
                    sims_section = ui.column().classes("w-full gap-1 mt-2")

            # ── Helpers ───────────────────────────────────────────────
            def _refresh_table() -> None:
                table_wrap.clear()
                sf = status_sel.value or None
                with SessionLocal() as session:
                    svc = VehicleService(session)
                    rows = svc.list_all(status_filter=sf, search=search_inp.value or "")
                with table_wrap:
                    if not rows:
                        ui.label("Nenhum veículo encontrado.").classes("text-slate-400 text-sm")
                        return
                    with ui.element("table").classes("w-full text-sm border-collapse"):
                        with ui.element("thead"):
                            with ui.element("tr").classes("bg-slate-100"):
                                for h in ("Modelo", "Placa", "Cor", "Valor Ref.", "Status"):
                                    with ui.element("th").classes(
                                        "px-3 py-2 text-left text-xs font-semibold text-slate-500 uppercase"
                                    ):
                                        ui.label(h)
                        with ui.element("tbody"):
                            for v in rows:
                                style = "cursor:pointer;"
                                if v.status == "vendido":
                                    style += "opacity:0.5;"
                                if selected_id["id"] == v.id:
                                    style += "background:#eff6ff;"
                                with ui.element("tr").classes("border-b border-slate-100").style(style).on(
                                    "click", lambda vid=v.id: _select_vehicle(vid)
                                ):
                                    row_label = f"{v.marca} {v.modelo} {v.ano_modelo}"
                                    with ui.element("td").classes("px-3 py-2 font-medium"):
                                        ui.label(row_label)
                                    with ui.element("td").classes("px-3 py-2"):
                                        ui.label(v.placa or "—")
                                    with ui.element("td").classes("px-3 py-2"):
                                        ui.label(v.cor or "—")
                                    with ui.element("td").classes("px-3 py-2 text-right"):
                                        ui.label(format_brl(Decimal(str(v.valor_referencia))))
                                    s_style, s_label = _STATUS_STYLE.get(v.status, ("", v.status))
                                    with ui.element("td").classes("px-3 py-2 text-center"):
                                        ui.label(s_label).style(
                                            f"{s_style};padding:2px 8px;border-radius:8px;font-size:11px"
                                        )

            def _select_vehicle(vid: int) -> None:
                selected_id["id"] = vid
                panel_mode["v"] = "view"
                _refresh_table()
                _render_panel(vid)
                panel_col.set_visibility(True)

            def _show_panel(mode: str) -> None:
                panel_mode["v"] = mode
                if mode == "create":
                    selected_id["id"] = None
                    _render_create_panel()
                    panel_col.set_visibility(True)

            def _render_panel(vid: int) -> None:
                from app.data.models import Vehicle as _V
                panel_body.clear()
                sims_section.clear()
                with SessionLocal() as session:
                    svc = VehicleService(session)
                    v = session.get(_V, vid)
                    sims = svc.get_simulations(vid)
                    if v:
                        v_data = {
                            "marca": v.marca, "modelo": v.modelo,
                            "ano_modelo": v.ano_modelo, "combustivel": v.combustivel,
                            "codigo_fipe": v.codigo_fipe, "fonte": v.fonte,
                            "valor_fipe": v.valor_fipe, "valor_referencia": v.valor_referencia,
                            "cor": v.cor, "placa": v.placa, "odometro_km": v.odometro_km,
                            "mes_referencia_fipe": v.mes_referencia_fipe, "status": v.status,
                        }
                    else:
                        v_data = None

                if v_data is None:
                    return

                panel_title.text = f"{v_data['marca']} {v_data['modelo']} {v_data['ano_modelo']}"
                btn_edit.set_visibility(True)
                btn_save.set_visibility(False)

                with panel_body:
                    # Status selector
                    with ui.row().classes("items-center gap-2"):
                        ui.label("Status:").classes("text-xs text-slate-500")
                        ui.select(
                            {"disponivel": "Disponível", "reservado": "Reservado", "vendido": "Vendido"},
                            value=v_data["status"],
                            on_change=lambda e, vid=vid: _change_status(vid, e.value),
                        ).classes("w-36").props("dense outlined")

                    # Data grid
                    with ui.element("div").classes(
                        "grid gap-x-4 gap-y-1 text-sm"
                    ).style("grid-template-columns: auto 1fr auto 1fr"):
                        _fipe = v_data["valor_fipe"]
                        _ref = v_data["valor_referencia"]
                        _odo = v_data["odometro_km"]
                        for field_label, val in [
                            ("FIPE", format_brl(Decimal(str(_fipe))) if _fipe is not None else "—"),
                            ("Referência", format_brl(Decimal(str(_ref))) if _ref is not None else "—"),
                            ("Cor", v_data["cor"] or "—"),
                            ("Placa", v_data["placa"] or "—"),
                            ("Odômetro", f"{int(_odo):,} km".replace(",", ".") if _odo else "—"),
                            ("Mês ref.", v_data["mes_referencia_fipe"] or "—"),
                            ("Cód. FIPE", v_data["codigo_fipe"] or "—"),
                            ("Fonte", str(v_data["fonte"]) if v_data["fonte"] else "—"),
                        ]:
                            ui.label(field_label).classes("text-slate-400 text-xs")
                            ui.label(str(val)).classes("text-slate-700 text-xs")

                # Simulations
                with sims_section:
                    if sims:
                        ui.label("Simulações vinculadas").classes(
                            "text-xs font-semibold text-slate-500 uppercase tracking-wider mt-2"
                        )
                        for sim in sims:
                            line = (
                                f"{sim.codigo} · {format_brl(sim.valor_veiculo)} · "
                                f"{sim.prazo_meses}x · {sim.criado_em.strftime('%d/%m/%Y')}"
                            )
                            ui.button(line, on_click=lambda sid=sim.id: _open_simulation(sid)).props(
                                "flat dense no-caps align=left"
                            ).classes("text-blue-600 text-xs w-full justify-start")

            def _change_status(vid: int, status: str) -> None:
                with SessionLocal() as session:
                    try:
                        VehicleService(session).set_status(vid, status, usuario_id=user_id)
                        ui.notify(f"Status atualizado: {status}", type="positive")
                    except VehicleServiceError as e:
                        ui.notify(str(e), type="negative")
                _refresh_table()

            def _open_simulation(sim_id: int) -> None:
                ng_app.storage.user["open_simulation_id"] = sim_id
                ui.navigate.to("/simulacao")

            def _render_create_panel() -> None:
                panel_body.clear()
                sims_section.clear()
                panel_title.text = "Novo Veículo"
                btn_edit.set_visibility(False)
                btn_save.set_visibility(False)

                with panel_body:
                    with ui.tabs().classes("w-full") as tabs:
                        tab_fipe = ui.tab("FIPE", icon="search")
                        tab_manual = ui.tab("Manual", icon="edit_note")

                    with ui.tab_panels(tabs, value=tab_fipe).classes("w-full"):

                        # ── FIPE tab ──────────────────────────────────
                        with ui.tab_panel(tab_fipe):
                            def _on_vehicle_created(_v) -> None:
                                ui.notify("Veículo cadastrado!", type="positive")
                                panel_col.set_visibility(False)
                                _refresh_table()
                            build_fipe_picker(chain, SessionLocal, user_id, _on_vehicle_created)

                        # ── Manual tab ────────────────────────────────
                        with ui.tab_panel(tab_manual):
                            m_tipo = ui.select(["carro", "moto", "caminhao"], label="Tipo", value="carro").classes("w-full")
                            m_marca = ui.input(label="Marca").classes("w-full")
                            m_modelo = ui.input(label="Modelo").classes("w-full")
                            m_ano = ui.number(label="Ano modelo", value=2024, min=1960, max=2030).classes("w-full")
                            m_comb = ui.input(label="Combustível", value="Gasolina").classes("w-full")
                            m_cor = ui.input(label="Cor").classes("w-full")
                            m_placa = ui.input(label="Placa (ex: ABC1234)").classes("w-full")
                            m_km = ui.number(label="Odômetro (km)", min=0).classes("w-full")
                            from app.ui.components.currency_input import CurrencyInput as _CI
                            m_ref = _CI("Valor de referência (R$)", Decimal("0"))

                            def _salvar_manual() -> None:
                                if not m_marca.value or not m_modelo.value:
                                    ui.notify("Marca e modelo são obrigatórios.", type="warning")
                                    return
                                with SessionLocal() as session:
                                    svc = VehicleService(session)
                                    try:
                                        svc.create_manual(
                                            tipo=m_tipo.value,
                                            marca=m_marca.value,
                                            modelo=m_modelo.value,
                                            ano_modelo=int(m_ano.value or 2024),
                                            combustivel=m_comb.value or "Gasolina",
                                            valor_referencia=m_ref.value,
                                            cor=m_cor.value or None,
                                            placa=m_placa.value or None,
                                            odometro_km=int(m_km.value) if m_km.value else None,
                                            criado_por=user_id,
                                        )
                                        ui.notify("Veículo cadastrado!", type="positive")
                                        panel_col.set_visibility(False)
                                        _refresh_table()
                                    except VehicleServiceError as e:
                                        ui.notify(str(e), type="negative")
                                    except Exception as exc:
                                        handle_unexpected(exc, "veiculos.salvar_manual")

                            ui.button("Salvar veículo", icon="save",
                                      on_click=_salvar_manual).props("color=primary").classes("w-full mt-2")

            # Holds edit-mode input widget refs for _save_edit to read
            _edit_inputs: dict = {}

            def _show_panel_edit() -> None:
                vid = selected_id["id"]
                if vid is None:
                    return
                panel_mode["v"] = "edit"
                panel_body.clear()
                sims_section.clear()
                btn_edit.set_visibility(False)
                btn_save.set_visibility(True)

                from app.data.models import Vehicle as _V
                from app.ui.components.currency_input import CurrencyInput
                with SessionLocal() as session:
                    v = session.get(_V, vid)
                    if v is None:
                        return
                    v_snap = {
                        "marca": v.marca, "modelo": v.modelo, "ano_modelo": v.ano_modelo,
                        "combustivel": v.combustivel, "codigo_fipe": v.codigo_fipe,
                        "valor_fipe": v.valor_fipe,
                        "cor": v.cor or "", "placa": v.placa or "",
                        "odometro_km": v.odometro_km or 0,
                        "valor_referencia": v.valor_referencia,
                    }

                panel_title.text = f"Editar — {v_snap['marca']} {v_snap['modelo']} {v_snap['ano_modelo']}"

                with panel_body:
                    ui.label("Dados FIPE (não editáveis)").classes(
                        "text-xs text-slate-400 uppercase tracking-wider"
                    )
                    for lbl, val in [
                        ("Marca/Modelo", f"{v_snap['marca']} {v_snap['modelo']} {v_snap['ano_modelo']}"),
                        ("Combustível", v_snap["combustivel"]),
                        ("Cód. FIPE", v_snap["codigo_fipe"] or "—"),
                        ("FIPE", format_brl(v_snap["valor_fipe"]) if v_snap["valor_fipe"] else "—"),
                    ]:
                        with ui.row().classes("gap-2 items-center"):
                            ui.label(f"{lbl}:").classes("text-xs text-slate-400 w-24")
                            ui.label(val).classes("text-xs text-slate-700")

                    ui.separator()
                    ui.label("Dados físicos").classes(
                        "text-xs text-slate-400 uppercase tracking-wider"
                    )
                    _edit_inputs["cor"] = ui.input(label="Cor", value=v_snap["cor"]).classes("w-full")
                    _edit_inputs["placa"] = ui.input(
                        label="Placa (ex: ABC1234)", value=v_snap["placa"]
                    ).classes("w-full")
                    _edit_inputs["odometro_km"] = ui.number(
                        label="Odômetro (km)", value=v_snap["odometro_km"], min=0
                    ).classes("w-full")
                    _edit_inputs["valor_referencia"] = CurrencyInput(
                        "Valor de referência (R$)", v_snap["valor_referencia"]
                    )

            def _save_edit() -> None:
                vid = selected_id["id"]
                if vid is None:
                    return
                cor_val = _edit_inputs.get("cor")
                placa_val = _edit_inputs.get("placa")
                km_val = _edit_inputs.get("odometro_km")
                ref_val = _edit_inputs.get("valor_referencia")
                fields = {
                    "cor": cor_val.value if cor_val else None,
                    "placa": placa_val.value if placa_val else None,
                    "odometro_km": int(km_val.value) if km_val and km_val.value else None,
                    "valor_referencia": ref_val.value if ref_val else None,
                }
                # Remove None values except cor (empty string → None is fine)
                fields = {k: v for k, v in fields.items() if v is not None}
                with SessionLocal() as session:
                    try:
                        VehicleService(session).update(vid, fields, usuario_id=user_id)
                        ui.notify("Veículo atualizado!", type="positive")
                    except VehicleServiceError as e:
                        ui.notify(str(e), type="negative")
                        return
                    except Exception as exc:
                        handle_unexpected(exc, "veiculos.save_edit")
                        return
                _select_vehicle(vid)

            # Initial load
            _refresh_table()

        shell(content)
