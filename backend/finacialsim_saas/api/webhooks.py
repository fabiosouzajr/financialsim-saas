"""PSP webhook endpoints — no JWT auth; HMAC-SHA256 verified per provider."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import get_db_session
from finacialsim_saas.pix.deps import get_pix_provider
from finacialsim_saas.pix.service import PixService
from finacialsim_saas.settings import get_settings
from finacialsim_saas.storage.deps import get_storage_backend

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])

_Session = Annotated[AsyncSession, Depends(get_db_session)]


@router.post("/pix")
async def pix_webhook(request: Request, session: _Session) -> dict:
    """Receives Pix PSP callbacks. Always returns 200. Logs everything."""
    body = await request.body()
    headers = dict(request.headers)
    settings = get_settings()
    svc = PixService(session, get_pix_provider(settings), get_storage_backend(settings))
    await svc.handle_webhook(headers, dict(request.query_params), body)
    return {"ok": True}
