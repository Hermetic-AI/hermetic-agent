import asyncio
import io
import tempfile
from pathlib import Path

import pytest

from hermetic_agent.chat_inject.overlay_builder import OverlayBuilder
from hermetic_agent.chat_inject.reload_queue import ReloadQueue, ReloadTask
from hermetic_agent.chat_inject.skill_overlay_manager import SkillOverlayManager
from hermetic_agent.store.object.memory_skill_files import MemorySkillFiles


@pytest.mark.asyncio
async def test_ensure_active_no_change_returns_cached_paths_no_reload():
    with tempfile.TemporaryDirectory() as tmp:
        sf = MemorySkillFiles(Path(tmp))
        await sf.upload_file("flight", "SKILL.md", open(__file__, "rb"), size=10)  # noqa: SIM115
        base = Path(tmp) / "stage"
        ob = OverlayBuilder(sf, base)

        reloads: list[str] = []

        async def apply(t: ReloadTask) -> bool:
            reloads.append(t.node_id)
            return True

        q = ReloadQueue(apply=apply)
        await q.start()
        try:
            mgr = SkillOverlayManager(ob, q, node_id="opencode-1")
            await mgr.ensure_active(["flight"])
            await mgr.ensure_active(["flight"])
        finally:
            await q.stop()
        assert len(reloads) == 1


@pytest.mark.asyncio
async def test_ensure_active_detects_change_and_reenqueues():
    with tempfile.TemporaryDirectory() as tmp:
        sf = MemorySkillFiles(Path(tmp))
        await sf.upload_file("flight", "SKILL.md", open(__file__, "rb"), size=10)  # noqa: SIM115
        base = Path(tmp) / "stage"
        ob = OverlayBuilder(sf, base)

        reloads: list[str] = []

        async def apply(t: ReloadTask) -> bool:
            reloads.append(t.node_id)
            return True

        q = ReloadQueue(apply=apply, debounce_seconds=0.05)
        await q.start()
        try:
            mgr = SkillOverlayManager(ob, q, node_id="opencode-1")
            await mgr.ensure_active(["flight"])
            await sf.upload_file("flight", "SKILL.md",
                                 io.BytesIO(b"v2"), size=20)
            await asyncio.sleep(0.1)
            await mgr.ensure_active(["flight"])
        finally:
            await q.stop()
        assert len(reloads) == 2
