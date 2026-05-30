from __future__ import annotations

import base64
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.auth.deps import RequestContext
from finacialsim_saas.data.models import Vehicle, VehicleStatus
from finacialsim_saas.errors import ExternalProviderError, NotFoundError, TenantAccessError, ValidationError
from finacialsim_saas.schemas.vehicles import VehicleIn, VehicleListItem, VehicleListPage, VehicleOut

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "ativo": {"reservado", "inativo"},
    "inativo": {"ativo"},
    "reservado": {"vendido", "ativo"},
    "vendido": set(),
}


class VehicleService:
    def __init__(self, session: AsyncSession, fipe_chain: Any = None) -> None:
        self._s = session
        self._fipe = fipe_chain

    async def create(self, body: VehicleIn, ctx: RequestContext) -> VehicleOut:
        vehicle = Vehicle(
            tenant_id=ctx.tenant_id,
            fonte=body.fonte,
            tipo=body.tipo,
            marca=body.marca,
            modelo=body.modelo,
            ano_modelo=body.ano_modelo,
            combustivel=body.combustivel,
            codigo_fipe=body.codigo_fipe,
            valor_fipe=Decimal(str(body.valor_fipe)) if body.valor_fipe is not None else None,
            valor_referencia=Decimal(str(body.valor_referencia)) if body.valor_referencia is not None else None,
            mes_referencia_fipe=body.mes_referencia_fipe,
            cor=body.cor,
            placa=body.placa,
            odometro_km=body.odometro_km,
            snapshot_json=body.snapshot_json,
            status=VehicleStatus.ativo,
            criado_por=ctx.user_id,
        )
        self._s.add(vehicle)
        await self._s.flush()
        return _to_out(vehicle)

    async def get(self, vehicle_id: uuid.UUID, ctx: RequestContext) -> VehicleOut:
        return _to_out(await self._get_or_404(vehicle_id, ctx.tenant_id))

    async def list(
        self,
        ctx: RequestContext,
        status: str | None = None,
        placa: str | None = None,
        cursor: str | None = None,
        limit: int = 20,
    ) -> VehicleListPage:
        stmt = select(Vehicle).where(Vehicle.tenant_id == ctx.tenant_id)
        if status:
            stmt = stmt.where(Vehicle.status == VehicleStatus(status))
        if placa:
            stmt = stmt.where(Vehicle.placa.ilike(f"%{placa}%"))
        if cursor:
            stmt = stmt.where(Vehicle.criado_em < _decode_cursor(cursor))
        stmt = stmt.order_by(Vehicle.criado_em.desc()).limit(limit + 1)

        rows = (await self._s.execute(stmt)).scalars().all()
        next_cursor = None
        if len(rows) > limit:
            rows = list(rows[:limit])
            next_cursor = _encode_cursor(rows[-1].criado_em)

        return VehicleListPage(
            items=[_to_list_item(r) for r in rows],
            next_cursor=next_cursor,
        )

    async def update(self, vehicle_id: uuid.UUID, body: VehicleIn, ctx: RequestContext) -> VehicleOut:
        v = await self._get_or_404(vehicle_id, ctx.tenant_id)
        v.fonte = body.fonte
        v.tipo = body.tipo
        v.marca = body.marca
        v.modelo = body.modelo
        v.ano_modelo = body.ano_modelo
        v.combustivel = body.combustivel
        v.codigo_fipe = body.codigo_fipe
        v.valor_fipe = Decimal(str(body.valor_fipe)) if body.valor_fipe is not None else None
        v.valor_referencia = Decimal(str(body.valor_referencia)) if body.valor_referencia is not None else None
        v.mes_referencia_fipe = body.mes_referencia_fipe
        v.cor = body.cor
        v.placa = body.placa
        v.odometro_km = body.odometro_km
        v.snapshot_json = body.snapshot_json
        v.atualizado_em = datetime.now(timezone.utc)
        await self._s.flush()
        return _to_out(v)

    async def set_status(self, vehicle_id: uuid.UUID, new_status: str, ctx: RequestContext) -> VehicleOut:
        v = await self._get_or_404(vehicle_id, ctx.tenant_id)
        current = v.status.value
        allowed = _VALID_TRANSITIONS.get(current, set())
        if new_status not in allowed:
            raise ValidationError(
                f"Transição {current!r} → {new_status!r} não permitida. "
                f"Permitidas: {sorted(allowed) or 'nenhuma'}"
            )
        v.status = VehicleStatus(new_status)
        v.atualizado_em = datetime.now(timezone.utc)
        await self._s.flush()
        return _to_out(v)

    async def refresh_fipe(self, vehicle_id: uuid.UUID, ctx: RequestContext) -> VehicleOut:
        v = await self._get_or_404(vehicle_id, ctx.tenant_id)
        if v.fonte == "manual":
            raise ValidationError("Veículo manual não tem dados FIPE para atualizar")
        if self._fipe is None:
            raise RuntimeError("fipe_chain not injected into VehicleService")
        snap = v.snapshot_json or {}
        result = await self._fipe.fetch({
            "action": "price",
            "tipo": v.tipo,
            "brand_id": snap.get("marca_id", ""),
            "model_id": snap.get("modelo_id", ""),
            "year_id": snap.get("year_id", ""),
        })
        if result.is_err:
            raise ExternalProviderError(f"FIPE unavailable: {result.error}")
        quote = result.value
        v.valor_fipe = quote.valor
        v.mes_referencia_fipe = quote.mes_referencia
        v.snapshot_json = {
            **snap,
            **quote.raw_payload,
            "marca_id": quote.marca_id,
            "modelo_id": quote.modelo_id,
        }
        v.atualizado_em = datetime.now(timezone.utc)
        await self._s.flush()
        return _to_out(v)

    async def _get_or_404(self, vehicle_id: uuid.UUID, tenant_id: uuid.UUID) -> Vehicle:
        row = await self._s.get(Vehicle, vehicle_id)
        if row is None:
            raise NotFoundError(f"Veículo {vehicle_id} não encontrado")
        if row.tenant_id != tenant_id:
            raise TenantAccessError("Acesso negado")
        return row


def _encode_cursor(dt: datetime) -> str:
    return base64.b64encode(dt.isoformat().encode()).decode()


def _decode_cursor(cursor: str) -> datetime:
    return datetime.fromisoformat(base64.b64decode(cursor).decode())


def _to_out(v: Vehicle) -> VehicleOut:
    return VehicleOut(
        id=v.id,
        tenant_id=v.tenant_id,
        fonte=v.fonte,
        tipo=v.tipo,
        marca=v.marca,
        modelo=v.modelo,
        ano_modelo=v.ano_modelo,
        combustivel=v.combustivel,
        codigo_fipe=v.codigo_fipe,
        valor_fipe=v.valor_fipe,
        valor_referencia=v.valor_referencia,
        mes_referencia_fipe=v.mes_referencia_fipe,
        cor=v.cor,
        placa=v.placa,
        odometro_km=v.odometro_km,
        status=v.status.value,
        snapshot_json=v.snapshot_json,
        criado_por=v.criado_por,
        criado_em=v.criado_em,
        atualizado_em=v.atualizado_em,
    )


def _to_list_item(v: Vehicle) -> VehicleListItem:
    return VehicleListItem(
        id=v.id,
        tipo=v.tipo,
        marca=v.marca,
        modelo=v.modelo,
        ano_modelo=v.ano_modelo,
        placa=v.placa,
        valor_fipe=v.valor_fipe,
        status=v.status.value,
        criado_em=v.criado_em,
    )
