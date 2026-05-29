"""Cadastro page - clientes + usuarios sub-tabs."""

from __future__ import annotations

from nicegui import ui

from app.data.database import get_session_factory
from app.services.auth_service import AuthError, AuthService
from app.services.client_service import ClientService, ClientServiceError
from app.ui.layout import shell
from app.ui.router import get_logged_perfil, get_logged_user_id

_SECTION_LABEL = "text-xs font-semibold text-slate-500 uppercase tracking-widest"


def build_cadastro_page(engine) -> None:
    SessionLocal = get_session_factory(engine)

    @ui.page("/cadastro")
    def page() -> None:
        def content() -> None:
            perfil = get_logged_perfil()
            current_user = get_logged_user_id() or 0

            with ui.row().classes("w-full items-center justify-between mb-2"):
                ui.label("Cadastro").classes("text-xl font-bold text-slate-800")

            with ui.tabs().classes("w-full") as inner_tabs:
                cli_tab = ui.tab("Clientes")
                if perfil == "admin":
                    usr_tab = ui.tab("Usuarios")
            with ui.tab_panels(inner_tabs, value=cli_tab).classes("w-full"):
                with ui.tab_panel(cli_tab):
                    _clients_panel(SessionLocal, current_user)
                if perfil == "admin":
                    with ui.tab_panel(usr_tab):
                        _users_panel(SessionLocal)

        shell(content)


def _clients_panel(SessionLocal, user_id: int) -> None:
    # ── Split layout: form left | table right ─────────────────────────
    with ui.row().classes("w-full gap-4 items-start"):

        # ── Form ──────────────────────────────────────────────────────
        with ui.column().classes("gap-3").style("width: 290px; flex-shrink: 0"):
            ui.label("Novo Cliente").classes(_SECTION_LABEL)

            tipo = ui.toggle(["PF", "PJ"], value="PF").classes("w-full")
            nome = ui.input("Nome").classes("w-full")
            cpf = ui.input("CPF / CNPJ").classes("w-full")
            telefone = ui.input("Telefone").classes("w-full")
            email = ui.input("Email").classes("w-full")

            ui.button("Cadastrar", icon="person_add",
                      on_click=lambda: _save()).props("color=primary")

        # ── Table ─────────────────────────────────────────────────────
        with ui.column().classes("flex-1 gap-2 min-w-0"):
            ui.label("Clientes Cadastrados").classes(_SECTION_LABEL)
            table = ui.table(
                columns=[
                    {
                        "name": "nome", "label": "Nome", "field": "nome",
                        "sortable": True, "align": "center",
                    },
                    {
                        "name": "doc", "label": "CPF/CNPJ", "field": "doc",
                        "align": "center",
                    },
                ],
                rows=[],
            ).classes("w-full").props("flat bordered")

    def _refresh() -> None:
        with SessionLocal() as session:
            results = ClientService(session).find("")
        table.rows = [
            {"nome": c.nome, "doc": c.cpf_cnpj}
            for c in results
        ]
        table.update()

    def _save() -> None:
        try:
            with SessionLocal() as session:
                svc = ClientService(session)
                if tipo.value == "PF":
                    svc.create_pf(
                        nome=nome.value or "", cpf=cpf.value or "", criado_por=user_id,
                        telefone=telefone.value or None, email=email.value or None,
                    )
                else:
                    svc.create_pj(
                        razao_social=nome.value or "", cnpj=cpf.value or "", criado_por=user_id,
                        telefone=telefone.value or None, email=email.value or None,
                    )
            ui.notify("Cliente cadastrado com sucesso", type="positive")
            _refresh()
        except ClientServiceError as e:
            ui.notify(str(e), type="negative")

    _refresh()


def _users_panel(SessionLocal) -> None:
    # ── Form ──────────────────────────────────────────────────────────
    with ui.column().classes("gap-3").style("width: 290px; flex-shrink: 0"):
        ui.label("Novo Usuario").classes(_SECTION_LABEL)

        nome = ui.input("Nome").classes("w-full")
        pin = ui.input("PIN (4-6 digitos)", password=True).classes("w-full")
        perfil = ui.select(
            ["vendedor", "gerente", "admin"], value="vendedor", label="Perfil"
        ).classes("w-full")

        def save() -> None:
            with SessionLocal() as session:
                try:
                    AuthService(session).create_user(
                        nome=nome.value or "", pin=pin.value or "", perfil=perfil.value
                    )
                    ui.notify("Usuario criado com sucesso", type="positive")
                except AuthError as e:
                    ui.notify(str(e), type="negative")

        ui.button("Criar Usuario", icon="person_add", on_click=save).props("color=primary")
