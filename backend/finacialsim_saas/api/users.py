import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext, get_current_ctx, get_db_session, require_role
from finacialsim_saas.auth.schemas import (
    CreateUserRequest, PatchUserRequest, UserListItem, UserMeResponse,
)
from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.data.models import NotificationsOutbox, Role, User
from finacialsim_saas.errors import NotFoundError, TenantAccessError
from finacialsim_saas.settings import get_settings

router = APIRouter(prefix="/api/v1", tags=["users"])


def _svc(session: AsyncSession) -> AuthService:
    return AuthService(session, get_settings())


@router.get("/me", response_model=UserMeResponse)
async def get_me(
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserMeResponse:
    result = await session.execute(select(User).where(User.id == ctx.user_id))
    user = result.scalar_one()
    return UserMeResponse(
        id=user.id, tenant_id=user.tenant_id, email=user.email, name=user.name,
        role=user.role.value, is_active=user.is_active,
        last_login_at=user.last_login_at, created_at=user.created_at,
    )


@router.get("/users", response_model=list[UserListItem])
async def list_users(
    ctx: Annotated[RequestContext, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[UserListItem]:
    result = await session.execute(
        select(User).where(
            User.tenant_id == ctx.tenant_id,
            User.role != Role.customer,
        )
    )
    return [
        UserListItem(
            id=u.id, email=u.email, name=u.name,
            role=u.role.value, is_active=u.is_active, created_at=u.created_at,
        )
        for u in result.scalars().all()
    ]


@router.post("/users", response_model=UserListItem, status_code=201)
async def create_user(
    body: CreateUserRequest,
    ctx: Annotated[RequestContext, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserListItem:
    svc = _svc(session)
    user = await svc.register_user(
        tenant_id=ctx.tenant_id, email=body.email, password=body.password,
        name=body.name, role=Role(body.role), ctx=ctx,
    )
    session.add(
        NotificationsOutbox(
            tenant_id=ctx.tenant_id,
            type="user_invite",
            recipient=user.email,
            payload={"user_name": user.name},
        )
    )
    await session.commit()
    await session.refresh(user)
    return UserListItem(
        id=user.id, email=user.email, name=user.name,
        role=user.role.value, is_active=user.is_active, created_at=user.created_at,
    )


@router.patch("/users/{user_id}", response_model=UserListItem)
async def patch_user(
    user_id: uuid.UUID,
    body: PatchUserRequest,
    ctx: Annotated[RequestContext, Depends(require_role("admin"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> UserListItem:
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise NotFoundError(f"User {user_id} not found")
    if str(user.tenant_id) != str(ctx.tenant_id):
        raise TenantAccessError("Cannot modify users from another tenant")

    before: dict = {"role": user.role.value, "is_active": user.is_active}
    if body.role is not None:
        user.role = Role(body.role)
    if body.is_active is not None:
        user.is_active = body.is_active
    after: dict = {"role": user.role.value, "is_active": user.is_active}

    svc = _svc(session)
    await svc.write_audit(
        tenant_id=ctx.tenant_id, usuario_id=ctx.user_id,
        acao="user_patch", entidade="user", entidade_id=user.id,
        diff_json={"before": before, "after": after},
    )
    await session.commit()
    await session.refresh(user)
    return UserListItem(
        id=user.id, email=user.email, name=user.name,
        role=user.role.value, is_active=user.is_active, created_at=user.created_at,
    )
