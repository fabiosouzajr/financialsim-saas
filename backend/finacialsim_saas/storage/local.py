"""LocalVolumeBackend — stores files on disk; signs URLs with HMAC-SHA256."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
import urllib.parse
from pathlib import Path


class LocalVolumeBackend:
    def __init__(self, root: Path, secret: str, base_url: str) -> None:
        self._root = root
        self._secret = secret.encode()
        self._base_url = base_url.rstrip("/")

    async def put(self, key: str, data: bytes, content_type: str) -> str:
        dest = self._root / key
        await asyncio.to_thread(dest.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(dest.write_bytes, data)
        return key

    async def get(self, key: str) -> bytes:
        path = self._root / key
        return await asyncio.to_thread(path.read_bytes)

    async def signed_url(self, key: str, expires_in: int = 300) -> str:
        expires_at = int(time.time()) + expires_in
        msg = f"{key}:{expires_at}".encode()
        sig = hmac.new(self._secret, msg, hashlib.sha256).hexdigest()
        params = urllib.parse.urlencode({"key": key, "expires": expires_at, "sig": sig})
        return f"{self._base_url}/api/v1/storage/serve?{params}"

    async def delete(self, key: str) -> None:
        path = self._root / key
        try:
            await asyncio.to_thread(path.unlink)
        except FileNotFoundError:
            pass
