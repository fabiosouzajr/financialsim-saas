"""FIPE cascade picker — tipo→marca→modelo→ano→price, then saves vehicle."""
from __future__ import annotations

from decimal import Decimal
from typing import Callable

from nicegui import ui

from app.data.models import Vehicle
from app.services.vehicle_service import VehicleService, VehicleServiceError
from app.ui.components.currency_input import CurrencyInput
from app.ui.error_handler import handle_unexpected
from app.utils.br_format import format_brl


def build_fipe_picker(
    chain,
    session_local,
    user_id: int,
    on_vehicle_created: Callable[[Vehicle], None],
    *,
    button_label: str = "Salvar veículo",
    button_icon: str | None = "save",
) -> None:
    """Render the FIPE cascade and vehicle creation form.

    Loads brands on mount. Calls on_vehicle_created(vehicle) after a successful save.
    """
    status = ui.label("").classes("text-xs text-slate-400")
    quote: dict = {"q": None}

    async def _load_brands(_=None) -> None:
        status.text = "Buscando marcas..."
        r = await chain.fetch({"action": "brands", "tipo": tipo_sel.value})
        if not r.is_ok:
            ui.notify(f"Erro: {r.error}", type="negative")
            return
        marca_sel.options = {b["id"]: b["nome"] for b in r.value}
        marca_sel.value = None
        modelo_sel.options = {}
        modelo_sel.value = None
        ano_sel.options = {}
        ano_sel.value = None
        quote["q"] = None
        result_box.set_visibility(False)
        marca_sel.update()
        status.text = f"{len(r.value)} marcas"

    async def _load_models(_=None) -> None:
        if not marca_sel.value:
            return
        status.text = "Buscando modelos..."
        r = await chain.fetch({
            "action": "models", "tipo": tipo_sel.value,
            "brand_id": marca_sel.value,
        })
        if not r.is_ok:
            ui.notify(f"Erro: {r.error}", type="negative")
            return
        modelo_sel.options = {m["id"]: m["nome"] for m in r.value}
        modelo_sel.value = None
        ano_sel.options = {}
        ano_sel.value = None
        modelo_sel.update()
        status.text = f"{len(r.value)} modelos"

    async def _load_years(_=None) -> None:
        if not modelo_sel.value:
            return
        status.text = "Buscando anos..."
        r = await chain.fetch({
            "action": "years", "tipo": tipo_sel.value,
            "brand_id": marca_sel.value, "model_id": modelo_sel.value,
        })
        if not r.is_ok:
            ui.notify(f"Erro: {r.error}", type="negative")
            return
        ano_sel.options = {y["id"]: y["nome"] for y in r.value}
        ano_sel.value = None
        ano_sel.update()
        status.text = f"{len(r.value)} anos"

    async def _get_price(_=None) -> None:
        if not ano_sel.value:
            return
        status.text = "Buscando preço..."
        r = await chain.fetch({
            "action": "price", "tipo": tipo_sel.value,
            "brand_id": marca_sel.value, "model_id": modelo_sel.value,
            "year_id": ano_sel.value,
        })
        if not r.is_ok:
            ui.notify(f"Erro: {r.error}", type="negative")
            return
        q = r.value
        quote["q"] = q
        result_box.set_visibility(True)
        result_label.text = (
            f"{q.marca} {q.modelo} {q.ano_modelo} · {q.combustivel} · "
            f"FIPE: {format_brl(q.valor)} · {q.mes_referencia}"
        )
        ref_inp.value = q.valor
        status.text = "Pronto"

    tipo_sel = ui.select(
        ["carro", "moto", "caminhao"], label="Tipo", value="carro",
        on_change=_load_brands,
    ).classes("w-full")
    marca_sel = ui.select({}, label="Marca", on_change=_load_models).classes("w-full")
    modelo_sel = ui.select({}, label="Modelo", on_change=_load_years).classes("w-full")
    ano_sel = ui.select({}, label="Ano / Combustível", on_change=_get_price).classes("w-full")

    with ui.column().classes("w-full gap-2 mt-2") as result_box:
        result_box.set_visibility(False)
        result_label = ui.label("").classes("text-xs text-slate-600 font-medium")
        cor_inp = ui.input(label="Cor").classes("w-full")
        placa_inp = ui.input(label="Placa (ex: ABC1234)").classes("w-full")
        km_inp = ui.number(label="Odômetro (km)", min=0).classes("w-full")
        ref_inp = CurrencyInput("Valor de referência (R$)", Decimal("0"))

        def _save() -> None:
            q = quote["q"]
            if q is None:
                return
            with session_local() as session:
                try:
                    v = VehicleService(session).create_from_fipe(
                        quote=q,
                        cor=cor_inp.value or None,
                        placa=placa_inp.value or None,
                        odometro_km=int(km_inp.value) if km_inp.value else None,
                        valor_referencia=ref_inp.value,
                        criado_por=user_id,
                    )
                    on_vehicle_created(v)
                except VehicleServiceError as e:
                    ui.notify(str(e), type="negative")
                except Exception as exc:
                    handle_unexpected(exc, "fipe_picker.save")

        ui.button(button_label, icon=button_icon, on_click=_save).props("color=primary").classes("w-full")

    ui.timer(0, _load_brands, once=True)
