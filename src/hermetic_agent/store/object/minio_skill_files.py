"""MinioSkillFiles — Task 10 stub. Task 11 fills in real I/O impl."""
from __future__ import annotations

from typing import Any


class MinioSkillFiles:
    """基于 MinIO 的 skill 文件存储 (Task 11 实现 I/O, 当前仅存 deps)."""

    def __init__(self, minio: Any, settings: Any) -> None:
        self.minio = minio
        self.settings = settings
        self.bucket = getattr(settings, "minio_bucket_skills", "hermetic-agent-skills")

    def __repr__(self) -> str:
        return f"MinioSkillFiles(bucket={self.bucket})"


__all__ = ["MinioSkillFiles"]
