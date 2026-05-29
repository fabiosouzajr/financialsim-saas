"""Common layout - sidebar + header. Used by all pages except /login."""

from __future__ import annotations

from typing import Callable

from nicegui import app, ui

from app.ui.router import get_logged_perfil, logout, navigate


# (label, route, allowed_roles, material-icon)
TABS = [
    ("Dashboard",    "/dashboard",    {"vendedor", "gerente", "admin"}, "dashboard"),
    ("Cadastro",     "/cadastro",     {"vendedor", "gerente", "admin"}, "people"),
    ("Simulação",    "/simulacao",    {"vendedor", "gerente", "admin"}, "calculate"),
    ("Comparativo",  "/comparativo",  {"vendedor", "gerente", "admin"}, "compare_arrows"),
    ("Amortização",  "/amortizacao",  {"vendedor", "gerente", "admin"}, "account_balance"),
    ("Indicadores",  "/indicadores",  {"vendedor", "gerente", "admin"}, "trending_up"),
    ("Veículos",     "/veiculos",     {"vendedor", "gerente", "admin"}, "directions_car"),
    ("Configurações", "/configuracoes", {"admin"},                      "settings"),
    ("Logs",         "/logs",         {"gerente", "admin"},             "receipt_long"),
    ("Documentação", "/docs",         {"vendedor", "gerente", "admin"}, "menu_book"),
]


def shell(content_builder: Callable[[], None]) -> None:
    perfil = get_logged_perfil()
    nome = app.storage.user.get("nome", "")

    # ── Slim top header (user info + logout) ───────────────────────
    with ui.header().classes("app-header items-center px-4"):
        ui.element("div").classes("flex-1")  # spacer
        with ui.row().classes("items-center gap-3"):
            ui.icon("account_circle", size="sm").classes("text-slate-400")
            with ui.column().classes("gap-0 items-start"):
                ui.label(nome).classes("text-sm font-semibold text-slate-800 leading-tight")
                ui.label(perfil or "").classes("text-xs text-slate-400 capitalize leading-tight")
            ui.button(icon="logout", on_click=_do_logout).props("flat round dense").classes(
                "text-slate-400 ml-1"
            )

    # ── Left sidebar ───────────────────────────────────────────────
    with ui.left_drawer(fixed=True, top_corner=True).props("width=240").classes("app-sidebar"):

        # Brand
        with ui.column().classes("px-5 pt-6 pb-5"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("directions_car", size="sm").classes("sidebar-brand-icon text-blue-400")
                ui.label("FinacialSim").classes("sidebar-brand-name text-white font-bold text-lg")
            ui.label("Financiamentos").classes("text-slate-500 text-xs mt-0.5 pl-0.5")

        ui.element("hr").classes("sidebar-divider")

        # Navigation
        with ui.column().classes("px-3 pt-3 pb-3 gap-0.5"):
            for label, route, roles, icon_name in TABS:
                if perfil in roles:
                    with ui.element("div").classes("nav-item").on(
                        "click", lambda r=route: navigate(r)
                    ):
                        ui.icon(icon_name, size="xs").classes("nav-icon")
                        ui.label(label).classes("nav-label")

        # User section pinned at bottom (spacer + divider + user row)
        ui.element("div").classes("flex-1")
        ui.element("hr").classes("sidebar-divider mt-auto")
        with ui.row().classes("items-center gap-2 px-4 py-4"):
            ui.icon("person", size="xs").classes("text-slate-500")
            with ui.column().classes("gap-0"):
                ui.label(nome).classes("text-slate-300 text-xs font-medium leading-tight")
                ui.label(perfil or "").classes("text-slate-500 text-xs capitalize leading-tight")

    # ── Main content ───────────────────────────────────────────────
    # Content placed outside header/drawer/footer goes into page container automatically.
    with ui.column().classes("w-full p-6 gap-4"):
        content_builder()


def _do_logout() -> None:
    logout()
    navigate("/login")
