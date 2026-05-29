"""CurrencyInput - NiceGUI input with R$ formatting."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Callable

from nicegui import ui

from app.utils.br_format import format_brl, parse_brl


class CurrencyInput:
    def __init__(
        self,
        label: str,
        value: Decimal = Decimal("0"),
        on_change: Callable[[Decimal], None] | None = None,
    ) -> None:
        self._value = value
        self._on_change = on_change
        self.input = ui.input(label=label, value=format_brl(value)).props("clearable")
        self.input.on("blur", self._format)
        self.input.on("change", self._on_input_change)

    def _format(self) -> None:
        try:
            self._value = parse_brl(self.input.value or "0")
        except (InvalidOperation, ValueError):
            self._value = Decimal("0")
        self.input.value = format_brl(self._value)
        if self._on_change:
            self._on_change(self._value)

    def _on_input_change(self) -> None:
        # Light validation during typing - actual normalization on blur
        pass

    @property
    def value(self) -> Decimal:
        try:
            return parse_brl(self.input.value or "0")
        except (InvalidOperation, ValueError):
            return Decimal("0")

    @value.setter
    def value(self, v: Decimal) -> None:
        self._value = v
        self.input.value = format_brl(v)