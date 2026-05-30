from __future__ import annotations

import base64
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_core.utils.document_validation import is_valid_cnpj, is_valid_cpf
from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.data.models import Client, ClientType
from finacialsim_saas.errors import ConflictError, NotFoundError, TenantAccessError, ValidationError
from finacialsim_saas.schemas.clients import ClientIn, ClientListItem, ClientListPage, ClientOut


class ClientService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create(self, body: ClientIn, ctx: RequestContext) -> ClientOut:
        _validate_document(body.cpf_cnpj, body.tipo)
        existing = (
            await self._s.execute(
                select(Client).where(
                    Client.tenant_id == ctx.tenant_id,
                    Client.cpf_cnpj == body.cpf_cnpj,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ConflictError(f"Cliente com CPF/CNPJ {body.cpf_cnpj} já existe")

        client = Client(
            tenant_id=ctx.tenant_id,
            nome=body.nome,
            cpf_cnpj=body.cpf_cnpj,
            tipo=ClientType(body.tipo),
            rg=body.rg,
            data_nasc=body.data_nasc,
            profissao=body.profissao,
            renda=body.renda,
            telefone=body.telefone,
            email=body.email,
            endereco_json=body.endereco_json,
            observacoes=body.observacoes,
            criado_por=ctx.user_id,
        )
        self._s.add(client)
        await self._s.flush()
        return _to_out(client)

    async def get(self, client_id: uuid.UUID, ctx: RequestContext) -> ClientOut:
        return _to_out(await self._get_or_404(client_id, ctx.tenant_id))

    async def list(
        self,
        ctx: RequestContext,
        q: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> ClientListPage:
        stmt = select(Client).where(
            Client.tenant_id == ctx.tenant_id,
            Client.is_active.is_(True),
        )
        if q:
            stmt = stmt.where(
                Client.nome.ilike(f"%{q}%") | Client.cpf_cnpj.ilike(f"%{q}%")
            )
        if cursor:
            stmt = stmt.where(Client.criado_em < _decode_cursor(cursor))
        stmt = stmt.order_by(Client.criado_em.desc()).limit(limit + 1)

        rows = (await self._s.execute(stmt)).scalars().all()
        next_cursor = None
        if len(rows) > limit:
            rows = list(rows[:limit])
            next_cursor = _encode_cursor(rows[-1].criado_em)

        return ClientListPage(
            items=[_to_list_item(r) for r in rows],
            next_cursor=next_cursor,
        )

    async def update(self, client_id: uuid.UUID, body: ClientIn, ctx: RequestContext) -> ClientOut:
        client = await self._get_or_404(client_id, ctx.tenant_id)
        _validate_document(body.cpf_cnpj, body.tipo)
        if body.cpf_cnpj != client.cpf_cnpj:
            dupe = (
                await self._s.execute(
                    select(Client).where(
                        Client.tenant_id == ctx.tenant_id,
                        Client.cpf_cnpj == body.cpf_cnpj,
                    )
                )
            ).scalar_one_or_none()
            if dupe is not None:
                raise ConflictError(f"CPF/CNPJ {body.cpf_cnpj} já em uso")
        client.nome = body.nome
        client.cpf_cnpj = body.cpf_cnpj
        client.tipo = ClientType(body.tipo)
        client.rg = body.rg
        client.data_nasc = body.data_nasc
        client.profissao = body.profissao
        client.renda = body.renda
        client.telefone = body.telefone
        client.email = body.email
        client.endereco_json = body.endereco_json
        client.observacoes = body.observacoes
        client.atualizado_em = datetime.now(timezone.utc)
        await self._s.flush()
        return _to_out(client)

    async def deactivate(self, client_id: uuid.UUID, ctx: RequestContext) -> ClientOut:
        client = await self._get_or_404(client_id, ctx.tenant_id)
        client.is_active = False
        client.atualizado_em = datetime.now(timezone.utc)
        await self._s.flush()
        return _to_out(client)

    async def _get_or_404(self, client_id: uuid.UUID, tenant_id: uuid.UUID) -> Client:
        row = await self._s.get(Client, client_id)
        if row is None:
            raise NotFoundError(f"Cliente {client_id} não encontrado")
        if row.tenant_id != tenant_id:
            raise TenantAccessError("Acesso negado")
        return row


def _validate_document(cpf_cnpj: str, tipo: str) -> None:
    clean = "".join(ch for ch in cpf_cnpj if ch.isdigit())
    if tipo == "pf":
        if not is_valid_cpf(clean):
            raise ValidationError("CPF inválido")
    elif tipo == "pj":
        if not is_valid_cnpj(clean):
            raise ValidationError("CNPJ inválido")
    else:
        raise ValidationError(f"tipo inválido: {tipo!r}. Use 'pf' ou 'pj'")


def _encode_cursor(dt: datetime) -> str:
    return base64.b64encode(dt.isoformat().encode()).decode()


def _decode_cursor(cursor: str) -> datetime:
    return datetime.fromisoformat(base64.b64decode(cursor).decode())


def _to_out(c: Client) -> ClientOut:
    return ClientOut(
        id=c.id,
        tenant_id=c.tenant_id,
        nome=c.nome,
        cpf_cnpj=c.cpf_cnpj,
        tipo=c.tipo.value,
        rg=c.rg,
        data_nasc=c.data_nasc,
        profissao=c.profissao,
        renda=c.renda,
        telefone=c.telefone,
        email=c.email,
        endereco_json=c.endereco_json,
        observacoes=c.observacoes,
        is_active=c.is_active,
        criado_por=c.criado_por,
        criado_em=c.criado_em,
        atualizado_em=c.atualizado_em,
    )


def _to_list_item(c: Client) -> ClientListItem:
    return ClientListItem(
        id=c.id,
        nome=c.nome,
        cpf_cnpj=c.cpf_cnpj,
        tipo=c.tipo.value,
        telefone=c.telefone,
        email=c.email,
        is_active=c.is_active,
        criado_em=c.criado_em,
    )
