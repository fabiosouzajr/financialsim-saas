import pytest
from typer.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


def test_tenant_create_and_user_create(runner, engine):
    """CLI creates tenant and user in the testcontainer DB."""
    # DATABASE_URL is already set by db_url fixture (engine depends on db_url)
    from finacialsim_saas.cli.main import app

    result = runner.invoke(
        app,
        ["tenant", "create",
         "--name", "CLI Loja",
         "--slug", "cli-loja",
         "--admin-email", "cli-admin@loja.com",
         "--admin-password", "cli-pass123"],
    )
    assert result.exit_code == 0, result.output
    assert "created" in result.output.lower()

    result2 = runner.invoke(
        app,
        ["user", "create",
         "--tenant-slug", "cli-loja",
         "--email", "cli-user@loja.com",
         "--role", "user",
         "--password", "userpass"],
    )
    assert result2.exit_code == 0, result2.output


def test_db_migrate_runs_without_error(runner):
    from finacialsim_saas.cli.main import app
    result = runner.invoke(app, ["db", "migrate"])
    assert result.exit_code == 0, result.output
    assert "migrate" in result.output.lower() or "head" in result.output.lower()


def test_db_reset_requires_confirm_flag(runner):
    from finacialsim_saas.cli.main import app
    result = runner.invoke(app, ["db", "reset"])
    assert result.exit_code != 0
    assert "confirm" in result.output.lower() or result.exit_code == 1


def test_notifications_drain_runs_without_error(runner):
    from finacialsim_saas.cli.main import app
    result = runner.invoke(app, ["notifications", "drain"])
    assert result.exit_code == 0, result.output


def test_notifications_retry_unknown_id(runner):
    import uuid
    from finacialsim_saas.cli.main import app
    bad_id = str(uuid.uuid4())
    result = runner.invoke(app, ["notifications", "retry", "--outbox-id", bad_id])
    assert result.exit_code != 0 or "not found" in result.output.lower()
