"""Staff Pix admin endpoints — manager|admin only."""
from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext, get_db_session, require_role
from finacialsim_saas.data.models import PixCharge, PixChargeStatus
from finacialsim_saas.pix.deps import get_pix_provider
from finacialsim_saas.pix.service import PixService
from finacialsim_saas.settings import get_settings
from finacialsim_saas.storage.deps import get_storage_backend

router = APIRouter(prefix="/api/v1/admin/pix", tags=["pix-admin"])

_StaffCtx = Annotated[RequestContext, Depends(require_role("manager", "admin"))]
_Session = Annotated[AsyncSession, Depends(get_db_session)]


def _pix_svc(request: Request, session: AsyncSession) -> PixService:
    settings = get_settings()
    return PixService(session, get_pix_provider(settings), get_storage_backend(settings))


@router.post("/fake/mark-paid/{txid}")
async def mark_paid(
    txid: str,
    request: Request,
    ctx: _StaffCtx,
    session: _Session,
) -> dict:
    """Fake-provider only: triggers webhook path to mark a charge as paid."""
    settings = get_settings()
    if settings.pix_provider == "external":
        raise HTTPException(status_code=501, detail="mark-paid not available for external provider")

    # Look up charge to get amount
    charge = await session.scalar(
        select(PixCharge).where(
            PixCharge.txid == txid,
            PixCharge.tenant_id == ctx.tenant_id,
        )
    )
    if charge is None:
        raise HTTPException(status_code=404, detail=f"charge with txid {txid!r} not found")
    if charge.status != PixChargeStatus.pending:
        raise HTTPException(
            status_code=409,
            detail=f"charge status is {charge.status.value}, cannot mark paid",
        )

    # Build webhook payload
    body_dict = {
        "pix": [
            {
                "txid": txid,
                "status": "paid",
                "valor": str(charge.amount),
            }
        ]
    }
    body = json.dumps(body_dict).encode()

    # Sign with PIX_WEBHOOK_SECRET
    if settings.pix_webhook_secret:
        sig = hmac.new(
            settings.pix_webhook_secret.encode(), body, hashlib.sha256
        ).hexdigest()
        headers = {"X-Pix-Signature": f"sha256={sig}", "Content-Type": "application/json"}
    else:
        headers = {"Content-Type": "application/json"}

    svc = _pix_svc(request, session)
    await svc.handle_webhook(headers, body)
    return {"txid": txid, "status": "paid"}


@router.get("/charges")
async def list_pix_charges(
    ctx: _StaffCtx,
    session: _Session,
    status: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, le=100),
) -> dict:
    """List pix charges for this tenant with cursor pagination."""
    import base64

    q = select(PixCharge).where(PixCharge.tenant_id == ctx.tenant_id)
    if status:
        q = q.where(PixCharge.status == PixChargeStatus(status))
    if cursor:
        cur = json.loads(base64.b64decode(cursor))
        q = q.where(PixCharge.criado_em < cur["ts"])
    q = q.order_by(PixCharge.criado_em.desc()).limit(limit + 1)

    results = list(await session.scalars(q))
    has_more = len(results) > limit
    items = results[:limit]

    next_cursor = None
    if has_more:
        next_cursor = base64.b64encode(
            json.dumps({"ts": items[-1].criado_em.isoformat()}).encode()
        ).decode()

    return {
        "items": [
            {
                "id": str(c.id),
                "txid": c.txid,
                "status": c.status.value,
                "amount": str(c.amount),
                "expires_at": c.expires_at.isoformat(),
                "parcela_payment_id": str(c.parcela_payment_id),
            }
            for c in items
        ],
        "next_cursor": next_cursor,
    }
