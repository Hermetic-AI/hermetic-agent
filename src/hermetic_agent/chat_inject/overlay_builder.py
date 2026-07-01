from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path

import structlog

from hermetic_agent.store.object.skill_files import SkillFilesClient

logger = structlog.get_logger(__name__)


class OverlayBuilder:
    """从 SkillFilesClient 拉 skill 文件到 host staging 目录.

    指纹 = sha1(sorted([file.etag for file in client.list_files(code)])).
    指纹不变 → 不重建; 变更 → 全量同步 + 写 _fingerprint.json.
    """

    def __init__(self, skill_files_client: SkillFilesClient,
                 host_base_dir: Path) -> None:
        self._client = skill_files_client
        self._base = Path(host_base_dir)
        self._base.mkdir(parents=True, exist_ok=True)

    async def build_for_session(self, skill_codes: Iterable[str],
                                 base_dir: Path | None = None) -> Path:
        base = Path(base_dir) if base_dir else self._base
        base.mkdir(parents=True, exist_ok=True)
        fingerprint: dict[str, list[str]] = {}
        for code in skill_codes:
            entries = await self._client.list_files(code)
            fingerprint[code] = sorted([e.etag for e in entries])
            target = base / code
            target.mkdir(parents=True, exist_ok=True)
            for entry in entries:
                blob = await self._client.download_file(code, entry.path)
                dst = target / entry.path
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(blob)
        meta = {"fingerprint": fingerprint,
                "skill_codes": list(skill_codes)}
        (base / "_fingerprint.json").write_text(
            json.dumps(meta, sort_keys=True), encoding="utf-8")
        logger.info("overlay_built", base=str(base),
                    skills=list(skill_codes))
        return base

    def compute_fingerprint(self, code_etags: dict[str, list[str]]) -> str:
        canonical = json.dumps(code_etags, sort_keys=True).encode()
        return hashlib.sha1(canonical).hexdigest()


__all__ = ["OverlayBuilder"]
