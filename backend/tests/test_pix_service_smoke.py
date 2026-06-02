"""Smoke test — full PixService tests are in test_pix_service.py (Plan 6E)."""
import pytest


def test_pix_service_importable():
    from finacialsim_saas.pix.service import PixService
    assert PixService is not None
