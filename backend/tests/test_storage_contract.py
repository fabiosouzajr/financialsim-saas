"""Storage backend contract test — same assertions pass both Local and S3 (MinIO)."""
from __future__ import annotations

from pathlib import Path

import pytest

from finacialsim_saas.storage.local import LocalVolumeBackend

KEY = "tenant-abc/proposals/123/proposta.pdf"
DATA = b"%PDF-1.4 contract test content"
CONTENT_TYPE = "application/pdf"


@pytest.fixture
def local_backend(tmp_path: Path) -> LocalVolumeBackend:
    return LocalVolumeBackend(
        root=tmp_path, secret="contract-secret", base_url="http://localhost:8000"
    )


@pytest.fixture
def s3_backend():
    try:
        from testcontainers.minio import MinioContainer
    except ImportError:
        pytest.skip("testcontainers[minio] not installed")

    try:
        minio = MinioContainer()
        minio.start()
    except Exception:
        pytest.skip("Docker unavailable — skipping MinIO contract test")

    import boto3
    client = boto3.client(
        "s3",
        endpoint_url=minio.get_url(),
        aws_access_key_id=minio.access_key,
        aws_secret_access_key=minio.secret_key,
        region_name="us-east-1",
    )
    client.create_bucket(Bucket="test-bucket")

    from finacialsim_saas.storage.s3 import S3Backend
    backend = S3Backend(
        bucket="test-bucket",
        endpoint_url=minio.get_url(),
        aws_access_key_id=minio.access_key,
        aws_secret_access_key=minio.secret_key,
    )
    yield backend
    minio.stop()


async def _run_contract(backend) -> None:
    returned_key = await backend.put(KEY, DATA, CONTENT_TYPE)
    assert returned_key == KEY

    retrieved = await backend.get(KEY)
    assert retrieved == DATA

    url = await backend.signed_url(KEY, expires_in=300)
    assert isinstance(url, str)
    assert len(url) > 0

    await backend.delete(KEY)
    await backend.delete("does/not/exist.pdf")  # must be silent


@pytest.mark.asyncio
async def test_contract_local(local_backend):
    await _run_contract(local_backend)


@pytest.mark.asyncio
async def test_contract_s3(s3_backend):
    await _run_contract(s3_backend)
