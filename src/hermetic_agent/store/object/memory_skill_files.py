from __future__ import annotations

import contextlib
import hashlib
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from hermetic_agent.store.object.skill_files import (
    FileEntry,
    SkillFilesClient,
    validate_skill_path,
)


class MemorySkillFiles(SkillFilesClient):
    """本地文件系统实现，用于 dev / 测试。"""

    def __init__(self, root_dir: Path) -> None:
        self._root = Path(root_dir)

    def _abs_path(self, code, path):
        return self._root / code / validate_skill_path(path)

    async def upload_file(self, code, path, stream, size):
        target = self._abs_path(code, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "wb") as f:
            shutil.copyfileobj(stream, f)
        return self._entry(code, path, target)

    async def download_file(self, code, path):
        return self._abs_path(code, path).read_bytes()

    async def delete_file(self, code, path):
        with contextlib.suppress(FileNotFoundError):
            os.remove(self._abs_path(code, path))

    async def list_files(self, code):
        root = self._root / code
        if not root.exists():
            return []
        out = []
        for p in root.rglob("*"):
            if p.is_file():
                rel = str(p.relative_to(root)).replace(os.sep, "/")
                out.append(self._entry(code, rel, p))
        return out

    async def sync_to_dir(self, code, target_dir):
        target = Path(target_dir) / code
        target.mkdir(parents=True, exist_ok=True)
        copied = []
        for entry in await self.list_files(code):
            src = self._abs_path(code, entry.path)
            dst = target / entry.path
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied.append(entry.path)
        return copied

    def _entry(self, code, path, abs_path):
        st = abs_path.stat()
        return FileEntry(
            path=path,
            size=st.st_size,
            etag=hashlib.sha1(abs_path.read_bytes()).hexdigest(),
            modified_at=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc),
        )


__all__ = ["MemorySkillFiles"]
