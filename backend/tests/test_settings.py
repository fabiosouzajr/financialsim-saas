import pytest
from finacialsim_saas.settings import Settings


def test_settings_loads_with_valid_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("PDF_OUTPUT_DIR", "/tmp/finacialsim-pdfs")
    s = Settings()
    assert s.app_env == "development"
    assert s.git_sha == "dev"
    assert s.pdf_output_dir == "/tmp/finacialsim-pdfs"


def test_settings_missing_database_url_raises(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(Exception):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_settings_has_jwt_and_phase1_fields(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret")
    # Force reload to pick up new env
    import importlib
    import finacialsim_saas.settings as _m
    importlib.reload(_m)
    s = _m.Settings()
    assert s.jwt_secret_key == "test-jwt-secret"
    assert s.access_token_expire_minutes == 15
    assert s.refresh_token_expire_days == 7
    assert s.frontend_base_url == "http://localhost:5173"


def test_settings_has_efi_pix_fields(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    s = Settings()
    assert s.efi_client_id == ""
    assert s.efi_client_secret == ""
    assert s.efi_certificate_path == ""
    assert s.efi_pix_key == ""
    assert s.efi_sandbox is True
