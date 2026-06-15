from __future__ import annotations

import asyncio

import typer

from finacialsim_saas.pix.efi import EfiPixProvider
from finacialsim_saas.settings import get_settings

pix_app = typer.Typer(help="Pix PSP management commands")


@pix_app.command("register-webhook")
def pix_register_webhook():
    """Registers (or re-registers) the Pix webhook callback URL with Efí. Idempotent (PUT)."""
    settings = get_settings()
    if settings.pix_provider != "efi":
        typer.echo("Error: PIX_PROVIDER is not 'efi'.", err=True)
        raise typer.Exit(1)

    url = (
        f"{settings.frontend_base_url}/api/v1/webhooks/pix"
        f"?hmac={settings.pix_webhook_secret}&ignorar="
    )

    async def _register():
        provider = EfiPixProvider(settings)
        await provider.register_webhook(url)

    asyncio.run(_register())
    typer.echo(f"Webhook registered: {url}")
