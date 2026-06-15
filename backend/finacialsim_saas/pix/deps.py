from __future__ import annotations

from pathlib import Path

from finacialsim_saas.pix.efi import EfiPixProvider
from finacialsim_saas.pix.fake import InMemoryFakePixProvider
from finacialsim_saas.pix.protocol import PixProvider
from finacialsim_saas.settings import Settings

# Cached singleton for the `efi` branch — EfiPixProvider.__init__ authenticates with Efí's
# OAuth2 token endpoint on construction; constructing per-request would multiply auth calls.
# Not lru_cache on get_pix_provider itself — that would wrongly cache fake across test settings.
_efi_provider: EfiPixProvider | None = None


def _validate_efi_settings(settings: Settings) -> None:
    missing = [
        name for name, value in (
            ("EFI_CLIENT_ID", settings.efi_client_id),
            ("EFI_CLIENT_SECRET", settings.efi_client_secret),
            ("EFI_CERTIFICATE_PATH", settings.efi_certificate_path),
            ("EFI_PIX_KEY", settings.efi_pix_key),
        )
        if not value
    ]
    if missing:
        raise ValueError(f"PIX_PROVIDER=efi requires {', '.join(missing)} to be set")
    if not Path(settings.efi_certificate_path).exists():
        raise ValueError(f"EFI_CERTIFICATE_PATH does not exist: {settings.efi_certificate_path}")


def get_pix_provider(settings: Settings) -> PixProvider:
    global _efi_provider
    if settings.pix_provider == "fake":
        return InMemoryFakePixProvider(secret=settings.pix_webhook_secret)
    if settings.pix_provider == "efi":
        if _efi_provider is None:
            _validate_efi_settings(settings)
            _efi_provider = EfiPixProvider(settings)
        return _efi_provider
    raise ValueError(f"Unknown PIX_PROVIDER: {settings.pix_provider!r}")
