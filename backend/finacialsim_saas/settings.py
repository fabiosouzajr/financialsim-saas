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


def get_settings() -> Settings:
    return Settings()
