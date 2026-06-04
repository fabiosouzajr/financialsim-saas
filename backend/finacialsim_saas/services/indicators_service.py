from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.data.models import IndicatorHistory
from finacialsim_saas.errors import AppError
from finacialsim_saas.integrations.bacen.schema import IndicatorPoint
from finacialsim_saas.schemas.indicators import IndicatorOut, SeriesPoint

UTC = timezone.utc

MAX_AGE_HOURS: dict[str, int] = {
    "SELIC": 26,
    "CDI": 26,
    "IPCA": 744,
    "TX_BACEN_VEIC": 744,
}

VALID_RANGES: dict[str, int] = {"3m": 3, "6m": 6, "12m": 12, "24m": 24}

CANONICAL_CODIGOS = ["SELIC", "CDI", "IPCA", "TX_BACEN_VEIC"]


def _yearly_to_monthly(r: Decimal) -> Decimal:
    r_f = float(r)
    monthly = ((1 + r_f / 100) ** (1 / 12) - 1) * 100
    return Decimal(str(round(monthly, 6)))


def _daily_to_30d(r: Decimal) -> Decimal:
    r_f = float(r)
    accum = ((1 + r_f / 100) ** 30 - 1) * 100
    return Decimal(str(round(accum, 6)))


def _compute_derived(
    codigo: str, r: Decimal
) -> tuple[Decimal | None, str | None, str | None]:
    try:
        if codigo in ("SELIC", "TX_BACEN_VEIC"):
            return _yearly_to_monthly(r), "pct_am", "% a.m."
        if codigo == "CDI":
            return _daily_to_30d(r), "pct_30d", "% (30d)"
    except (ValueError, ArithmeticError, OverflowError):
        pass
    return None, None, None


class IndicatorsService:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def upsert(self, point: IndicatorPoint) -> None:
        now = datetime.now(UTC)
        stmt = (
            pg_insert(IndicatorHistory)
            .values(
                codigo=point.codigo,
                data_referencia=point.data_referencia,
                valor=point.valor,
                unidade=point.unidade,
                fonte=point.fonte,
                payload_json=None,
                coletado_em=now,
            )
            .on_conflict_do_update(
                constraint="uq_indicators_history_codigo_date",
                set_={
                    "valor": point.valor,
                    "unidade": point.unidade,
                    "fonte": point.fonte,
                    "coletado_em": now,
                },
            )
        )
        await self._s.execute(stmt)

    async def latest(self, codigo: str) -> IndicatorOut | None:
        row = await self._s.scalar(
            select(IndicatorHistory)
            .where(IndicatorHistory.codigo == codigo)
            .order_by(IndicatorHistory.data_referencia.desc())
            .limit(1)
        )
        if row is None:
            return None
        coletado_em = row.coletado_em
        if coletado_em.tzinfo is None:
            coletado_em = coletado_em.replace(tzinfo=UTC)
        age_h = (datetime.now(UTC) - coletado_em).total_seconds() / 3600
        stale = age_h > MAX_AGE_HOURS.get(codigo, 26)

        unidade = row.unidade
        if codigo == "TX_BACEN_VEIC":
            unidade = "pct_aa"

        valor_d, unidade_d, label_d = _compute_derived(codigo, Decimal(str(row.valor)))

        return IndicatorOut(
            codigo=row.codigo,
            valor=row.valor,
            unidade=unidade,
            fonte=row.fonte,
            data_referencia=row.data_referencia,
            coletado_em=coletado_em,
            stale=stale,
            valor_derivado=valor_d,
            unidade_derivada=unidade_d,
            label_derivada=label_d,
        )

    async def latest_all(self) -> list[IndicatorOut]:
        results = [await self.latest(c) for c in CANONICAL_CODIGOS]
        return [r for r in results if r is not None]

    async def series(self, codigo: str, range_str: str) -> list[SeriesPoint]:
        months = VALID_RANGES.get(range_str)
        if months is None:
            raise AppError(
                f"Invalid range '{range_str}'. Valid: {list(VALID_RANGES)}"
            )
        since = date.today() - timedelta(days=months * 31)
        rows = (
            await self._s.scalars(
                select(IndicatorHistory)
                .where(
                    IndicatorHistory.codigo == codigo,
                    IndicatorHistory.data_referencia >= since,
                )
                .order_by(IndicatorHistory.data_referencia.asc())
            )
        ).all()
        return [SeriesPoint(data_referencia=r.data_referencia, valor=r.valor) for r in rows]
