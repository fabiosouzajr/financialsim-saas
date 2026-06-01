"""Storage serve endpoint — validates HMAC token and streams the file."""
from __future__ import annotations

import hashlib
import hmac
import time

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from finacialsim_saas.settings import get_settings
from finacialsim_saas.storage.deps import get_storage_backend

router = APIRouter(prefix="/api/v1/storage", tags=["storage"])


@router.get("/serve")
async def serve_storage_file(
    key: str = Query(...),
    expires: int = Query(...),
    sig: str = Query(...),
) -> StreamingResponse:
    settings = get_settings()
    secret = settings.storage_hmac_secret.encode()
    msg = f"{key}:{expires}".encode()
    expected = hmac.new(secret, msg, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise HTTPException(status_code=403, detail="invalid signature")
    if time.time() > expires:
        raise HTTPException(status_code=410, detail="link expired")

    storage = get_storage_backend(settings)
    data = await storage.get(key)
    filename = key.rsplit("/", 1)[-1]
    return StreamingResponse(
        iter([data]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
