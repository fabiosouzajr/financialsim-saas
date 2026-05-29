"""PercentInput - input as % (display) -> Decimal fraction (model)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Callable

from nicegui import ui


def _parse(text: str) -> Decimal:
    cleaned = text.replace("%", "").replace(",", ".").strip()
    return Decimal(cleaned) / Decimal("100")


class PercentInput:
    def __init__(
        self,
        label: str,
        value: Decimal = Decimal("0"),
        decimals: int = 2,
        on_change: Callable[[Decimal], None] | None = None,
    ) -> None:
        self._value = value
        self.decimals = decimals
        self._on_change = on_change
        self.input = ui.input(label=label, value=self._format(value)).props("clearable")
        self.input.on("blur", self._fmt)

    def _format(self, v: Decimal) -> str:
        s = f"{v * Decimal('100'):.{self.decimals}f}".replace(".", ",")
        return f"{s}%"

    def _fmt(self) -> None:
        try:
            self._value = _parse(self.input.value or "0")
        except (InvalidOperation, ValueError):
            self._value = Decimal("0")
        self.input.value = self._format(self._value)
        if self._on_change:
            self._on_change(self._value)

    @property
    def value(self) -> Decimal:
        try:
            return _parse(self.input.value or "0")
        except (InvalidOperation, ValueError):
            return Decimal("0")

    @value.setter
    def value(self, v: Decimal) -> None:
        self._value = v
        self.input.value = self._format(v)