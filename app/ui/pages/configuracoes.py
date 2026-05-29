"""Configuracoes - edit business_rules."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from nicegui import ui

from app.data.database import get_session_factory
from app.services.rules_service import RulesService
from app.ui.components.currency_input import CurrencyInput
from app.ui.components.percent_input import PercentInput
from app.ui.layout import shell
from app.ui.router import get_logged_user_id

EDITABLE_KEYS = [
    "nome_loja", "cnpj_loja", "endereco_loja", "telefone_loja",
    "entrada_minima_pct", "prazo_minimo_meses", "prazo_maximo_meses",
    "taxa_minima_mes", "taxa_maxima_mes", "dias_max_carencia",
    "valor_minimo_financiado", "incluir_iof_default",
    "iof_fixo_pct", "iof_diario_pct", "iof_diario_max_dias",
    "rateio_ipva_meses_default", "rateio_emplacamento_meses_default",
    "backup_diario_horario", "update_indicadores_horario",
    "fipe_cache_listas_ttl_dias", "fipe_cache_preco_ttl_horas",
]

LABEL_MAP: dict[str, str] = {
    "nome_loja":                         "Nome da loja",
    "cnpj_loja":                         "CNPJ da loja",
    "endereco_loja":                     "Endereço da loja",
    "telefone_loja":                     "Telefone da loja",
    "entrada_minima_pct":                "Entrada mínima",
    "prazo_minimo_meses":                "Prazo mínimo (meses)",
    "prazo_maximo_meses":                "Prazo máximo (meses)",
    "taxa_minima_mes":                   "Taxa mínima ao mês",
    "taxa_maxima_mes":                   "Taxa máxima ao mês",
    "dias_max_carencia":                 "Carência máxima (dias)",
    "valor_minimo_financiado":           "Valor mínimo financiado (R$)",
    "incluir_iof_default":               "Incluir IOF por padrão",
    "iof_fixo_pct":                      "IOF fixo",
    "iof_diario_pct":                    "IOF diário",
    "iof_diario_max_dias":               "IOF diário — máx. dias",
    "rateio_ipva_meses_default":         "Rateio IPVA (meses padrão)",
    "rateio_emplacamento_meses_default": "Rateio emplacamento (meses padrão)",
    "backup_diario_horario":             "Horário do backup diário",
    "update_indicadores_horario":        "Horário de atualização de indicadores",
    "fipe_cache_listas_ttl_dias":        "Cache FIPE — listas (dias)",
    "fipe_cache_preco_ttl_horas":        "Cache FIPE — preço (horas)",
}

PCT_KEYS = {
    "entrada_minima_pct", "taxa_minima_mes", "taxa_maxima_mes",
    "iof_fixo_pct", "iof_diario_pct",
}
BOOL_KEYS = {"incluir_iof_default"}
INT_KEYS = {
    "prazo_minimo_meses", "prazo_maximo_meses", "dias_max_carencia",
    "iof_diario_max_dias", "rateio_ipva_meses_default",
    "rateio_emplacamento_meses_default",
    "fipe_cache_listas_ttl_dias", "fipe_cache_preco_ttl_horas",
}
CURRENCY_KEYS = {"valor_minimo_financiado"}
# backup_diario_horario, update_indicadores_horario → plain ui.input

GROUPS = [
    ("Dados da Loja", True, [
        "nome_loja", "cnpj_loja", "endereco_loja", "telefone_loja",
    ]),
    ("Financiamento", True, [
        "entrada_minima_pct", "prazo_minimo_meses", "prazo_maximo_meses",
        "taxa_minima_mes", "taxa_maxima_mes", "dias_max_carencia",
        "valor_minimo_financiado",
    ]),
    ("IOF", True, [
        "incluir_iof_default", "iof_fixo_pct", "iof_diario_pct", "iof_diario_max_dias",
    ]),
    ("Extras / Rateio", False, [
        "rateio_ipva_meses_default", "rateio_emplacamento_meses_default",
    ]),
    ("Sistema", False, [
        "backup_diario_horario", "update_indicadores_horario",
        "fipe_cache_listas_ttl_dias", "fipe_cache_preco_ttl_horas",
    ]),
]


def _safe_decimal(raw: str) -> Decimal:
    try:
        return Decimal(raw or "0")
    except InvalidOperation:
        return Decimal("0")


def _safe_int(raw: str) -> int:
    try:
        return int(raw or 0)
    except (ValueError, TypeError):
        return 0


def build_configuracoes_page(engine) -> None:
    SessionLocal = get_session_factory(engine)

    @ui.page("/configuracoes")
    def page() -> None:
        def content() -> None:
            ui.label("Regras de negocio").classes("text-lg font-bold")

            widgets: dict[str, Any] = {}

            with SessionLocal() as session:
                svc = RulesService(session)
                raw_values = {k: svc.get_raw(k) or "" for k in EDITABLE_KEYS}

            for group_title, open_default, keys in GROUPS:
                with (
                    ui.expansion(group_title, value=open_default).classes("w-full"),
                    ui.column().classes("gap-3 px-1"),
                ):
                    for k in keys:
                        raw = raw_values[k]
                        label = LABEL_MAP[k]
                        if k in PCT_KEYS:
                            widgets[k] = PercentInput(label, _safe_decimal(raw))
                        elif k in BOOL_KEYS:
                            bool_val = raw.lower() in ("true", "1", "yes")
                            widgets[k] = ui.switch(label, value=bool_val)
                        elif k in INT_KEYS:
                            widgets[k] = (
                                ui.number(label, value=_safe_int(raw), format="%d")
                                .classes("w-full")
                            )
                        elif k in CURRENCY_KEYS:
                            widgets[k] = CurrencyInput(label, _safe_decimal(raw))
                        else:
                            widgets[k] = ui.input(label, value=raw).classes("w-full")

            def save_all() -> None:
                user_id = get_logged_user_id()
                with SessionLocal() as session:
                    svc = RulesService(session)
                    for key, widget in widgets.items():
                        if key in PCT_KEYS:
                            value = str(widget.value)
                        elif key in BOOL_KEYS:
                            value = "true" if widget.value else "false"
                        elif key in INT_KEYS:
                            value = str(int(widget.value or 0))
                        elif key in CURRENCY_KEYS:
                            value = str(widget.value)
                        else:
                            value = widget.value or ""
                        svc.set(key, value, user_id=user_id)
                ui.notify("Configuracoes salvas", type="positive")

            ui.button("Salvar tudo", on_click=save_all).classes("mt-4 w-full")

        shell(content)
