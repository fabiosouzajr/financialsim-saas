"""KPI card - label + big value + optional secondary text + hide toggle."""

from __future__ import annotations

from nicegui import ui


class KpiCard:
    def __init__(self, label: str, value: str, secondary: str = "", compact: bool = False) -> None:
        self.visible = True
        self._real_value = value
        self._real_secondary = secondary
        card_cls = "kpi-card-compact" if compact else "kpi-card"
        value_cls = "kpi-value-compact" if compact else "kpi-value"
        with ui.card().classes(card_cls) as self.card:
            self.label_el = ui.label(label).classes("kpi-label")
            self.value_el = ui.label(value).classes(value_cls)
            self.secondary_el = ui.label(secondary).classes("kpi-label")
            with ui.row().classes("w-full justify-end"):
                self._eye_btn = ui.button(icon="visibility", on_click=self._toggle).props("flat dense")

    def _toggle(self) -> None:
        self.visible = not self.visible
        if self.visible:
            self.value_el.text = self._real_value
            self.secondary_el.text = self._real_secondary
            self._eye_btn.props("icon=visibility")
        else:
            self.value_el.text = "•••"
            self.secondary_el.text = ""
            self._eye_btn.props("icon=visibility_off")
        self.value_el.update()
        self.secondary_el.update()
        self._eye_btn.update()

    def set(self, value: str, secondary: str = "") -> None:
        self._real_value = value
        self._real_secondary = secondary
        if self.visible:
            self.value_el.text = value
            self.secondary_el.text = secondary
        self.value_el.update()
        self.secondary_el.update()
