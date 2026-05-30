import json
from decimal import Decimal
from finacialsim_saas.schemas.types import DecimalStr
from pydantic import BaseModel


def test_decimal_str_serializes_as_string():
    class M(BaseModel):
        v: DecimalStr

    m = M(v=Decimal("1234.56"))
    data = json.loads(m.model_dump_json())
    assert data["v"] == "1234.56"
    assert isinstance(data["v"], str)


def test_decimal_str_parses_from_string():
    class M(BaseModel):
        v: DecimalStr

    m = M(v="99.99")
    assert m.v == Decimal("99.99")
    assert isinstance(m.v, Decimal)


def test_simulation_create_validates_required_fields():
    from finacialsim_saas.schemas.simulations import SimulationCreate
    import pytest
    with pytest.raises(Exception):
        SimulationCreate()  # missing required fields


def test_fee_in_schema():
    from finacialsim_saas.schemas.simulations import FeeIn
    fee = FeeIn(nome="Tarifa cadastro", valor="150.00", incluir_no_principal=True)
    assert fee.valor == __import__("decimal").Decimal("150.00")


def test_extra_in_schema():
    from finacialsim_saas.schemas.simulations import ExtraIn
    extra = ExtraIn(
        tipo="protecao", nome="Proteção Veicular", valor_total="100.00",
        modalidade="mensal_continuo", duracao_meses=24, ordem=1,
    )
    assert extra.modalidade == "mensal_continuo"


def test_business_rules_out_has_all_14_keys():
    from finacialsim_saas.schemas.business_rules import BusinessRulesOut
    fields = set(BusinessRulesOut.model_fields.keys())
    required = {
        "entrada_minima_pct", "prazo_minimo_meses", "prazo_maximo_meses",
        "taxa_minima_mes", "taxa_maxima_mes", "dias_max_carencia",
        "valor_minimo_financiado", "iof_fixo_pct", "iof_diario_pct",
        "iof_diario_max_dias", "incluir_iof_default",
        "rateio_ipva_meses_default", "rateio_emplacamento_meses_default",
        "taxa_por_prazo_curva",
    }
    assert required.issubset(fields)
