import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext, get_current_ctx, get_db_session, require_role
from finacialsim_saas.schemas.clients import ClientIn, ClientListPage, ClientOut
from finacialsim_saas.services.client_service import ClientService

router = APIRouter(prefix="/api/v1/clients", tags=["clients"])


@router.get("", response_model=ClientListPage)
async def list_clients(
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    q: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, le=100),
) -> ClientListPage:
    return await ClientService(session).list(ctx, q=q, cursor=cursor, limit=limit)


@router.post("", response_model=ClientOut, status_code=201)
async def create_client(
    body: ClientIn,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ClientOut:
    result = await ClientService(session).create(body, ctx)
    await session.commit()
    return result


@router.get("/{client_id}", response_model=ClientOut)
async def get_client(
    client_id: uuid.UUID,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ClientOut:
    return await ClientService(session).get(client_id, ctx)


@router.patch("/{client_id}", response_model=ClientOut)
async def update_client(
    client_id: uuid.UUID,
    body: ClientIn,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ClientOut:
    result = await ClientService(session).update(client_id, body, ctx)
    await session.commit()
    return result


@router.post("/{client_id}/deactivate", response_model=ClientOut)
async def deactivate_client(
    client_id: uuid.UUID,
    ctx: Annotated[RequestContext, Depends(get_current_ctx)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ClientOut:
    result = await ClientService(session).deactivate(client_id, ctx)
    await session.commit()
    return result


@router.post("/{client_id}/invite", status_code=200)
async def invite_client_customer(
    client_id: uuid.UUID,
    ctx: Annotated[RequestContext, Depends(require_role("manager", "admin"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict:
    """Create or re-invite the customer user for a client. Invalidates old token."""
    from finacialsim_saas.auth.service import AuthService
    from finacialsim_saas.settings import get_settings
    from finacialsim_saas.data.models import User, Role
    from sqlalchemy import select

    svc = AuthService(session, get_settings())

    existing = await session.scalar(
        select(User).where(
            User.client_id == client_id,
            User.role == Role.customer,
            User.tenant_id == ctx.tenant_id,
        )
    )
    if existing is not None:
        user = await svc.re_invite(client_id, ctx)
    else:
        user = await svc.invite_customer(client_id, ctx)
    await session.commit()

    return {"user_id": str(user.id), "email": user.email, "status": "invited"}
