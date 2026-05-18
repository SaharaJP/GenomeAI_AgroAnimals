"""S3-compatible blob storage adapter (MinIO in dev, S3 in prod).

Reads config from env:
  - GENOMEAI_BLOB_ENDPOINT       (e.g. http://localhost:9100 for dev)
  - GENOMEAI_BLOB_ACCESS_KEY     (or _FILE)
  - GENOMEAI_BLOB_SECRET_KEY     (or _FILE)
  - GENOMEAI_BLOB_REGION         (default us-east-1; MinIO ignores it)
  - GENOMEAI_BLOB_BUCKET_DEFAULT (per-feature buckets can override)

Used for personnel photos (P1-4 R6) and future binary attachments.
"""
from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from typing import Any, BinaryIO, Optional

logger = logging.getLogger(__name__)


class BlobStorageError(RuntimeError):
    pass


def _read_secret(env_name: str, *, fallback: Optional[str] = None) -> Optional[str]:
    direct = (os.environ.get(env_name) or '').strip()
    if direct:
        return direct
    file_path = (os.environ.get(f'{env_name}_FILE') or '').strip()
    if file_path and os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except OSError:
            pass
    return fallback


@dataclass(frozen=True)
class BlobStorageSettings:
    endpoint: str
    access_key: str
    secret_key: str
    region: str
    default_bucket: str

    @property
    def configured(self) -> bool:
        return bool(self.endpoint and self.access_key and self.secret_key)


def load_blob_storage_settings() -> BlobStorageSettings:
    endpoint = (os.environ.get('GENOMEAI_BLOB_ENDPOINT') or '').strip()
    access_key = _read_secret('GENOMEAI_BLOB_ACCESS_KEY') or ''
    secret_key = _read_secret('GENOMEAI_BLOB_SECRET_KEY') or ''
    region = (os.environ.get('GENOMEAI_BLOB_REGION') or 'us-east-1').strip()
    default_bucket = (os.environ.get('GENOMEAI_BLOB_BUCKET_DEFAULT') or 'genomeai-personnel-photos').strip()
    return BlobStorageSettings(
        endpoint=endpoint,
        access_key=access_key,
        secret_key=secret_key,
        region=region,
        default_bucket=default_bucket,
    )


def _make_client(settings: BlobStorageSettings) -> Any:
    if not settings.configured:
        raise BlobStorageError(
            'GENOMEAI_BLOB_ENDPOINT/ACCESS_KEY/SECRET_KEY не настроены — blob storage недоступен.'
        )
    try:
        import boto3  # type: ignore
        from botocore.client import Config  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise BlobStorageError(f'boto3 SDK недоступен: {exc}') from exc
    return boto3.client(
        's3',
        endpoint_url=settings.endpoint,
        aws_access_key_id=settings.access_key,
        aws_secret_access_key=settings.secret_key,
        region_name=settings.region,
        config=Config(signature_version='s3v4', retries={'max_attempts': 2}),
    )


def ensure_bucket(*, bucket: Optional[str] = None) -> str:
    """Create the bucket if it doesn't exist (idempotent). Returns bucket name."""
    settings = load_blob_storage_settings()
    target_bucket = bucket or settings.default_bucket
    client = _make_client(settings)
    try:
        client.head_bucket(Bucket=target_bucket)
        return target_bucket
    except Exception:
        # head_bucket raises 404 / NoSuchBucket; fall through to create
        pass
    try:
        client.create_bucket(Bucket=target_bucket)
    except Exception as exc:
        # Tolerate race "BucketAlreadyOwnedByYou"
        msg = str(exc)
        if 'BucketAlreadyOwnedByYou' in msg or 'BucketAlreadyExists' in msg:
            return target_bucket
        raise BlobStorageError(f'create_bucket failed for {target_bucket}: {exc}') from exc
    return target_bucket


def put_object(
    *,
    key: str,
    body: bytes | BinaryIO,
    content_type: str = 'application/octet-stream',
    bucket: Optional[str] = None,
) -> str:
    """Upload an object; returns the bucket/key path (not a URL)."""
    settings = load_blob_storage_settings()
    target_bucket = bucket or settings.default_bucket
    ensure_bucket(bucket=target_bucket)
    client = _make_client(settings)
    try:
        client.put_object(Bucket=target_bucket, Key=key, Body=body, ContentType=content_type)
    except Exception as exc:
        raise BlobStorageError(f'put_object failed for {target_bucket}/{key}: {exc}') from exc
    return f'{target_bucket}/{key}'


def get_presigned_url(
    *,
    key: str,
    bucket: Optional[str] = None,
    expires_in: int = 3600,
) -> str:
    """Generate a time-limited URL for client download."""
    settings = load_blob_storage_settings()
    target_bucket = bucket or settings.default_bucket
    client = _make_client(settings)
    try:
        return client.generate_presigned_url(
            'get_object',
            Params={'Bucket': target_bucket, 'Key': key},
            ExpiresIn=int(expires_in),
        )
    except Exception as exc:
        raise BlobStorageError(f'presign failed for {target_bucket}/{key}: {exc}') from exc


def delete_object(*, key: str, bucket: Optional[str] = None) -> None:
    settings = load_blob_storage_settings()
    target_bucket = bucket or settings.default_bucket
    client = _make_client(settings)
    try:
        client.delete_object(Bucket=target_bucket, Key=key)
    except Exception as exc:
        raise BlobStorageError(f'delete failed for {target_bucket}/{key}: {exc}') from exc


__all__ = [
    'BlobStorageError',
    'BlobStorageSettings',
    'delete_object',
    'ensure_bucket',
    'get_presigned_url',
    'load_blob_storage_settings',
    'put_object',
]
