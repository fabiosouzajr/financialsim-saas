"""Tenant profile endpoints — company info and logo for the proposal PDF."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext, get_db_session, require_role
from finacialsim_saas.data.models import Tenant
from finacialsim_saas.settings import get_settings
from finacialsim_saas.storage.deps import get_storage_backend

router = APIRouter(prefix="/api/v1/admin/tenant-profile", tags=["tenant-profile"])

_MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2 MB
_ALLOWED_MIME = {"image/png", "image/jpeg"}


class TenantProfileOut(BaseModel):
    nome: str
    cnpj: str | None
    telefone: str | None
    endereco: str | None
    logo_url: str | None
    proposta_validade_dias: int


class TenantProfileIn(BaseModel):
    nome: str
    cnpj: str | None = None
    telefone: str | None = None
    endereco: str | None = None
    proposta_validade_dias: int = Field(default=15, ge=1, le=30)

    @model_validator(mode="after")
    def validate_cnpj(self) -> "TenantProfileIn":
        if self.cnpj is not None:
            from finacialsim_core.utils.document_validation import is_valid_cnpj
            if not is_valid_cnpj(self.cnpj):
                raise ValueError("CNPJ inválido")
        return self


async def _tenant_profile_out(tenant: Tenant) -> TenantProfileOut:
    logo_url = None
    if tenant.logo_key:
        settings = get_settings()
        storage = get_storage_backend(settings)
        logo_url = await storage.signed_url(tenant.logo_key, expires_in=3600)
    return TenantProfileOut(
        nome=tenant.name,
        cnpj=tenant.cnpj,
        telefone=tenant.telefone,
        endereco=tenant.endereco,
        logo_url=logo_url,
        proposta_validade_dias=tenant.proposta_validade_dias,
    )


@router.get("", response_model=TenantProfileOut)
async def get_tenant_profile(
    ctx: Annotated[RequestContext, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TenantProfileOut:
    tenant = await session.get(Tenant, ctx.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return await _tenant_profile_out(tenant)


@router.put("", response_model=TenantProfileOut)
async def update_tenant_profile(
    body: TenantProfileIn,
    ctx: Annotated[RequestContext, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TenantProfileOut:
    tenant = await session.get(Tenant, ctx.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    tenant.name = body.nome
    tenant.cnpj = body.cnpj
    tenant.telefone = body.telefone
    tenant.endereco = body.endereco
    tenant.proposta_validade_dias = body.proposta_validade_dias
    await session.commit()
    await session.refresh(tenant)
    return await _tenant_profile_out(tenant)


@router.post("/logo", response_model=TenantProfileOut)
async def upload_logo(
    ctx: Annotated[RequestContext, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    file: UploadFile = File(...),
) -> TenantProfileOut:
    if file.content_type not in _ALLOWED_MIME:
        raise HTTPException(status_code=422, detail="Logo must be PNG or JPEG")
    data = await file.read()
    if len(data) > _MAX_LOGO_BYTES:
        raise HTTPException(status_code=422, detail="Logo must be under 2 MB")

    ext = "png" if file.content_type == "image/png" else "jpg"
    key = f"{ctx.tenant_id}/logo/{uuid.uuid4()}.{ext}"

    settings = get_settings()
    storage = get_storage_backend(settings)
    await storage.put(key, data, file.content_type)

    tenant = await session.get(Tenant, ctx.tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    tenant.logo_key = key
    await session.commit()
    await session.refresh(tenant)

    return await _tenant_profile_out(tenant)
