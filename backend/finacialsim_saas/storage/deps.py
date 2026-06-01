"""Build storage backend from settings."""
from __future__ import annotations

from pathlib import Path

from finacialsim_saas.settings import Settings
from finacialsim_saas.storage import StorageBackend
from finacialsim_saas.storage.local import LocalVolumeBackend


def get_storage_backend(settings: Settings) -> StorageBackend:
    if settings.storage_backend == "local":
        return LocalVolumeBackend(
            root=Path(settings.storage_local_root),
            secret=settings.storage_hmac_secret,
            base_url=settings.storage_base_url,
        )
    raise ValueError(f"Unknown storage backend: {settings.storage_backend!r}")
