from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import structlog

logger = structlog.get_logger(__name__)

if TYPE_CHECKING:
    from hermetic_agent.chat_inject.overlay_builder import OverlayBuilder
    from hermetic_agent.chat_inject.reload_queue import ReloadQueue


@dataclass
class SkillFingerprint:
    """每 node 维护一份 (paths, fingerprint_str) 缓存."""
    paths: list[str] = field(default_factory=list)
    fingerprint: str = ""


class SkillOverlayManager:
    """每 (node_id) 计算激活的 skill paths + 指纹, 与上次不同时排队 reload."""

    def __init__(self, overlay_builder: OverlayBuilder,
                 reload_queue: ReloadQueue, *,
                 node_id: str) -> None:
        self._builder = overlay_builder
        self._queue = reload_queue
        self._node_id = node_id
        self._last = SkillFingerprint()

    async def ensure_active(self, skill_codes: list[str]) -> list[str]:
        entries_by_code: dict[str, list[str]] = {}
        for code in skill_codes:
            es = await self._builder._client.list_files(code)
            entries_by_code[code] = sorted([e.etag for e in es])
        fp = self._builder.compute_fingerprint(entries_by_code)
        paths = [f"{code}/" for code in skill_codes]
        if fp == self._last.fingerprint and paths == self._last.paths:
            return list(self._last.paths)
        await self._builder.build_for_session(skill_codes)
        from hermetic_agent.chat_inject.reload_queue import ReloadTask
        await self._queue.enqueue(
            ReloadTask(node_id=self._node_id, paths=paths))
        self._last = SkillFingerprint(paths=list(paths), fingerprint=fp)
        logger.info("skill_overlay_reload_enqueued",
                    node_id=self._node_id, paths=paths)
        return paths


__all__ = ["SkillOverlayManager", "SkillFingerprint"]
