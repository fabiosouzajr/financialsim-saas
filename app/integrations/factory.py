"""Composition helpers — build default provider chains."""

from __future__ import annotations

from app.integrations.bacen.brasilapi import BrasilApiBacenProvider
from app.integrations.bacen.cached import CachedBacenProvider
from app.integrations.bacen.sgs import BcbSgsProvider
from app.integrations.base import ProviderChain
from app.integrations.fipe.brasilapi import BrasilApiFipeProvider
from app.integrations.fipe.cache import CachedFipeProvider
from app.integrations.fipe.parallelum import ParallelumFipeProvider


def build_fipe_chain(
    session_factory,
    listas_ttl_horas: int = 720,
    preco_ttl_horas: int = 24,
) -> ProviderChain:
    """Parallelum (primary) → BrasilAPI (fallback), both with cache."""
    parallelum = CachedFipeProvider(
        ParallelumFipeProvider(),
        session_factory,
        listas_ttl_horas=listas_ttl_horas,
        preco_ttl_horas=preco_ttl_horas,
    )
    brasilapi = CachedFipeProvider(
        BrasilApiFipeProvider(),
        session_factory,
        listas_ttl_horas=listas_ttl_horas,
        preco_ttl_horas=preco_ttl_horas,
    )
    return ProviderChain([parallelum, brasilapi])


def build_bacen_chain(session_factory, ttl_horas: int = 24) -> ProviderChain:
    """SGS (primary) → BrasilAPI (fallback), both with cache."""
    sgs = CachedBacenProvider(BcbSgsProvider(), session_factory, ttl_horas=ttl_horas)
    brasil = CachedBacenProvider(BrasilApiBacenProvider(), session_factory, ttl_horas=ttl_horas)
    return ProviderChain([sgs, brasil])
