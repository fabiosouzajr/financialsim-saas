from __future__ import annotations

import pytest

from finacialsim_saas.pix import deps as pix_deps
from finacialsim_saas.settings import Settings


def _settings(**overrides) -> Settings:
    base: dict = dict(
        database_url="postgresql+asyncpg://u:p@localhost/db",  # type: ignore[arg-type]
        pix_provider="fake",
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture(autouse=True)
def _reset_efi_singleton(monkeypatch):
    monkeypatch.setattr(pix_deps, "_efi_provider", None)


def test_external_provider_value_no_longer_supported():
    """Selector rename fake|external → fake|efi (spec §5) — "external" must now raise."""
    with pytest.raises(ValueError, match="Unknown PIX_PROVIDER"):
        pix_deps.get_pix_provider(_settings(pix_provider="external"))


def test_efi_provider_requires_settings_to_be_set():
    settings = _settings(
        pix_provider="efi",
        efi_client_id="", efi_client_secret="x", efi_certificate_path="/no/file", efi_pix_key="key",
    )
    with pytest.raises(ValueError, match="EFI_CLIENT_ID"):
        pix_deps.get_pix_provider(settings)


def test_efi_provider_requires_certificate_file_to_exist():
    settings = _settings(
        pix_provider="efi",
        efi_client_id="id", efi_client_secret="secret",
        efi_certificate_path="/no/such/file.pem", efi_pix_key="key",
    )
    with pytest.raises(ValueError, match="does not exist"):
        pix_deps.get_pix_provider(settings)


def test_efi_provider_is_cached_as_singleton(monkeypatch, tmp_path):
    cert = tmp_path / "efi.pem"
    cert.write_text("cert")
    settings = _settings(
        pix_provider="efi",
        efi_client_id="id", efi_client_secret="secret",
        efi_certificate_path=str(cert), efi_pix_key="key",
    )

    constructed = []

    class _FakeEfiProvider:
        name = "efi"

        def __init__(self, settings):
            constructed.append(settings)

    monkeypatch.setattr(pix_deps, "EfiPixProvider", _FakeEfiProvider)

    first = pix_deps.get_pix_provider(settings)
    second = pix_deps.get_pix_provider(settings)

    assert first is second
    assert len(constructed) == 1
