import asyncio
from pathlib import Path

import typer

db_app = typer.Typer(help="Database management commands")


def _alembic_config():
    from alembic.config import Config
    script_location = Path(__file__).parent.parent.parent / "alembic"
    from finacialsim_saas.settings import get_settings
    cfg = Config()
    cfg.set_main_option("script_location", str(script_location))
    cfg.set_main_option(
        "sqlalchemy.url",
        str(get_settings().database_url).replace("+asyncpg", ""),
    )
    return cfg


@db_app.command("migrate")
def db_migrate():
    """Run Alembic upgrade head."""
    from alembic import command as alembic_command
    alembic_command.upgrade(_alembic_config(), "head")
    typer.echo("Database migrated to head.")


@db_app.command("reset")
def db_reset(
    confirm: bool = typer.Option(False, "--confirm", help="Required to actually reset"),
):
    """Drop all tables and re-run migrations. Dev only."""
    from finacialsim_saas.settings import get_settings

    settings = get_settings()
    if settings.app_env == "production":
        typer.echo("Error: db reset is not allowed in production.", err=True)
        raise typer.Exit(1)
    if not confirm:
        typer.echo("Error: pass --confirm to actually reset the database.", err=True)
        raise typer.Exit(1)

    async def _reset():
        from finacialsim_saas.data.database import build_engine
        from sqlalchemy import text
        engine = build_engine(str(settings.database_url))
        async with engine.begin() as conn:
            await conn.execute(text("DROP SCHEMA public CASCADE"))
            await conn.execute(text("CREATE SCHEMA public"))
        await engine.dispose()

    asyncio.run(_reset())

    from alembic import command as alembic_command
    alembic_command.upgrade(_alembic_config(), "head")
    typer.echo("Database reset and migrated to head.")
