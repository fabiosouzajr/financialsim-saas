from decimal import Decimal
from typing import Annotated

from pydantic import BeforeValidator, PlainSerializer

DecimalStr = Annotated[
    Decimal,
    BeforeValidator(lambda v: Decimal(str(v)) if not isinstance(v, Decimal) else v),
    PlainSerializer(lambda v: str(v), return_type=str),
]
