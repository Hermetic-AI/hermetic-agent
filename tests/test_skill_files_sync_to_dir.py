import tempfile
from pathlib import Path

import pytest

from hermetic_agent.store.object.memory_skill_files import MemorySkillFiles


@pytest.mark.asyncio
async def test_sync_to_dir_copies_all_files():
    with tempfile.TemporaryDirectory() as tmp_root:
        root = Path(tmp_root)
        sf = MemorySkillFiles(root)
        await sf.upload_file("flight", "SKILL.md", open(__file__, "rb"), size=10)  # noqa: SIM115
        await sf.upload_file("flight", "scripts/x.py", open(__file__, "rb"), size=10)  # noqa: SIM115
        with tempfile.TemporaryDirectory() as target_root:
            copied = await sf.sync_to_dir("flight", Path(target_root))
            assert sorted(copied) == ["SKILL.md", "scripts/x.py"]
            assert (Path(target_root) / "flight" / "SKILL.md").exists()
            assert (Path(target_root) / "flight" / "scripts" / "x.py").exists()
