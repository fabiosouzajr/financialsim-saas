from __future__ import annotations

from finacialsim_saas.settings import Settings


def _settings(**overrides) -> Settings:
    base: dict = dict(
        database_url="postgresql+asyncpg://u:p@localhost/db",  # type: ignore[arg-type]
        pix_provider="efi", app_env="production", efi_sandbox=True,
    )
    base.update(overrides)
    return Settings(**base)


def test_pix_sandbox_warning_fires_for_efi_sandbox_in_production():
    from finacialsim_saas.main import _pix_sandbox_warning

    warning = _pix_sandbox_warning(_settings())
    assert warning is not None
    assert "sandbox" in warning.lower()


def test_pix_sandbox_warning_silent_outside_efi_sandbox_production_combo():
    from finacialsim_saas.main import _pix_sandbox_warning

    assert _pix_sandbox_warning(_settings(app_env="development")) is None
    assert _pix_sandbox_warning(_settings(efi_sandbox=False)) is None
    assert _pix_sandbox_warning(_settings(pix_provider="fake")) is None
