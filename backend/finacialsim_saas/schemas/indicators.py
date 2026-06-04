from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, BeforeValidator


def _to_decimal_str(v: object) -> str:
    """Normalize Decimal to string, stripping trailing zeros beyond 2 decimal places.

    Examples: Decimal('10.750000') → '10.75', Decimal('10.700000') → '10.70'
    """
    if isinstance(v, str):
        return v
    d = Decimal(str(v)) if not isinstance(v, Decimal) else v
    # Format with full precision then rstrip zeros, keeping at least 2 decimal places.
    s = format(d, "f")  # fixed-point, no scientific notation
    if "." in s:
        integer_part, frac_part = s.split(".")
        frac_part = frac_part.rstrip("0").ljust(2, "0")
        return f"{integer_part}.{frac_part}"
    return s


# Coerces Decimal/str/int to normalized str at construction time so attribute access returns str.
_DecimalAsStr = Annotated[str, BeforeValidator(_to_decimal_str)]


class IndicatorOut(BaseModel):
    codigo: str
    valor: _DecimalAsStr
    unidade: str
    fonte: str
    data_referencia: date
    coletado_em: datetime
    stale: bool
    valor_derivado: _DecimalAsStr | None = None
    unidade_derivada: str | None = None
    label_derivada: str | None = None


class SeriesPoint(BaseModel):
    data_referencia: date
    valor: _DecimalAsStr


class SeriesOut(BaseModel):
    codigo: str
    range: str
    points: list[SeriesPoint]
