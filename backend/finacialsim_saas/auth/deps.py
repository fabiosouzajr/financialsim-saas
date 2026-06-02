import uuid
from dataclasses import dataclass
from datetime import timezone
from typing import Annotated, AsyncGenerator

import jwt
from fastapi import Depends, Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.data.models import Role, User
from finacialsim_saas.errors import AuthError, TenantAccessError
from finacialsim_saas.settings import get_settings


@dataclass
class RequestContext:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: Role
    iat: float
    client_id: uuid.UUID | None = None


async def _parse_bearer(request: Request) -> RequestContext | None:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        payload = jwt.decode(
            auth[7:], get_settings().jwt_secret_key, algorithms=["HS256"]
        )
    except jwt.PyJWTError:
        return None
    return RequestContext(
        user_id=uuid.UUID(payload["sub"]),
        tenant_id=uuid.UUID(payload["tenant_id"]),
        role=Role(payload["role"]),
        iat=float(payload["iat"]),
        client_id=uuid.UUID(payload["client_id"]) if "client_id" in payload else None,
    )


async def get_db_session(
    request: Request,
    ctx: Annotated[RequestContext | None, Depends(_parse_bearer)],
) -> AsyncGenerator[AsyncSession, None]:
    factory = request.app.state.session_factory
    async with factory() as session:
        if ctx is not None:
            await session.execute(
                text(f"SET LOCAL app.tenant_id = '{ctx.tenant_id}'")
            )
        yield session


async def get_current_ctx(
    ctx: Annotated[RequestContext | None, Depends(_parse_bearer)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> RequestContext:
    if ctx is None:
        raise AuthError("Not authenticated")
    result = await session.execute(select(User).where(User.id == ctx.user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise AuthError("User not found or inactive")
    if str(user.tenant_id) != str(ctx.tenant_id):
        raise AuthError("Token tenant mismatch")
    if user.tokens_revoked_at is not None:
        revoked_ts = user.tokens_revoked_at.replace(tzinfo=timezone.utc).timestamp()
        if ctx.iat <= revoked_ts:
            raise AuthError("Token revoked")
    return ctx


def require_role(*allowed_roles: str):
    async def _inner(
        ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    ) -> RequestContext:
        if ctx.role.value not in allowed_roles:
            raise TenantAccessError("Insufficient permissions")
        return ctx
    return _inner
