from __future__ import annotations

from finacialsim_saas.pix.fake import InMemoryFakePixProvider
from finacialsim_saas.pix.protocol import PixProvider
from finacialsim_saas.pix.stub import StubExternalPixProvider
from finacialsim_saas.settings import Settings


def get_pix_provider(settings: Settings) -> PixProvider:
    if settings.pix_provider == "fake":
        return InMemoryFakePixProvider(secret=settings.pix_webhook_secret)
    if settings.pix_provider == "external":
        return StubExternalPixProvider()
    raise ValueError(f"Unknown PIX_PROVIDER: {settings.pix_provider!r}")
