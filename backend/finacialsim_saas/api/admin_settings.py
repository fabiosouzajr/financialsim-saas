from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext, get_db_session, require_role
from finacialsim_saas.schemas.admin_settings import SettingItem, SettingUpdateIn
from finacialsim_saas.services.settings_service import (
    READ_ONLY_KEYS,
    WRITABLE_KEYS,
    SettingsService,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin-settings"])


@router.get("/settings", response_model=dict[str, SettingItem])
async def get_admin_settings(
    ctx: Annotated[RequestContext, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, SettingItem]:
    all_settings = await SettingsService(session).get_all()
    return {
        key: SettingItem(value=value, source=source)
        for key, (value, source) in all_settings.items()
    }


@router.put("/settings/{key}", status_code=status.HTTP_204_NO_CONTENT)
async def update_admin_setting(
    key: str,
    body: SettingUpdateIn,
    ctx: Annotated[RequestContext, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> None:
    if key in READ_ONLY_KEYS:
        raise HTTPException(status_code=422, detail=f"Key '{key}' is read-only (env-only)")
    if key not in WRITABLE_KEYS:
        raise HTTPException(status_code=422, detail=f"Unknown settings key: '{key}'")
    svc = SettingsService(session)
    await svc.update(key, body.value, updated_by=str(ctx.user_id))
    await session.commit()
