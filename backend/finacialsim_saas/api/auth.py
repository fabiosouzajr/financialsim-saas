from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext, get_current_ctx, get_db_session
from finacialsim_saas.auth.schemas import (
    LoginRequest, PasswordResetConfirmBody, PasswordResetRequestBody,
    RefreshRequest, TokenResponse,
)
from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.data.models import User
from finacialsim_saas.settings import get_settings

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _svc(session: AsyncSession) -> AuthService:
    return AuthService(session, get_settings())


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TokenResponse:
    svc = _svc(session)
    user = await svc.authenticate(body.email, body.password)
    access, refresh = await svc.issue_tokens(user)
    user.last_login_at = datetime.now(timezone.utc)
    await svc.write_audit(tenant_id=user.tenant_id, usuario_id=user.id, acao="login")
    await session.commit()
    return TokenResponse(access=access, refresh=refresh)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(
    body: RefreshRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TokenResponse:
    svc = _svc(session)
    _, access, refresh = await svc.rotate_refresh(body.refresh)
    await session.commit()
    return TokenResponse(access=access, refresh=refresh)


@router.post("/logout", status_code=204)
async def logout(
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    svc = _svc(session)
    result = await session.execute(select(User).where(User.id == ctx.user_id))
    user = result.scalar_one()
    await svc.revoke_all(user)
    await svc.write_audit(tenant_id=ctx.tenant_id, usuario_id=ctx.user_id, acao="logout")
    await session.commit()
    return Response(status_code=204)


@router.post("/password-reset/request", status_code=202)
async def password_reset_request(
    body: PasswordResetRequestBody,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    svc = _svc(session)
    await svc.request_password_reset(body.email)
    await session.commit()
    return Response(status_code=202)


@router.post("/password-reset/confirm", status_code=204)
async def password_reset_confirm(
    body: PasswordResetConfirmBody,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    svc = _svc(session)
    await svc.confirm_password_reset(body.token, body.password)
    await session.commit()
    return Response(status_code=204)
