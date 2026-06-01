from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext, get_current_ctx, get_db_session
from finacialsim_saas.schemas.audit_log import AuditLogItem, AuditLogPage
from finacialsim_saas.services.audit_service import AuditService

router = APIRouter(prefix="/api/v1", tags=["audit-log"])


@router.get("/audit-log", response_model=AuditLogPage)
async def list_audit_log(
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    usuario_id: uuid.UUID | None = None,
    entidade: str | None = None,
    acao: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    cursor: str | None = None,
    format: str | None = None,
) -> AuditLogPage | StreamingResponse:
    svc = AuditService(session)
    items, next_cursor = await svc.list(
        tenant_id=ctx.tenant_id,
        caller_role=ctx.role,
        caller_user_id=ctx.user_id,
        usuario_id=usuario_id,
        entidade=entidade,
        acao=acao,
        date_from=date_from,
        date_to=date_to,
        cursor=cursor,
    )

    if format == "csv":
        return _build_csv_response(items)

    return AuditLogPage(
        items=[AuditLogItem.model_validate(i) for i in items],
        next_cursor=next_cursor,
    )


def _build_csv_response(items: list) -> StreamingResponse:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["timestamp", "acao", "entidade", "entidade_id", "usuario_id", "diff_json"])
    for row in items:
        writer.writerow([
            row.timestamp.isoformat(),
            row.acao,
            row.entidade or "",
            str(row.entidade_id) if row.entidade_id else "",
            str(row.usuario_id) if row.usuario_id else "",
            json.dumps(row.diff_json) if row.diff_json else "",
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit-log.csv"},
    )
