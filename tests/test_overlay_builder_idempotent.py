import tempfile
from pathlib import Path

import pytest

from hermetic_agent.store.object.memory_skill_files import MemorySkillFiles


@pytest.mark.asyncio
async def test_overlay_builder_is_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        sf = MemorySkillFiles(Path(tmp))
        await sf.upload_file("flight", "SKILL.md", open(__file__, "rb"), size=10)  # noqa: SIM115
        await sf.upload_file("flight", "scripts/x.py", open(__file__, "rb"), size=10)  # noqa: SIM115
        base = Path(tmp) / "stage"
        from hermetic_agent.chat_inject.overlay_builder import OverlayBuilder
        ob = OverlayBuilder(sf, base)
        p1 = await ob.build_for_session(["flight"], base)
        assert (base / "flight" / "SKILL.md").exists()
        p2 = await ob.build_for_session(["flight"], base)
        assert p1 == p2


@pytest.mark.asyncio
async def test_overlay_builder_respects_fingerprint_change():
    with tempfile.TemporaryDirectory() as tmp:
        sf = MemorySkillFiles(Path(tmp))
        await sf.upload_file("flight", "SKILL.md", open(__file__, "rb"), size=10)  # noqa: SIM115
        base = Path(tmp) / "stage"
        from hermetic_agent.chat_inject.overlay_builder import OverlayBuilder
        ob = OverlayBuilder(sf, base)
        await ob.build_for_session(["flight"], base)
        await sf.upload_file("flight", "SKILL.md", open(__file__, "rb"), size=20)  # noqa: SIM115
        await ob.build_for_session(["flight"], base)
        assert (base / "flight" / "SKILL.md").exists()
