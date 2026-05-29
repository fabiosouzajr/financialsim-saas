"""FinacialSim entry point - boots NiceGUI in a pywebview window."""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger
from nicegui import ui

from app.data.database import create_engine_for_sqlite
from app.ui.pages.amortizacao import build_amortizacao_page
from app.ui.pages.cadastro import build_cadastro_page
from app.ui.pages.comparativo import build_comparativo_page
from app.ui.pages.configuracoes import build_configuracoes_page
from app.ui.pages.dashboard import build_dashboard_page
from app.ui.pages.docs import build_docs_page
from app.ui.pages.veiculos import build_veiculos_page
from app.ui.pages.indicadores import build_indicadores_page
from app.ui.pages.logs import build_logs_page
from app.ui.pages.login import build_login_page
from app.ui.pages.simulacao import build_simulacao_page
from app.ui.theme import apply_global_styles
from app.utils.logger import setup_logging


def _platform_data_dir() -> Path:
    if sys.platform.startswith("win"):
        base = Path.home() / "AppData" / "Roaming" / "FinacialSim"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "FinacialSim"
    else:
        base = Path.home() / ".local" / "share" / "FinacialSim"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _run_migrations(db_path: Path) -> None:
    """Run alembic upgrade head on startup. Idempotent."""
    from alembic import command as alembic_command
    from alembic.config import Config

    # In a frozen PyInstaller app, files live under sys._MEIPASS (_internal/).
    # When running from source, they live two levels above this file.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        base = Path(meipass)
    else:
        base = Path(__file__).resolve().parents[1]

    alembic_ini = base / "alembic.ini"
    migrations_dir = base / "app" / "data" / "migrations"

    if not alembic_ini.exists():
        logger.warning("alembic.ini not found - skipping migrations")
        return

    cfg = Config(str(alembic_ini))
    cfg.set_main_option("script_location", str(migrations_dir))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    try:
        alembic_command.upgrade(cfg, "head")
        logger.info("Migrations applied (alembic upgrade head)")
    except Exception as exc:
        logger.error(f"Alembic upgrade failed: {exc}")


def build_app() -> None:
    project_root = Path(__file__).resolve().parents[1]
    setup_logging(project_root / "logs")
    db_path = project_root / "data" / "finacialsim.db"

    # Run migrations if DB is new or schema outdated
    _run_migrations(db_path)

    engine = create_engine_for_sqlite(db_path)
    apply_global_styles()

    build_login_page(engine)
    build_dashboard_page(engine)
    build_cadastro_page(engine)
    data_dir = _platform_data_dir()
    build_simulacao_page(engine, data_dir)
    build_comparativo_page(engine)
    build_amortizacao_page(engine)
    build_indicadores_page(engine)
    build_veiculos_page(engine)
    build_configuracoes_page(engine)
    build_logs_page(engine)
    build_docs_page(engine)

    @ui.page("/")
    def root() -> None:
        ui.navigate.to("/login")


def main() -> None:
    build_app()
    ui.run(
        title="FinacialSim",
        favicon="🚗",
        native=True,
        window_size=(1400, 900),
        storage_secret="finacialsim-secret-change-me",
        reload=False,
        show=False,
    )


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()
    main()