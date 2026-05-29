"""Logs - audit_log viewer."""

from __future__ import annotations

from nicegui import ui

from app.data.database import get_session_factory
from app.data.models import AuditLog
from app.ui.layout import shell


def build_logs_page(engine) -> None:
    SessionLocal = get_session_factory(engine)

    @ui.page("/logs")
    def page() -> None:
        def content() -> None:
            with SessionLocal() as session:
                rows = (
                    session.query(AuditLog)
                    .order_by(AuditLog.timestamp.desc())
                    .limit(200)
                    .all()
                )
            ui.table(
                columns=[
                    {"name": "ts", "label": "Timestamp", "field": "ts"},
                    {"name": "user", "label": "Usuario", "field": "user"},
                    {"name": "acao", "label": "Acao", "field": "acao"},
                    {"name": "ent", "label": "Entidade", "field": "ent"},
                ],
                rows=[
                    {
                        "ts": r.timestamp.strftime("%d/%m/%Y %H:%M"),
                        "user": str(r.usuario_id or "-"),
                        "acao": r.acao,
                        "ent": r.entidade or "-",
                    } for r in rows
                ],
            )

        shell(content)