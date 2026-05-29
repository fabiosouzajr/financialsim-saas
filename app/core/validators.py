"""Business rule validations for simulation inputs."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class ValidationLevel(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class ValidationIssue:
    level: ValidationLevel
    field: str
    message: str


@dataclass(frozen=True)
class ValidationRules:
    entrada_minima_pct: Decimal
    prazo_minimo_meses: int
    prazo_maximo_meses: int
    taxa_minima_mes: Decimal
    taxa_maxima_mes: Decimal
    dias_max_carencia: int
    valor_minimo_financiado: Decimal


DEFAULT_RULES = ValidationRules(
    entrada_minima_pct=Decimal("0.10"),
    prazo_minimo_meses=12,
    prazo_maximo_meses=72,
    taxa_minima_mes=Decimal("0.005"),
    taxa_maxima_mes=Decimal("0.05"),
    dias_max_carencia=90,
    valor_minimo_financiado=Decimal("5000"),
)


@dataclass(frozen=True)
class SimulationInput:
    valor_veiculo: Decimal
    valor_entrada: Decimal
    prazo_meses: int
    taxa_mensal: Decimal
    dias_carencia: int


def validate_simulation(
    input_data: SimulationInput, rules: ValidationRules
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    if input_data.valor_veiculo <= 0:
        issues.append(
            ValidationIssue(
                ValidationLevel.ERROR, "valor_veiculo", "Valor do veiculo deve ser maior que zero"
            )
        )
        return issues

    pct_entrada = input_data.valor_entrada / input_data.valor_veiculo
    if pct_entrada < rules.entrada_minima_pct:
        issues.append(
            ValidationIssue(
                ValidationLevel.ERROR,
                "valor_entrada",
                f"Entrada minima: {rules.entrada_minima_pct * 100}%"
                f" (atual: {pct_entrada * 100:.1f}%)",
            )
        )

    if (
        input_data.prazo_meses < rules.prazo_minimo_meses
        or input_data.prazo_meses > rules.prazo_maximo_meses
    ):
        issues.append(
            ValidationIssue(
                ValidationLevel.ERROR,
                "prazo_meses",
                f"Prazo deve estar entre {rules.prazo_minimo_meses}"
                f" e {rules.prazo_maximo_meses} meses",
            )
        )

    # taxa_minima is WARNING (not ERROR): low rates are unusual but mathematically valid
    if input_data.taxa_mensal < rules.taxa_minima_mes:
        issues.append(
            ValidationIssue(
                ValidationLevel.WARNING,
                "taxa_mensal",
                f"Taxa abaixo do minimo usual: {rules.taxa_minima_mes * 100}% a.m.",
            )
        )
    elif input_data.taxa_mensal > rules.taxa_maxima_mes:
        issues.append(
            ValidationIssue(
                ValidationLevel.ERROR,
                "taxa_mensal",
                f"Taxa acima do maximo: {rules.taxa_maxima_mes * 100}% a.m.",
            )
        )

    if input_data.dias_carencia > rules.dias_max_carencia:
        issues.append(
            ValidationIssue(
                ValidationLevel.ERROR,
                "dias_carencia",
                f"Carencia maxima: {rules.dias_max_carencia} dias",
            )
        )

    valor_financiado = input_data.valor_veiculo - input_data.valor_entrada
    if valor_financiado < rules.valor_minimo_financiado:
        issues.append(
            ValidationIssue(
                ValidationLevel.ERROR,
                "valor_financiado",
                f"Valor financiado minimo: R$ {rules.valor_minimo_financiado}",
            )
        )

    return issues
