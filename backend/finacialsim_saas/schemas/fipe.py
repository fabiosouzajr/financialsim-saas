from __future__ import annotations

from pydantic import BaseModel

from finacialsim_saas.schemas.types import DecimalStr


class FipeBrandItem(BaseModel):
    id: str
    nome: str


class FipeModelItem(BaseModel):
    id: str
    nome: str


class FipeYearItem(BaseModel):
    id: str
    nome: str


class FipePriceOut(BaseModel):
    tipo: str
    marca: str
    marca_id: str
    modelo: str
    modelo_id: str
    ano_modelo: int
    combustivel: str
    codigo_fipe: str
    valor: DecimalStr
    mes_referencia: str
    fonte: str
