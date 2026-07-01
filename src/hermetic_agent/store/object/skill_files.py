from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

PATH_RE = re.compile(r"^[\w\-./]+$")


def validate_skill_path(path: str) -> str:
    """返回规范化 path; 不合法抛 ValueError.

    拒绝：空字符串、仅空白、含 `..` / `\\` / 前导 `/` / `\\x00` / `;` / `$` 等.
    """
    if path is None:
        raise ValueError("path is None")
    s = path.strip()
    if not s or not PATH_RE.match(s):
        raise ValueError(
            f"invalid skill file path: {path!r}. "
            "Allowed: letters, digits, _, -, ., /. No leading '/', no '..'."
        )
    if s.startswith("/"):
        raise ValueError("path may not start with /")
    parts = s.split("/")
    if any(p in ("", "..", ".") for p in parts):
        raise ValueError(f"path contains traversal segment: {path!r}")
    return s


@dataclass
class FileEntry:
    path: str
    size: int
    etag: str
    modified_at: object  # datetime


class SkillFilesClient(ABC):
    @abstractmethod
    async def upload_file(self, code, path, stream, size) -> FileEntry: ...
    @abstractmethod
    async def download_file(self, code, path) -> bytes: ...
    @abstractmethod
    async def delete_file(self, code, path) -> None: ...
    @abstractmethod
    async def list_files(self, code) -> list[FileEntry]: ...
    @abstractmethod
    async def sync_to_dir(self, code, target_dir) -> list[str]: ...


def key_for(code: str, path: str) -> str:
    return f"skills/{code}/{validate_skill_path(path)}"


__all__ = ["validate_skill_path", "FileEntry", "SkillFilesClient", "key_for"]
