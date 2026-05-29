"""Login page - PIN-based auth."""

from __future__ import annotations

from nicegui import ui

from app.data.database import get_session_factory
from app.data.repositories import UserRepository
from app.services.auth_service import AuthError, AuthService
from app.ui.router import login_user, navigate


def build_login_page(engine) -> None:
    SessionLocal = get_session_factory(engine)

    @ui.page("/login")
    def login_page() -> None:
        with SessionLocal() as session:
            users = UserRepository(session).list_active()
            user_options = {u.id: f"{u.nome} ({u.perfil})" for u in users}

        with ui.card().classes("absolute-center w-96"):
            ui.label("FinacialSim - Login").classes("text-xl font-bold")
            user_select = ui.select(options=user_options, label="Usuario").classes("w-full")
            pin_input = ui.input(label="PIN", password=True).props("type=password")
            pin_input.on("keydown.enter", lambda _: do_login())
            error_label = ui.label("").classes("text-red-500")

            def do_login() -> None:
                if not user_select.value:
                    error_label.text = "Selecione um usuario"
                    error_label.update()
                    return
                with SessionLocal() as session:
                    try:
                        user = AuthService(session).login(user_select.value, pin_input.value or "")
                        login_user(user.id, user.perfil, user.nome)
                        navigate("/dashboard")
                    except AuthError as e:
                        error_label.text = str(e)
                        error_label.update()

            ui.button("Entrar", on_click=do_login).classes("w-full")