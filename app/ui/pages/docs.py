"""Documentacao tecnica - renderiza docs/*.md inline."""

from __future__ import annotations

from pathlib import Path

from nicegui import ui

from app.ui.layout import shell


DOCS = [
    ("Guia do usuario", "docs/guia_usuario.md"),
    ("Matematica da Tabela Price", "docs/matematica_price.md"),
    ("Troubleshooting", "docs/troubleshooting.md"),
    ("Arquitetura", "docs/ARQUITETURA.md"),
]


def build_docs_page(engine) -> None:

    @ui.page("/docs")
    def page() -> None:
        def content() -> None:
            with ui.row().classes("w-full"):
                with ui.column().classes("w-1/4"):
                    for label, path in DOCS:
                        ui.button(label, on_click=lambda p=path: _load(p)).classes("w-full")

                content_area = ui.column().classes("w-3/4")
                with content_area:
                    ui.markdown("Selecione um documento.")

                def _load(path: str) -> None:
                    content_area.clear()
                    p = Path(path)
                    if not p.exists():
                        with content_area:
                            ui.label(f"Arquivo nao encontrado: {path}")
                        return
                    with content_area:
                        ui.markdown(p.read_text(encoding="utf-8"))

        shell(content)