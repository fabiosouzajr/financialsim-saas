import asyncio
from typing import Annotated

import typer
from sqlalchemy import select

from finacialsim_saas.auth.service import AuthService
from finacialsim_saas.data.database import build_engine, build_session_factory
from finacialsim_saas.data.models import Role, Tenant
from finacialsim_saas.settings import get_settings

app = typer.Typer(name="finacialsim-saas", help="FinacialSim SaaS management CLI")
tenant_app = typer.Typer()
user_app = typer.Typer()
app.add_typer(tenant_app, name="tenant")
app.add_typer(user_app, name="user")


def _run(coro):
    return asyncio.run(coro)


@tenant_app.command("create")
def tenant_create(
    name: Annotated[str, typer.Option("--name")],
    slug: Annotated[str, typer.Option("--slug")],
    admin_email: Annotated[str, typer.Option("--admin-email")],
    admin_password: Annotated[str, typer.Option(
        "--admin-password", prompt=True, hide_input=True
    )],
):
    async def _create():
        settings = get_settings()
        engine = build_engine(str(settings.database_url))
        factory = build_session_factory(engine)
        async with factory() as session:
            existing = await session.execute(select(Tenant).where(Tenant.slug == slug))
            if existing.scalar_one_or_none() is not None:
                typer.echo(f"Error: tenant slug '{slug}' already exists.", err=True)
                raise typer.Exit(1)
            tenant = Tenant(name=name, slug=slug)
            session.add(tenant)
            await session.flush()
            svc = AuthService(session, settings)
            await svc.register_user(
                tenant_id=tenant.id,
                email=admin_email,
                password=admin_password,
                name=admin_email,
                role=Role.admin,
            )
            await session.commit()
            typer.echo(f"Tenant '{name}' (slug={slug}) created. Admin: {admin_email}")
        await engine.dispose()

    _run(_create())


@user_app.command("create")
def user_create(
    tenant_slug: Annotated[str, typer.Option("--tenant-slug")],
    email: Annotated[str, typer.Option("--email")],
    role: Annotated[str, typer.Option("--role")],
    password: Annotated[str, typer.Option(
        "--password", prompt=True, hide_input=True
    )],
):
    async def _create():
        settings = get_settings()
        engine = build_engine(str(settings.database_url))
        factory = build_session_factory(engine)
        async with factory() as session:
            t_result = await session.execute(
                select(Tenant).where(Tenant.slug == tenant_slug)
            )
            tenant = t_result.scalar_one_or_none()
            if tenant is None:
                typer.echo(f"Error: tenant '{tenant_slug}' not found.", err=True)
                raise typer.Exit(1)
            svc = AuthService(session, settings)
            await svc.register_user(
                tenant_id=tenant.id, email=email, password=password,
                name=email, role=Role(role),
            )
            await session.commit()
            typer.echo(f"User '{email}' ({role}) created in tenant '{tenant_slug}'.")
        await engine.dispose()

    _run(_create())


@user_app.command("reset-password")
def user_reset_password(
    tenant_slug: Annotated[str, typer.Option("--tenant-slug")],
    email: Annotated[str, typer.Option("--email")],
):
    async def _reset():
        settings = get_settings()
        engine = build_engine(str(settings.database_url))
        factory = build_session_factory(engine)
        async with factory() as session:
            svc = AuthService(session, settings)
            await svc.request_password_reset(email)
            await session.commit()
            typer.echo(f"Password reset enqueued for {email} (check dev-mail/).")
        await engine.dispose()

    _run(_reset())


if __name__ == "__main__":
    app()
