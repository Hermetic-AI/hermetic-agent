"""MemorySkillFiles — Task 10 stub. Task 11 fills in real I/O impl."""
from __future__ import annotations

from pathlib import Path
from typing import Any


class MemorySkillFiles:
    """本地磁盘 skill 文件存储 (Task 11 实现 I/O, 当前仅存 root)."""

    def __init__(self, root: Path, *, settings: Any | None = None) -> None:
        self.root = Path(root)

    def __repr__(self) -> str:
        return f"MemorySkillFiles(root={self.root})"


__all__ = ["MemorySkillFiles"]
