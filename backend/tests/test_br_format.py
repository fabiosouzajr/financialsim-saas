import pytest
from decimal import Decimal
from datetime import date

from finacialsim_saas.utils.br_format import (
    format_brl, format_pct, format_date_br, format_cpf_cnpj,
)


def test_format_brl_basic():
    assert format_brl(Decimal("1234.56")) == "R$ 1.234,56"

def test_format_brl_negative():
    assert format_brl(Decimal("-100.00")) == "-R$ 100,00"

def test_format_brl_large():
    assert format_brl(Decimal("1000000.00")) == "R$ 1.000.000,00"

def test_format_pct_default():
    assert format_pct(Decimal("0.0189")) == "1,89%"

def test_format_pct_4_decimals():
    assert format_pct(Decimal("0.01290"), 4) == "1,2900%"

def test_format_date_br():
    assert format_date_br(date(2026, 6, 1)) == "01/06/2026"

def test_format_cpf_pf():
    assert format_cpf_cnpj("12345678909", "PF") == "123.456.789-09"

def test_format_cpf_pj():
    assert format_cpf_cnpj("12345678000195", "PJ") == "12.345.678/0001-95"

def test_format_cpf_invalid_passthrough():
    assert format_cpf_cnpj("123", "PF") == "123"
