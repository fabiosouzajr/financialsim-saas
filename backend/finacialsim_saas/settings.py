from typing import Literal

from pydantic import PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    database_url: PostgresDsn

    redis_url: RedisDsn = "redis://localhost:6379/0"  # type: ignore[assignment]

    app_env: Literal["development", "production", "test"] = "development"
    app_secret_key: str = "change-me-in-production"

    git_sha: str = "dev"
    build_time: str = ""

    pdf_output_dir: str = "/tmp/finacialsim-pdfs"

    jwt_secret_key: str = "change-jwt-secret-in-production"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    frontend_base_url: str = "http://localhost:5173"
    maildir_path: str = "./dev-mail"

    storage_backend: str = "local"
    storage_local_root: str = "./storage"
    storage_hmac_secret: str = "change-storage-secret-in-production"
    storage_base_url: str = "http://localhost:8000"

    pix_provider: str = "fake"
    pix_webhook_secret: str = ""

    # Email delivery
    email_provider: str = "smtp"  # smtp | ses | resend
    smtp_host: str = "localhost"
    smtp_port: int = 1025          # Mailpit default
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_tls: bool = False
    smtp_from: str = "noreply@finacialsim.local"

    max_emails_per_tenant_per_hour: int = 1000  # enforcement deferred to v2


def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
