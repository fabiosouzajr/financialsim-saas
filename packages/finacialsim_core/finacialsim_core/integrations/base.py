"""Provider protocol, Result type, and ProviderChain."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, Protocol, TypeVar, runtime_checkable

T = TypeVar("T")


@dataclass(frozen=True)
class Ok(Generic[T]):
    value: T
    is_ok: bool = True
    is_err: bool = False


@dataclass(frozen=True)
class Err:
    error: str
    is_ok: bool = False
    is_err: bool = True


Result = Ok[T] | Err  # type: ignore[valid-type]


@runtime_checkable
class Provider(Protocol):
    name: str

    async def fetch(self, query: dict[str, Any]) -> "Ok[Any] | Err": ...


class ProviderChain:
    """Try each provider in order; first Ok wins."""

    def __init__(self, providers: list[Provider]) -> None:
        if not providers:
            raise ValueError("ProviderChain requires at least one provider")
        self.providers = providers

    async def fetch(self, query: dict[str, Any]) -> "Ok[Any] | Err":
        last_error = "no providers"
        for p in self.providers:
            result = await p.fetch(query)
            if result.is_ok:
                return result
            last_error = result.error  # type: ignore[union-attr]
        return Err(f"all_providers_failed: {last_error}")
