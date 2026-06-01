from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from finacialsim_saas.integrations.bacen.schema import IndicatorPoint
from finacialsim_saas.services.indicators_service import IndicatorsService

UTC = timezone.utc


async def test_upsert_and_latest(session: AsyncSession):
    svc = IndicatorsService(session)
    point = IndicatorPoint(
        codigo="SELIC",
        data_referencia=date(2026, 6, 1),
        valor=Decimal("10.75"),
        unidade="pct_aa",
        fonte="bacen_sgs",
    )
    await svc.upsert(point)
    await session.commit()

    result = await svc.latest("SELIC")
    assert result is not None
    assert result.valor == "10.75"
    assert result.codigo == "SELIC"
    assert result.stale is False  # just inserted


async def test_upsert_idempotent(session: AsyncSession):
    svc = IndicatorsService(session)
    point = IndicatorPoint(
        codigo="CDI",
        data_referencia=date(2026, 6, 1),
        valor=Decimal("10.65"),
        unidade="pct_ad",
        fonte="bacen_sgs",
    )
    await svc.upsert(point)
    await session.commit()

    updated = IndicatorPoint(
        codigo="CDI",
        data_referencia=date(2026, 6, 1),
        valor=Decimal("10.70"),
        unidade="pct_ad",
        fonte="bacen_sgs",
    )
    await svc.upsert(updated)
    await session.commit()

    result = await svc.latest("CDI")
    assert result is not None
    assert result.valor == "10.70"


async def test_series_returns_ordered_points(session: AsyncSession):
    svc = IndicatorsService(session)
    for i in range(1, 4):
        await svc.upsert(IndicatorPoint(
            codigo="IPCA",
            data_referencia=date(2026, i, 1),
            valor=Decimal(f"4.{i}"),
            unidade="pct_am",
            fonte="bacen_sgs",
        ))
    await session.commit()

    points = await svc.series("IPCA", "12m")
    assert len(points) >= 3
    assert points[0].data_referencia <= points[-1].data_referencia


async def test_series_invalid_range_raises(session: AsyncSession):
    from finacialsim_saas.errors import AppError
    svc = IndicatorsService(session)
    with pytest.raises(AppError):
        await svc.series("SELIC", "99y")


async def test_latest_missing_returns_none(session: AsyncSession):
    svc = IndicatorsService(session)
    result = await svc.latest("NONEXISTENT")
    assert result is None
