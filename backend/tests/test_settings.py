import pytest
from finacialsim_saas.settings import Settings


def test_settings_loads_with_valid_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/db")
    s = Settings()
    assert s.app_env == "development"
    assert s.git_sha == "dev"
    assert s.pdf_output_dir == "/tmp/finacialsim-pdfs"


def test_settings_missing_database_url_raises(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(Exception):
        Settings(_env_file=None)  # type: ignore[call-arg]
