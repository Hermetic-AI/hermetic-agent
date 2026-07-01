from __future__ import annotations

from pathlib import Path
from typing import Any


def build_asset_clients(settings: Any) -> dict[str, Any]:
    """根据 settings.asset_backend 返回 asset 客户端集合.

    Returns:
        {"minio": MinioClient | None, "skill_files": SkillFilesClient}
    """
    backend = (getattr(settings, "asset_backend", "memory") or "memory").lower()
    minio = None
    if backend == "minio":
        from hermetic_agent.store.object.minio_client import MinioClient
        minio = MinioClient(settings)

    skills_dir = Path(
        getattr(settings, "skills_default_dir", "work/cache/_memory-skill-files"),
    )
    if backend == "minio" and minio is not None:
        from hermetic_agent.store.object.minio_skill_files import MinioSkillFiles
        skill_files = MinioSkillFiles(minio, settings)
    else:
        from hermetic_agent.store.object.memory_skill_files import MemorySkillFiles
        skills_dir.mkdir(parents=True, exist_ok=True)
        skill_files = MemorySkillFiles(skills_dir, settings=settings)

    return {"minio": minio, "skill_files": skill_files}


__all__ = ["build_asset_clients"]
