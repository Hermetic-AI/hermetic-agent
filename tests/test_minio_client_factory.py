"""Tests for build_asset_clients factory and MinioClient wrapper.

Per task-10 brief: factory dispatches based on ``asset_backend`` setting.
- "memory" -> ``MemorySkillFiles`` + ``minio=None``
- "minio"  -> ``MinioSkillFiles`` + ``MinioClient`` instance
"""
from types import SimpleNamespace

import pytest

from hermetic_agent.store.object.factory import build_asset_clients


def test_memory_backend_returns_memory_skill_files():
    s = SimpleNamespace(
        asset_backend="memory",
        minio_bucket_skills="x",
        skills_default_dir="/tmp/skill_files_test",
    )
    clients = build_asset_clients(s)
    sf = clients["skill_files"]
    assert sf.__class__.__name__ == "MemorySkillFiles"
    assert clients["minio"] is None


def test_minio_backend_returns_minio_clients():
    pytest.importorskip("minio")
    s = SimpleNamespace(
        asset_backend="minio",
        minio_bucket_skills="hermetic-agent-skills",
        minio_endpoint="127.0.0.1:9000",
        minio_secure=False,
        minio_access_key="k",
        minio_secret_key="s",
        minio_connect_timeout=5.0,
        minio_request_timeout=30.0,
        skills_default_dir="/tmp/skill_files_test",
    )
    clients = build_asset_clients(s)
    sf = clients["skill_files"]
    assert sf.__class__.__name__ == "MinioSkillFiles"
    assert clients["minio"] is not None
