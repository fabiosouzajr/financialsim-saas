from __future__ import annotations


from finacialsim_core.integrations.base import ProviderChain
from finacialsim_core.integrations.fipe.brasilapi import BrasilApiFipeProvider
from finacialsim_core.integrations.fipe.parallelum import ParallelumFipeProvider
from finacialsim_core.integrations.fipe.schema import VehicleQuote
from finacialsim_saas.errors import ExternalProviderError
from finacialsim_saas.services.fipe_cache import PostgresFipeCache


def build_fipe_chain(
    session_factory,
    listas_ttl_horas: int = 720,
    preco_ttl_horas: int = 24,
) -> ProviderChain:
    parallelum = PostgresFipeCache(
        ParallelumFipeProvider(),
        session_factory,
        listas_ttl_horas=listas_ttl_horas,
        preco_ttl_horas=preco_ttl_horas,
    )
    brasilapi = PostgresFipeCache(
        BrasilApiFipeProvider(),
        session_factory,
        listas_ttl_horas=listas_ttl_horas,
        preco_ttl_horas=preco_ttl_horas,
    )
    return ProviderChain([parallelum, brasilapi])


class FipeService:
    def __init__(self, chain: ProviderChain) -> None:
        self._chain = chain

    async def get_brands(self, tipo: str) -> list[dict]:
        result = await self._chain.fetch({"action": "brands", "tipo": tipo})
        if result.is_err:
            raise ExternalProviderError(f"FIPE brands unavailable: {result.error}")
        return result.value

    async def get_models(self, tipo: str, brand_id: str) -> list[dict]:
        result = await self._chain.fetch(
            {"action": "models", "tipo": tipo, "brand_id": brand_id}
        )
        if result.is_err:
            raise ExternalProviderError(f"FIPE models unavailable: {result.error}")
        return result.value

    async def get_years(self, tipo: str, brand_id: str, model_id: str) -> list[dict]:
        result = await self._chain.fetch(
            {"action": "years", "tipo": tipo, "brand_id": brand_id, "model_id": model_id}
        )
        if result.is_err:
            raise ExternalProviderError(f"FIPE years unavailable: {result.error}")
        return result.value

    async def get_price(
        self, tipo: str, brand_id: str, model_id: str, year_id: str
    ) -> VehicleQuote:
        result = await self._chain.fetch(
            {
                "action": "price",
                "tipo": tipo,
                "brand_id": brand_id,
                "model_id": model_id,
                "year_id": year_id,
            }
        )
        if result.is_err:
            raise ExternalProviderError(f"FIPE price unavailable: {result.error}")
        return result.value
