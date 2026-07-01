from __future__ import annotations

from typing import Any, BinaryIO

import structlog

logger = structlog.get_logger(__name__)


class MinioClient:
    """minio-py SDK 包装. 延迟 import, 缺则提示安装."""

    def __init__(self, settings: Any) -> None:
        self._endpoint = settings.minio_endpoint
        self._access_key = settings.minio_access_key
        self._secret_key = settings.minio_secret_key
        self._secure = bool(settings.minio_secure)
        self._timeout = float(settings.minio_request_timeout)
        self._client = None

    def _ensure(self):
        if self._client is not None:
            return self._client
        try:
            from minio import Minio
        except ImportError as e:
            raise RuntimeError(
                "minio SDK not installed. pip install minio>=7.2.0"
            ) from e
        self._client = Minio(
            self._endpoint,
            access_key=self._access_key,
            secret_key=self._secret_key,
            secure=self._secure,
            timeout=self._timeout,
        )
        return self._client

    def bucket_exists(self, bucket: str) -> bool:
        return self._ensure().bucket_exists(bucket)

    def ensure_bucket(self, bucket: str, *, location: str = "us-east-1") -> bool:
        cli = self._ensure()
        if cli.bucket_exists(bucket):
            return False
        cli.make_bucket(bucket, location=location)
        return True

    def put_object(self, bucket: str, key: str,
                   stream: BinaryIO, length: int,
                   *, content_type: str = "application/octet-stream") -> None:
        self._ensure().put_object(
            bucket, key, stream, length=length, content_type=content_type,
        )

    def get_object(self, bucket: str, key: str) -> bytes:
        resp = self._ensure().get_object(bucket, key)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()

    def delete_object(self, bucket: str, key: str) -> None:
        self._ensure().remove_object(bucket, key)

    def list_objects(self, bucket: str, *, prefix: str = "",
                     recursive: bool = True) -> list[dict]:
        return [
            {"key": obj.object_name, "size": obj.size,
             "etag": obj.etag, "modified_at": obj.last_modified}
            for obj in self._ensure().list_objects(
                bucket, prefix=prefix, recursive=recursive,
            )
        ]


__all__ = ["MinioClient"]
