from datetime import date, timezone
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


async def test_selic_latest_has_monthly_derived(session: AsyncSession):
    svc = IndicatorsService(session)
    await svc.upsert(IndicatorPoint(
        codigo="SELIC",
        data_referencia=date(2026, 6, 1),
        valor=Decimal("10.50"),
        unidade="pct_aa",
        fonte="bacen_sgs",
    ))
    await session.commit()

    result = await svc.latest("SELIC")
    assert result is not None
    assert result.unidade == "pct_aa"
    assert result.valor_derivado is not None
    assert result.unidade_derivada == "pct_am"
    assert result.label_derivada == "% a.m."
    # 10.50% annual → ~0.835% monthly
    monthly = float(result.valor_derivado)
    assert 0.80 < monthly < 0.90


async def test_cdi_latest_has_30d_accumulated(session: AsyncSession):
    svc = IndicatorsService(session)
    await svc.upsert(IndicatorPoint(
        codigo="CDI",
        data_referencia=date(2026, 6, 1),
        valor=Decimal("0.0521"),  # % a.d.
        unidade="pct_ad",
        fonte="bacen_sgs",
    ))
    await session.commit()

    result = await svc.latest("CDI")
    assert result is not None
    assert result.valor_derivado is not None
    assert result.unidade_derivada == "pct_30d"
    assert result.label_derivada == "% (30d)"
    # 0.0521% daily → ~1.57% accumulated over 30 days
    accum = float(result.valor_derivado)
    assert 1.4 < accum < 1.7


async def test_ipca_latest_has_no_derived(session: AsyncSession):
    svc = IndicatorsService(session)
    await svc.upsert(IndicatorPoint(
        codigo="IPCA",
        data_referencia=date(2026, 6, 1),
        valor=Decimal("4.14"),
        unidade="pct_12m",
        fonte="bacen_sgs",
    ))
    await session.commit()

    result = await svc.latest("IPCA")
    assert result is not None
    assert result.unidade == "pct_12m"
    assert result.valor_derivado is None
    assert result.unidade_derivada is None
    assert result.label_derivada is None


async def test_tx_bacen_veic_unit_normalized_and_has_monthly_derived(session: AsyncSession):
    svc = IndicatorsService(session)
    # Insert with old (wrong) unit pct_am — simulates existing DB rows
    await svc.upsert(IndicatorPoint(
        codigo="TX_BACEN_VEIC",
        data_referencia=date(2026, 6, 1),
        valor=Decimal("17.00"),
        unidade="pct_am",  # old wrong unit — should be normalized to pct_aa at read time
        fonte="bacen_sgs",
    ))
    await session.commit()

    result = await svc.latest("TX_BACEN_VEIC")
    assert result is not None
    assert result.unidade == "pct_aa"  # normalized at read time
    assert result.valor_derivado is not None
    assert result.unidade_derivada == "pct_am"
    assert result.label_derivada == "% a.m."
    # 17.00% annual → ~1.31% monthly
    monthly = float(result.valor_derivado)
    assert 1.25 < monthly < 1.40
