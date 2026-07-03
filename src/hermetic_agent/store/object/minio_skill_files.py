from __future__ import annotations

import hashlib
import io
from datetime import datetime, timezone
from pathlib import Path

from hermetic_agent.store.object.minio_client import MinioClient
from hermetic_agent.store.object.skill_files import (
    FileEntry,
    SkillFilesClient,
    key_for,
    validate_skill_path,
)


class MinioSkillFiles(SkillFilesClient):
    """MinIO 后端实现。bucket 单，key = skills/{code}/{path}."""

    def __init__(self, minio: MinioClient, settings) -> None:
        self._cli = minio
        self._bucket = settings.minio_bucket_skills

    async def upload_file(self, code, path, stream, size):
        path = validate_skill_path(path)
        key = key_for(code, path)
        buf = stream.read()
        size = len(buf)
        self._cli.put_object(
            self._bucket, key, io.BytesIO(buf), length=size,
            content_type="application/octet-stream",
        )
        return FileEntry(
            path=path, size=size,
            etag=hashlib.sha1(buf).hexdigest(),
            modified_at=datetime.now(timezone.utc),
        )

    async def download_file(self, code, path):
        path = validate_skill_path(path)
        return self._cli.get_object(self._bucket, key_for(code, path))

    async def delete_file(self, code, path):
        path = validate_skill_path(path)
        self._cli.delete_object(self._bucket, key_for(code, path))

    async def list_files(self, code):
        prefix = f"skills/{code}/"
        items = self._cli.list_objects(self._bucket, prefix=prefix)
        return [
            FileEntry(
                path=item["key"][len(prefix):],
                size=item["size"], etag=item["etag"],
                modified_at=item["modified_at"],
            )
            for item in items
        ]

    async def sync_to_dir(self, code, target_dir):
        target = Path(target_dir) / code
        target.mkdir(parents=True, exist_ok=True)
        copied = []
        for entry in await self.list_files(code):
            blob = await self.download_file(code, entry.path)
            dst = target / entry.path
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(blob)
            copied.append(entry.path)
        return copied


__all__ = ["MinioSkillFiles"]
