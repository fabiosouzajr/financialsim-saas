from __future__ import annotations

import inspect
from datetime import date

from finacialsim_saas.pix.protocol import PayerInfo, PixProvider


def test_payer_info_fields():
    payer = PayerInfo(document="12345678909", document_type="cpf", name="Maria Silva")
    assert payer.document == "12345678909"
    assert payer.document_type == "cpf"
    assert payer.name == "Maria Silva"


def test_create_charge_uses_date_based_due_date_and_validity_days():
    sig = inspect.signature(PixProvider.create_charge)
    assert "due_date" in sig.parameters
    assert "validity_days" in sig.parameters
    assert "expires_in" not in sig.parameters
    # protocol.py uses `from __future__ import annotations` so annotations are strings
    assert sig.parameters["due_date"].annotation == "date"
    assert sig.parameters["validity_days"].annotation == "int"


def test_create_charge_accepts_optional_payer_info():
    sig = inspect.signature(PixProvider.create_charge)
    assert sig.parameters["payer"].annotation == "PayerInfo | None"


def test_verify_webhook_signature_has_query_params():
    sig = inspect.signature(PixProvider.verify_webhook)
    assert list(sig.parameters) == ["self", "headers", "query_params", "body"]
