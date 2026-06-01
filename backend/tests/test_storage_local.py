import hashlib
import hmac
import time
import urllib.parse
from pathlib import Path

import pytest

from finacialsim_saas.storage.local import LocalVolumeBackend


@pytest.fixture
def storage(tmp_path: Path) -> LocalVolumeBackend:
    return LocalVolumeBackend(
        root=tmp_path,
        secret="test-secret",
        base_url="http://localhost:8000",
    )


@pytest.mark.asyncio
async def test_put_and_get(storage: LocalVolumeBackend):
    key = "tenant-1/proposals/abc/proposta.pdf"
    data = b"%PDF-1.4 test content"
    await storage.put(key, data, "application/pdf")
    result = await storage.get(key)
    assert result == data


@pytest.mark.asyncio
async def test_signed_url_structure(storage: LocalVolumeBackend):
    key = "tenant-1/proposals/abc/proposta.pdf"
    url = await storage.signed_url(key, expires_in=300)
    assert url.startswith("http://localhost:8000/api/v1/storage/serve?")
    parsed = urllib.parse.urlparse(url)
    params = urllib.parse.parse_qs(parsed.query)
    assert "key" in params
    assert "expires" in params
    assert "sig" in params
    assert params["key"][0] == key


@pytest.mark.asyncio
async def test_signed_url_valid_hmac(storage: LocalVolumeBackend):
    key = "tenant-1/proposals/abc/proposta.pdf"
    url = await storage.signed_url(key, expires_in=300)
    params = dict(urllib.parse.parse_qs(urllib.parse.urlparse(url).query))
    expires = int(params["expires"][0])
    sig = params["sig"][0]
    msg = f"{key}:{expires}".encode()
    expected = hmac.new(b"test-secret", msg, hashlib.sha256).hexdigest()
    assert hmac.compare_digest(expected, sig)


@pytest.mark.asyncio
async def test_delete(storage: LocalVolumeBackend, tmp_path: Path):
    key = "tenant-1/proposals/abc/proposta.pdf"
    await storage.put(key, b"data", "application/pdf")
    assert (tmp_path / key).exists()
    await storage.delete(key)
    assert not (tmp_path / key).exists()


@pytest.mark.asyncio
async def test_delete_nonexistent_is_silent(storage: LocalVolumeBackend):
    await storage.delete("does/not/exist.pdf")
