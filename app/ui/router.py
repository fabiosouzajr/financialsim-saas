"""Router + role guards for the NiceGUI app."""

from __future__ import annotations

from typing import Callable

from nicegui import app, ui


def get_logged_user_id() -> int | None:
    return app.storage.user.get("user_id")


def get_logged_perfil() -> str | None:
    return app.storage.user.get("perfil")


def login_user(user_id: int, perfil: str, nome: str) -> None:
    app.storage.user["user_id"] = user_id
    app.storage.user["perfil"] = perfil
    app.storage.user["nome"] = nome


def logout() -> None:
    app.storage.user.clear()


def require_role(*allowed_roles: str) -> Callable:
    def decorator(handler: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            perfil = get_logged_perfil()
            if perfil is None:
                ui.navigate.to("/login")
                return None
            if perfil not in allowed_roles:
                ui.notify("Acesso negado", type="negative")
                ui.navigate.to("/dashboard")
                return None
            return handler(*args, **kwargs)
        return wrapper
    return decorator


def navigate(route: str) -> None:
    ui.navigate.to(route)