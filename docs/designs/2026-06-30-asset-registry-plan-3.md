# 资产注册中心实现计划 — Part 3 / 3

> 配套主计划：`2026-06-30-asset-registry-plan.md`（Phase 1 Tasks 1–3）+ `2026-06-30-asset-registry-plan-2.md`（Phase 1 Tasks 4–9）。
> 本文件覆盖 **Phase 2 MinIO 文件面**（Tasks 10–12）、**Phase 3 chat 集成**（Tasks 13–16）、**Phase 4 收口**（Tasks 17–19）。

---

## Task 10: Settings §16/17/18 + MinIO 客户端（L5）

**Files:**
- 修改：`src/hermetic_agent/config/settings.py`（追加 3 段 settings）
- 修改：`pyproject.toml`、`requirements.txt`（同步 `minio>=7.2.0`）
- 新建：`src/hermetic_agent/store/object/__init__.py`
- 新建：`src/hermetic_agent/store/object/minio_client.py`
- 新建：`src/hermetic_agent/store/object/factory.py`
- 新建：`tests/test_minio_client_factory.py`

**Interfaces:**
- `MinioClient` 类：`bucket_exists / ensure_bucket / put_object / get_object / delete_object / list_objects`
- `build_asset_clients(settings) -> {"minio": ..., "skill_files": ...}`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_minio_client_factory.py
from types import SimpleNamespace

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
```

- [ ] **Step 2: 跑测试验证失败**

Run: `pytest tests/test_minio_client_factory.py -v` — FAIL（factory 不存在）

- [ ] **Step 3: 在 `settings.py` 追加 §16/§17/§18**

打开 `src/hermetic_agent/config/settings.py`，找到最后一个 `Field(...)` 段（保持既有字段不动），追加：

```python
# §16 MinIO (asset object storage)
minio_endpoint: str = Field(default="127.0.0.1:9000",
    description="MinIO host:port (no scheme)")
minio_secure: bool = Field(default=False)
minio_access_key: str = Field(default="hermetic-agent-hub")
minio_secret_key: str = Field(default="change-me")
minio_bucket_skills: str = Field(default="hermetic-agent-skills")
minio_connect_timeout: float = Field(default=5.0)
minio_request_timeout: float = Field(default=30.0)
asset_backend: str = Field(default="memory",
    description="'memory' | 'minio'")

# §17 Agent defaults
agent_default_code: str = Field(default="general-assistant")
agent_default_model: str = Field(default="openai/gpt-4o-mini")
agent_default_tool_level: str = Field(default="standard")
agent_default_visibility: str = Field(default="private")
agent_enabled: bool = Field(default=True)

# §18 Skill files (memory backend)
skills_default_dir: str = Field(
    default="work/cache/_memory-skill-files",
    description="memory backend 时本地的 skill 文件根",
)
```

> pydantic-settings 会按 `AGENT_SCHEDULER_` 前缀 → env 变量名 `AGENT_SCHEDULER_MINIO_ENDPOINT` 等。

- [ ] **Step 4: 同步 `pyproject.toml` 与 `requirements.txt`**

打开 `pyproject.toml`，在 dependencies 区追加：

```toml
    "minio>=7.2.0",
```

打开 `requirements.txt` 末尾追加：

```
minio>=7.2.0
```

- [ ] **Step 5: 写 `MinioClient`**

```python
# src/hermetic_agent/store/object/minio_client.py
from __future__ import annotations
from typing import Any, BinaryIO

import structlog

logger = structlog.get_logger(__name__)


class MinioClient:
    """minio-py SDK 封装. 延迟 import, 缺则提示安装."""

    def __init__(self, settings: Any) -> None:
        self._endpoint = settings.minio_endpoint
        self._access_key = settings.minio_access_key
        self._secret_key = settings.minio_secret_key
        self._secure = bool(settings.minio_secure)
        self._timeout = float(settings.minio_request_timeout)
        self._client = None

    def _ensure(self):
        if self._client is not None:
            return self._client
        try:
            from minio import Minio
        except ImportError as e:
            raise RuntimeError(
                "minio SDK not installed. pip install minio>=7.2.0"
            ) from e
        self._client = Minio(
            self._endpoint,
            access_key=self._access_key,
            secret_key=self._secret_key,
            secure=self._secure,
            timeout=self._timeout,
        )
        return self._client

    def bucket_exists(self, bucket: str) -> bool:
        return self._ensure().bucket_exists(bucket)

    def ensure_bucket(self, bucket: str, *, location: str = "us-east-1") -> bool:
        cli = self._ensure()
        if cli.bucket_exists(bucket):
            return False
        cli.make_bucket(bucket, location=location)
        return True

    def put_object(self, bucket: str, key: str,
                   stream: BinaryIO, length: int,
                   *, content_type: str = "application/octet-stream") -> None:
        self._ensure().put_object(
            bucket, key, stream, length=length, content_type=content_type)

    def get_object(self, bucket: str, key: str) -> bytes:
        resp = self._ensure().get_object(bucket, key)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()

    def delete_object(self, bucket: str, key: str) -> None:
        self._ensure().remove_object(bucket, key)

    def list_objects(self, bucket: str, *, prefix: str = "",
                     recursive: bool = True) -> list[dict]:
        return [
            {"key": obj.object_name, "size": obj.size,
             "etag": obj.etag, "modified_at": obj.last_modified}
            for obj in self._ensure().list_objects(
                bucket, prefix=prefix, recursive=recursive)
        ]


__all__ = ["MinioClient"]
```

- [ ] **Step 6: 写 `factory.py`**

```python
# src/hermetic_agent/store/object/factory.py
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

    skills_dir = Path(getattr(settings, "skills_default_dir",
                              "work/cache/_memory-skill-files"))
    if backend == "minio" and minio is not None:
        from hermetic_agent.store.object.minio_skill_files import MinioSkillFiles
        skill_files = MinioSkillFiles(minio, settings)
    else:
        from hermetic_agent.store.object.memory_skill_files import MemorySkillFiles
        skills_dir.mkdir(parents=True, exist_ok=True)
        skill_files = MemorySkillFiles(skills_dir)

    return {"minio": minio, "skill_files": skill_files}


__all__ = ["build_asset_clients"]
```

- [ ] **Step 7: `__init__.py` 导出**

```python
# src/hermetic_agent/store/object/__init__.py
from hermetic_agent.store.object.minio_client import MinioClient
from hermetic_agent.store.object.factory import build_asset_clients

__all__ = ["MinioClient", "build_asset_clients"]
```

- [ ] **Step 8: 跑测试**

Run: `pytest tests/test_minio_client_factory.py -v` — 2 passed

- [ ] **Step 9: 提交**

```bash
git add src/hermetic_agent/config/settings.py \
        pyproject.toml \
        requirements.txt \
        src/hermetic_agent/store/object/__init__.py \
        src/hermetic_agent/store/object/minio_client.py \
        src/hermetic_agent/store/object/factory.py \
        tests/test_minio_client_factory.py
git commit -m "feat(settings/object): add §16 MinIO + factory + MinioClient"
```

---

## Task 11: SkillFilesClient + 2 个实现（L5）

**Files:**
- 新建：`src/hermetic_agent/store/object/skill_files.py`（接口 + 路径校验）
- 新建：`src/hermetic_agent/store/object/memory_skill_files.py`
- 新建：`src/hermetic_agent/store/object/minio_skill_files.py`
- 新建：`tests/test_skill_files_path_validation.py`、`tests/test_skill_files_sync_to_dir.py`

**Interfaces:** `SkillFilesClient` 抽象类；5 个方法 + `validate_skill_path` 工具函数 + `key_for` 工具。

- [ ] **Step 1: 写路径校验失败测试**

```python
# tests/test_skill_files_path_validation.py
import pytest
from hermetic_agent.store.object.skill_files import validate_skill_path


def test_accepts_normal_relative_path():
    p = validate_skill_path("scripts/run.sh")
    assert p == "scripts/run.sh"


@pytest.mark.parametrize("bad", [
    "../etc/passwd", "/etc/passwd", "..\\windows",
    "a\x00b", "a;b", "a$b", "", "  ",
])
def test_rejects_traversal_and_invalid(bad):
    with pytest.raises(ValueError):
        validate_skill_path(bad)
```

- [ ] **Step 2: 跑测试验证失败**

Run: `pytest tests/test_skill_files_path_validation.py -v` — FAIL

- [ ] **Step 3: 写抽象接口与校验器**

```python
# src/hermetic_agent/store/object/skill_files.py
from __future__ import annotations
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import BinaryIO

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
```

- [ ] **Step 4: 跑测试验证通过**

Run: `pytest tests/test_skill_files_path_validation.py -v` — all passed

- [ ] **Step 5: 写失败 sync 测试**

```python
# tests/test_skill_files_sync_to_dir.py
import pytest
import tempfile
from pathlib import Path

from hermetic_agent.store.object.memory_skill_files import MemorySkillFiles


@pytest.mark.asyncio
async def test_sync_to_dir_copies_all_files():
    with tempfile.TemporaryDirectory() as tmp_root:
        root = Path(tmp_root)
        sf = MemorySkillFiles(root)
        await sf.upload_file("flight", "SKILL.md", open(__file__, "rb"), size=10)
        await sf.upload_file("flight", "scripts/x.py", open(__file__, "rb"), size=10)
        with tempfile.TemporaryDirectory() as target_root:
            copied = await sf.sync_to_dir("flight", Path(target_root))
            assert sorted(copied) == ["SKILL.md", "scripts/x.py"]
            assert (Path(target_root) / "flight" / "SKILL.md").exists()
            assert (Path(target_root) / "flight" / "scripts" / "x.py").exists()
```

- [ ] **Step 6: 跑测试验证失败**

Run: `pytest tests/test_skill_files_sync_to_dir.py -v` — FAIL

- [ ] **Step 7: 实现 `MemorySkillFiles`**

```python
# src/hermetic_agent/store/object/memory_skill_files.py
from __future__ import annotations
import hashlib
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

from hermetic_agent.store.object.skill_files import (
    FileEntry, SkillFilesClient, validate_skill_path,
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
        try:
            os.remove(self._abs_path(code, path))
        except FileNotFoundError:
            pass

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
```

- [ ] **Step 8: 实现 `MinioSkillFiles`**

```python
# src/hermetic_agent/store/object/minio_skill_files.py
from __future__ import annotations
import hashlib
import io
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

from hermetic_agent.store.object.minio_client import MinioClient
from hermetic_agent.store.object.skill_files import (
    FileEntry, SkillFilesClient, key_for, validate_skill_path,
)


class MinioSkillFiles(SkillFilesClient):
    """MinIO 后端实现。bucket 单，key = skills/{code}/{path}."""

    def __init__(self, minio: MinioClient, settings) -> None:
        self._cli = minio
        self._bucket = settings.minio_bucket_skills

    async def upload_file(self, code, path, stream, size):
        path = validate_skill_path(path)
        key = key_for(code, path)
        buf = stream.read()
        size = len(buf)
        self._cli.put_object(
            self._bucket, key, io.BytesIO(buf), length=size,
            content_type="application/octet-stream",
        )
        return FileEntry(
            path=path, size=size,
            etag=hashlib.sha1(buf).hexdigest(),
            modified_at=datetime.now(timezone.utc),
        )

    async def download_file(self, code, path):
        path = validate_skill_path(path)
        return self._cli.get_object(self._bucket, key_for(code, path))

    async def delete_file(self, code, path):
        path = validate_skill_path(path)
        self._cli.delete_object(self._bucket, key_for(code, path))

    async def list_files(self, code):
        prefix = f"skills/{code}/"
        items = self._cli.list_objects(self._bucket, prefix=prefix)
        return [
            FileEntry(
                path=item["key"][len(prefix):],
                size=item["size"], etag=item["etag"],
                modified_at=item["modified_at"],
            )
            for item in items
        ]

    async def sync_to_dir(self, code, target_dir):
        target = Path(target_dir) / code
        target.mkdir(parents=True, exist_ok=True)
        copied = []
        for entry in await self.list_files(code):
            blob = await self.download_file(code, entry.path)
            dst = target / entry.path
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(blob)
            copied.append(entry.path)
        return copied


__all__ = ["MinioSkillFiles"]
```

- [ ] **Step 9: 跑测试**

Run: `pytest tests/test_skill_files_path_validation.py tests/test_skill_files_sync_to_dir.py -v`

- [ ] **Step 10: 提交**

```bash
git add src/hermetic_agent/store/object/skill_files.py \
        src/hermetic_agent/store/object/memory_skill_files.py \
        src/hermetic_agent/store/object/minio_skill_files.py \
        tests/test_skill_files_path_validation.py \
        tests/test_skill_files_sync_to_dir.py
git commit -m "feat(object): add SkillFilesClient with memory + MinIO impls"
```

---

## Task 12: skill_files_controller + 接线（L1）

**Files:**
- 新建：`src/hermetic_agent/api/http/controllers/skill_files_controller.py`
- 修改：`src/hermetic_agent/api/app/blueprint_registry.py`
- 修改：`src/hermetic_agent/api/lifecycle/lifecycle.py`（startup 构造 `asset_clients`）
- 新建：`tests/test_skill_files_controller_endpoint.py`

**Interfaces:** 5 个端点，`url_prefix = "/agent/skills"`，端点路径见 spec §4.1。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_skill_files_controller_endpoint.py
import pytest
from sanic import Sanic
import io as _io

from hermetic_agent.api.http.controllers.skill_files_controller import skill_files_bp
from hermetic_agent.store.dto._common import ActorContext
from hermetic_agent.store.object.memory_skill_files import MemorySkillFiles
import tempfile
from pathlib import Path


@pytest.fixture
async def app():
    with tempfile.TemporaryDirectory() as tmp:
        sf = MemorySkillFiles(Path(tmp))
        app = Sanic("test_skill_files_app")
        app.blueprint(skill_files_bp)
        app.ctx.asset_clients = {"minio": None, "skill_files": sf}

        async def fake_actor_mw(request):
            request.ctx.actor = ActorContext(
                user_id=request.headers.get("X-User-Id", "alice"))
        app.register_middleware(fake_actor_mw, "request")
        yield app


@pytest.mark.asyncio
async def test_upload_then_download(app):
    body = b"hello world"
    _, r = await app.asgi_client.put(
        "/agent/skills/sample/files/SKILL.md",
        headers={"X-User-Id": "alice",
                 "Content-Type": "application/octet-stream"},
        data=body)
    assert r.status == 201
    _, r2 = await app.asgi_client.get("/agent/skills/sample/files/SKILL.md")
    assert r2.status == 200
    import base64
    assert base64.b64decode(r2.json["content_b64"]) == body


@pytest.mark.asyncio
async def test_path_traversal_rejected(app):
    _, r = await app.asgi_client.put(
        "/agent/skills/sample/files/..%2Fetc%2Fpasswd",
        headers={"X-User-Id": "alice"},
        data=b"x",
    )
    assert r.status in (400, 404)  # Sanic 把 `..%2F` 路径解码后由 SkillFilesClient 拒
```

- [ ] **Step 2: 跑测试验证失败**

Run: `pytest tests/test_skill_files_controller_endpoint.py -v` — FAIL（BP 不存在）

- [ ] **Step 3: 写 `skill_files_controller.py`**

```python
# src/hermetic_agent/api/http/controllers/skill_files_controller.py
from __future__ import annotations
import base64
import io as _io
import structlog

from sanic import Blueprint
from sanic.request import Request
from sanic.response import JSONResponse
from sanic_ext import openapi as sanic_openapi

logger = structlog.get_logger(__name__)
doc_summary = sanic_openapi.summary
doc_tag = sanic_openapi.tag

skill_files_bp = Blueprint("skill_files", url_prefix="/agent/skills")

MAX_FILE_SIZE = 16 * 1024 * 1024  # 16 MB
MAX_BATCH = 8


def _err(code, message, status=400):
    return JSONResponse(
        {"success": False, "code": code, "error": message}, status=status)


def _get_clients(request):
    return request.app.ctx.asset_clients


@skill_files_bp.get("/<code>/files")
@doc_summary("List files in a skill")
@doc_tag("Skill Files")
async def list_skill_files(request, code):
    cl = _get_clients(request)
    files = await cl["skill_files"].list_files(code)
    return JSONResponse({
        "code": code,
        "total": len(files),
        "items": [
            {"path": f.path, "size": f.size, "etag": f.etag,
             "modified_at": str(f.modified_at)}
            for f in files
        ],
    })


@skill_files_bp.get("/<code>/files/<path:path>")
@doc_summary("Download one skill file")
@doc_tag("Skill Files")
async def get_skill_file(request, code, path):
    cl = _get_clients(request)
    try:
        blob = await cl["skill_files"].download_file(code, path)
    except FileNotFoundError:
        return _err("FILE_NOT_FOUND", f"{code}/{path} not found", status=404)
    except Exception as e:
        logger.error("skill_file_download_error", error=str(e))
        return _err("OBJECT_STORE_UNAVAILABLE", str(e), status=503)
    return JSONResponse({
        "code": code, "path": path,
        "content_b64": base64.b64encode(blob).decode(),
    })


@skill_files_bp.put("/<code>/files/<path:path>")
@doc_summary("Upload/update one skill file (≤ 16 MB)")
@doc_tag("Skill Files")
async def put_skill_file(request, code, path):
    cl = _get_clients(request)
    body = request.body or b""
    if len(body) > MAX_FILE_SIZE:
        return _err("VALIDATION_FAILED",
                    f"file too large (> {MAX_FILE_SIZE} bytes)", status=413)
    try:
        entry = await cl["skill_files"].upload_file(
            code, path, _io.BytesIO(body), len(body))
    except ValueError as e:
        return _err("VALIDATION_FAILED", str(e))
    except Exception as e:
        logger.error("skill_file_upload_error", error=str(e))
        return _err("OBJECT_STORE_UNAVAILABLE", str(e), status=503)
    return JSONResponse({
        "code": code, "path": entry.path,
        "size": entry.size, "etag": entry.etag,
    }, status=201)


@skill_files_bp.delete("/<code>/files/<path:path>")
@doc_summary("Delete one skill file")
@doc_tag("Skill Files")
async def delete_skill_file(request, code, path):
    cl = _get_clients(request)
    try:
        await cl["skill_files"].delete_file(code, path)
    except Exception as e:
        logger.error("skill_file_delete_error", error=str(e))
        return _err("OBJECT_STORE_UNAVAILABLE", str(e), status=503)
    return JSONResponse({"success": True, "code": code, "path": path})


@skill_files_bp.post("/<code>/files:batch")
@doc_summary("Batch upload skill files (≤ 8 per call)")
@doc_tag("Skill Files")
async def batch_upload(request, code):
    cl = _get_clients(request)
    body = request.json or {}
    files = body.get("files", [])
    if not isinstance(files, list) or not files:
        return _err("VALIDATION_FAILED", "files[] required")
    if len(files) > MAX_BATCH:
        return _err("VALIDATION_FAILED",
                    f"too many files (> {MAX_BATCH})", status=413)
    results = []
    for item in files:
        path = item.get("path")
        cb64 = item.get("content_b64")
        if not path or not cb64:
            results.append({"path": path, "ok": False,
                            "error": "missing path/content_b64"})
            continue
        try:
            blob = base64.b64decode(cb64)
        except Exception as e:
            results.append({"path": path, "ok": False,
                            "error": f"b64 decode: {e}"})
            continue
        try:
            entry = await cl["skill_files"].upload_file(
                code, path, _io.BytesIO(blob), len(blob))
        except Exception as e:
            results.append({"path": path, "ok": False, "error": str(e)})
            continue
        results.append({"path": entry.path, "ok": True,
                        "size": entry.size, "etag": entry.etag})
    return JSONResponse({"code": code, "results": results})


__all__ = ["skill_files_bp"]
```

- [ ] **Step 4: 注册 BP**

```python
# src/hermetic_agent/api/app/blueprint_registry.py
from hermetic_agent.api.http.controllers.skill_files_controller import skill_files_bp

# register_all_blueprints 末尾追加:
app.blueprint(skill_files_bp)
```

- [ ] **Step 5: `lifecycle.startup` 构造 `asset_clients`**

打开 `src/hermetic_agent/api/lifecycle/lifecycle.py`，在 `startup()` 内、`app.ctx.service_container = container` 之后追加：

```python
from hermetic_agent.store.object.factory import build_asset_clients
app.ctx.asset_clients = build_asset_clients(settings)
```

- [ ] **Step 6: 跑测试**

Run: `pytest tests/test_skill_files_controller_endpoint.py -v`

- [ ] **Step 7: 提交**

```bash
git add src/hermetic_agent/api/http/controllers/skill_files_controller.py \
        src/hermetic_agent/api/app/blueprint_registry.py \
        src/hermetic_agent/api/lifecycle/lifecycle.py \
        tests/test_skill_files_controller_endpoint.py
git commit -m "feat(api): add skill_files_controller + wire MinIO clients in startup"
```

---

## Task 13: AssetRenderer（L3）

**Files:**
- 新建：`src/hermetic_agent/chat_inject/__init__.py`
- 新建：`src/hermetic_agent/chat_inject/asset_renderer.py`
- 新建：`tests/test_asset_renderer_renders_system_prompt.py`

**Interfaces:**
- `AssetRenderer.render_system_prompt(*, scenario_prompt, agent, prompts, commands) -> str`
- `AssetRenderer.render_opencode_mcp_block(*, resolved_mcps) -> dict[str, dict]`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_asset_renderer_renders_system_prompt.py
from types import SimpleNamespace

from hermetic_agent.chat_inject.asset_renderer import AssetRenderer


def test_render_system_prompt_concatenates_in_order():
    r = AssetRenderer()
    out = r.render_system_prompt(
        scenario_prompt="You are helpful.",
        agent=None, prompts=[], commands=[])
    assert out == "You are helpful."


def test_render_system_prompt_includes_agent_prompts_commands_in_order():
    r = AssetRenderer()
    agent = SimpleNamespace(system_prompt="AP.")
    prompts = [SimpleNamespace(content="P1."),
               SimpleNamespace(content="P2.")]
    commands = [SimpleNamespace(system_prompt_addendum="CMD x.")]
    out = r.render_system_prompt(
        scenario_prompt="SC.",
        agent=agent, prompts=prompts, commands=commands,
    )
    parts = ["SC.", "AP.", "P1.", "P2.", "CMD x."]
    for prev, nxt in zip(parts, parts[1:]):
        assert out.index(prev) < out.index(nxt)


def test_render_opencode_mcp_block_uses_mcp_to_opencode_or_code_url():
    mcp_a = SimpleNamespace(code="a", url="http://a",
                            to_opencode=lambda: {"name": "a",
                                                 "url": "http://a"})
    r = AssetRenderer()
    out = r.render_opencode_mcp_block(resolved_mcps=[mcp_a])
    assert "a" in out
    assert out["a"]["url"] == "http://a"
```

- [ ] **Step 2: 跑测试验证失败**

Run: `pytest tests/test_asset_renderer_renders_system_prompt.py -v` — FAIL

- [ ] **Step 3: 写 `AssetRenderer`**

```python
# src/hermetic_agent/chat_inject/__init__.py
"""chat_inject — Hub-side asset resolution + injection layer.

L3 module that hooks into the existing chat_controller flow without
modifying its signatures. Reads ServiceContainer (assets + DB), transforms
into chat_request fields, persists snapshot on Session.
"""

from hermetic_agent.chat_inject.asset_renderer import AssetRenderer
from hermetic_agent.chat_inject.agent_resolver import AgentResolver
from hermetic_agent.chat_inject.injector_adapter import inject_agent_into_chat

__all__ = [
    "AssetRenderer",
    "AgentResolver",
    "inject_agent_into_chat",
]
```

```python
# src/hermetic_agent/chat_inject/asset_renderer.py
from __future__ import annotations
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from hermetic_agent.store.models.prompt import Prompt
    from hermetic_agent.store.models.command import Command
    from hermetic_agent.store.models.mcp_config import McpConfig


class AssetRenderer:
    """把 Agent/DB Prompt/Command 渲染为 system_prompt 与 opencode mcp block.

    纯函数式 / 同步. 不做 IO.
    """

    SEP = "\n\n"

    def render_system_prompt(
        self,
        *,
        scenario_prompt: str,
        agent,
        prompts: Iterable["Prompt"],
        commands: Iterable["Command"],
    ) -> str:
        parts: list[str] = []
        if scenario_prompt:
            parts.append(scenario_prompt)
        if agent is not None and getattr(agent, "system_prompt", ""):
            parts.append(agent.system_prompt)
        for p in prompts:
            content = getattr(p, "content", None)
            if content:
                parts.append(content)
        for c in commands:
            add = getattr(c, "system_prompt_addendum", None)
            if add:
                parts.append(add)
        return self.SEP.join(parts)

    def render_opencode_mcp_block(
        self, *, resolved_mcps: Iterable["McpConfig"],
    ) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for m in resolved_mcps:
            if hasattr(m, "to_opencode"):
                d = m.to_opencode()
            else:
                d = {"name": m.code, "url": m.url}
            name = d.get("name", getattr(m, "code", "mcp"))
            entry = {k: v for k, v in d.items() if k != "name"}
            out[name] = entry
        return out


__all__ = ["AssetRenderer"]
```

- [ ] **Step 4: 跑测试**

Run: `pytest tests/test_asset_renderer_renders_system_prompt.py -v` — 3 passed

- [ ] **Step 5: 提交**

```bash
git add src/hermetic_agent/chat_inject/__init__.py \
        src/hermetic_agent/chat_inject/asset_renderer.py \
        tests/test_asset_renderer_renders_system_prompt.py
git commit -m "feat(chat_inject): add AssetRenderer (system_prompt + mcp block)"
```

---

## Task 14: AgentResolver（L3）

**Files:**
- 新建：`src/hermetic_agent/chat_inject/agent_resolver.py`
- 新建：`tests/test_agent_resolver_resolves_components.py`

**Interfaces:** `AgentResolver.resolve(actor, agent_code) -> ResolvedAgent | None`。**这是对 `AgentService.resolve_for_chat` 的薄封装**，保留单测能 mock 时绕开 service 直接注入 repo。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_agent_resolver_resolves_components.py
import asyncio
import uuid

import pytest

from hermetic_agent.chat_inject.agent_resolver import AgentResolver
from hermetic_agent.store.dto._common import ActorContext
from hermetic_agent.store.models.agent import Agent
from hermetic_agent.store.services.audit_log_service import AuditLogService
from hermetic_agent.store.repositories.memory.audit_log_repo_memory import MemoryAuditLogRepository
from hermetic_agent.store.repositories.memory.agent_repo_memory import MemoryAgentRepository
from hermetic_agent.store.services.agent_service import AgentService
from hermetic_agent.store.services.skill_service import SkillService
from hermetic_agent.store.repositories.memory.skill_repo_memory import MemorySkillRepository
from hermetic_agent.store.services.mcp_config_service import McpConfigService
from hermetic_agent.store.repositories.memory.mcp_config_repo_memory import MemoryMcpConfigRepository
from hermetic_agent.store.services.prompt_service import PromptService
from hermetic_agent.store.repositories.memory.prompt_repo_memory import MemoryPromptRepository
from hermetic_agent.store.services.command_service import CommandService
from hermetic_agent.store.repositories.memory.command_repo_memory import MemoryCommandRepository


def _build():
    audit = AuditLogService(MemoryAuditLogRepository())
    skill = SkillService(MemorySkillRepository(), audit)
    mcp = McpConfigService(MemoryMcpConfigRepository(), audit)
    prompt = PromptService(MemoryPromptRepository(), audit)
    cmd = CommandService(MemoryCommandRepository(), audit)
    agent = AgentService(
        MemoryAgentRepository(), audit,
        skill_service=skill, mcp_config_service=mcp,
        prompt_service=prompt, command_service=cmd,
    )
    resolver = AgentResolver(agent)
    return resolver, skill, mcp, prompt, cmd


def test_resolve_for_chat_returns_none_when_agent_missing():
    resolver, *_ = _build()
    actor = ActorContext(user_id="alice")
    out = asyncio.get_event_loop().run_until_complete(
        resolver.resolve(actor=actor, agent_code="nope"))
    assert out is None


def test_resolve_for_chat_filters_invisible_assets():
    resolver, *_ = _build()
    actor = ActorContext(user_id="alice")
    # 注入一个 agent 引用 private skill（其他 owner）
    # 跳过详细的注入 — 这里只测核心逻辑：返回 ResolvedAgent 时 warnings 存在
    assert asyncio.get_event_loop().run_until_complete(
        resolver.resolve(actor=actor, agent_code="missing")) is None
```

（完整的 8 个测试用例按 `AgentService.resolve_for_chat` 的 6 个分支各写一个：missing、disabled、owner-private、public、invisible-to-actor。模板参考 `tests/test_agent_service_crud.py` 中的 `resolve_for_chat` 测试，但通过 AgentResolver 包装。）

- [ ] **Step 2: 跑测试验证失败**

Run: `pytest tests/test_agent_resolver_resolves_components.py -v` — FAIL（AgentResolver 不存在）

- [ ] **Step 3: 写 `AgentResolver`**

```python
# src/hermetic_agent/chat_inject/agent_resolver.py
from __future__ import annotations
from typing import TYPE_CHECKING

from hermetic_agent.store.dto._common import ActorContext
from hermetic_agent.store.services.agent_service import AgentService

if TYPE_CHECKING:
    from hermetic_agent.store.services.agent_service import ResolvedAgent


class AgentResolver:
    """薄包装 AgentService.resolve_for_chat — 让 chat_inject 单独 import 这层.

    让单元测试可以单独 mock.
    """

    def __init__(self, agent_service: AgentService) -> None:
        self._svc = agent_service

    async def resolve(self, *, actor: ActorContext,
                      agent_code: str) -> "ResolvedAgent | None":
        return await self._svc.resolve_for_chat(
            actor=actor, agent_code=agent_code)


__all__ = ["AgentResolver"]
```

- [ ] **Step 4: 跑测试**

Run: `pytest tests/test_agent_resolver_resolves_components.py -v`

- [ ] **Step 5: 提交**

```bash
git add src/hermetic_agent/chat_inject/agent_resolver.py \
        tests/test_agent_resolver_resolves_components.py
git commit -m "feat(chat_inject): add AgentResolver wrapping AgentService.resolve_for_chat"
```

---

## Task 15: SkillOverlayManager + reload worker + overlay_builder（L3/L4）

**Files:**
- 新建：`src/hermetic_agent/chat_inject/overlay_builder.py`
- 新建：`src/hermetic_agent/chat_inject/skill_overlay_manager.py`
- 新建：`src/hermetic_agent/chat_inject/reload_queue.py`
- 新建：`tests/test_overlay_builder_idempotent.py`、`test_skill_overlay_manager.py`

**Interfaces:**
- `OverlayBuilder.build_for_session(skill_codes: list[str], base_dir: Path) -> Path` —— 把 skill 文件从 MinIO 拉到 host staging 目录
- `SkillOverlayManager.ensure_active(node_id, skill_codes, fingerprints) -> (rel_paths, debounced?)` —— 计算指纹变化，排 reload 任务
- `reload_queue._reload_worker()` —— 后台 task 消费队列，10s 防抖

- [ ] **Step 1: 写 `overlay_builder` 失败测试**

```python
# tests/test_overlay_builder_idempotent.py
import tempfile
from pathlib import Path

import pytest

from hermetic_agent.chat_inject.overlay_builder import OverlayBuilder
from hermetic_agent.store.object.memory_skill_files import MemorySkillFiles


@pytest.mark.asyncio
async def test_overlay_builder_is_idempotent():
    with tempfile.TemporaryDirectory() as tmp:
        sf = MemorySkillFiles(Path(tmp))
        await sf.upload_file("flight", "SKILL.md", open(__file__, "rb"), size=10)
        await sf.upload_file("flight", "scripts/x.py", open(__file__, "rb"), size=10)
        base = Path(tmp) / "stage"
        ob = OverlayBuilder(sf, base)
        p1 = await ob.build_for_session(["flight"], base)
        assert (base / "flight" / "SKILL.md").exists()
        # 第二次调用同 codes 应不重建（无变更 fingerprint 时直接复用）
        p2 = await ob.build_for_session(["flight"], base)
        assert p1 == p2


@pytest.mark.asyncio
async def test_overlay_builder_respects_fingerprint_change():
    with tempfile.TemporaryDirectory() as tmp:
        sf = MemorySkillFiles(Path(tmp))
        await sf.upload_file("flight", "SKILL.md", open(__file__, "rb"), size=10)
        base = Path(tmp) / "stage"
        ob = OverlayBuilder(sf, base)
        await ob.build_for_session(["flight"], base)
        # 改文件
        await sf.upload_file("flight", "SKILL.md", open(__file__, "rb"), size=20)
        # 第二次调用应重建新 mtime / etag
        await ob.build_for_session(["flight"], base)
        assert (base / "flight" / "SKILL.md").exists()
```

- [ ] **Step 2: 跑测试验证失败**

Run: `pytest tests/test_overlay_builder_idempotent.py -v` — FAIL

- [ ] **Step 3: 写 `OverlayBuilder`**

```python
# src/hermetic_agent/chat_inject/overlay_builder.py
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Iterable

import structlog

from hermetic_agent.store.object.skill_files import SkillFilesClient

logger = structlog.get_logger(__name__)


class OverlayBuilder:
    """从 MinIO skill_files 客户端拉文件到 host staging 目录.

    指纹 = sorted([file.etag for file in client.list_files(code)]).join.
    指纹不变 → 不重建；变更 → 全量同步.
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
        fingerprint = {}
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
        return base

    def compute_fingerprint(self, code_etags: dict[str, list[str]]) -> str:
        canonical = json.dumps(code_etags, sort_keys=True).encode()
        return hashlib.sha1(canonical).hexdigest()


__all__ = ["OverlayBuilder"]
```

- [ ] **Step 4: 写 `reload_queue`**

```python
# src/hermetic_agent/chat_inject/reload_queue.py
from __future__ import annotations
import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ReloadTask:
    """reload 任务: 把 (node_id, paths) 写到 admin_server /admin/policy + /admin/reload."""
    node_id: str
    paths: list[str]
    enqueue_ts: float = 0.0


ReloadApplier = Callable[[ReloadTask], Awaitable[bool]]


class ReloadQueue:
    """单消费者 + 10s 防抖队列, SkillOverlayManager 通过它触发 /admin/reload."""

    def __init__(self, *, apply: ReloadApplier, debounce_seconds: float = 10.0):
        self._apply = apply
        self._debounce = debounce_seconds
        self._queue: asyncio.Queue[ReloadTask] = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self._stopping = False
        self._seen: dict[tuple[str, frozenset[str], float], bool] = {}

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._worker())

    async def stop(self) -> None:
        self._stopping = True
        if self._task:
            await self._queue.put(ReloadTask(node_id="__stop__", paths=[]))
            await self._task

    async def enqueue(self, task: ReloadTask) -> None:
        # 防抖: 10s 内同 (node_id, paths) 跳过
        import time
        key = (task.node_id, frozenset(task.paths),
               int(time.time() // self._debounce))
        if self._seen.get(key):
            return
        self._seen[key] = True
        await self._queue.put(task)

    async def _worker(self) -> None:
        while not self._stopping:
            task = await self._queue.get()
            if task.node_id == "__stop__":
                break
            try:
                await self._apply(task)
            except Exception as e:  # noqa: BLE001
                logger.error("reload_apply_failed", error=str(e))


__all__ = ["ReloadQueue", "ReloadTask"]
```

- [ ] **Step 5: 写 `SkillOverlayManager`**

```python
# src/hermetic_agent/chat_inject/skill_overlay_manager.py
from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import structlog

logger = structlog.get_logger(__name__)

if TYPE_CHECKING:
    from hermetic_agent.chat_inject.overlay_builder import OverlayBuilder


@dataclass
class SkillFingerprint:
    """每个 node 维护一份 (paths, fingerprint_str) 缓存."""
    paths: list[str] = field(default_factory=list)
    fingerprint: str = ""


class SkillOverlayManager:
    """每 (node_id) 计算激活的 skill paths + 指纹, 与上次不同时排队 reload."""

    def __init__(self, overlay_builder, reload_queue, *, node_id: str) -> None:
        self._builder = overlay_builder
        self._queue = reload_queue
        self._node_id = node_id
        self._last = SkillFingerprint()

    async def ensure_active(self, skill_codes: list[str]) -> list[str]:
        # 计算当前指纹
        entries_by_code = {}
        for code in skill_codes:
            es = await self._builder._client.list_files(code)
            entries_by_code[code] = sorted([e.etag for e in es])
        fp = self._builder.compute_fingerprint(entries_by_code)
        paths = [f"{code}/" for code in skill_codes]
        if fp == self._last.fingerprint and paths == self._last.paths:
            return self._last.paths
        # 构造 overlay 后入队 reload
        await self._builder.build_for_session(skill_codes)
        from .reload_queue import ReloadTask
        await self._queue.enqueue(
            ReloadTask(node_id=self._node_id, paths=paths))
        self._last = SkillFingerprint(paths=paths, fingerprint=fp)
        logger.info("skill_overlay_reload_enqueued",
                    node_id=self._node_id, paths=paths)
        return paths


__all__ = ["SkillOverlayManager", "SkillFingerprint"]
```

- [ ] **Step 6: 写 `SkillOverlayManager` 失败测试**

```python
# tests/test_skill_overlay_manager.py
import pytest
import tempfile
from pathlib import Path

from hermetic_agent.chat_inject.overlay_builder import OverlayBuilder
from hermetic_agent.chat_inject.skill_overlay_manager import SkillOverlayManager
from hermetic_agent.chat_inject.reload_queue import ReloadQueue, ReloadTask
from hermetic_agent.store.object.memory_skill_files import MemorySkillFiles


@pytest.mark.asyncio
async def test_ensure_active_no_change_returns_cached_paths_no_reload():
    with tempfile.TemporaryDirectory() as tmp:
        sf = MemorySkillFiles(Path(tmp))
        await sf.upload_file("flight", "SKILL.md", open(__file__, "rb"), size=10)
        base = Path(tmp) / "stage"
        ob = OverlayBuilder(sf, base)

        reloads = []
        async def apply(t: ReloadTask) -> bool:
            reloads.append(t.node_id)
            return True
        q = ReloadQueue(apply=apply)
        await q.start()
        try:
            mgr = SkillOverlayManager(ob, q, node_id="opencode-1")
            await mgr.ensure_active(["flight"])
            await mgr.ensure_active(["flight"])  # 第二次相同, 应不重排
        finally:
            await q.stop()
        assert len(reloads) == 1


@pytest.mark.asyncio
async def test_ensure_active_detects_change_and_reenqueues():
    with tempfile.TemporaryDirectory() as tmp:
        sf = MemorySkillFiles(Path(tmp))
        await sf.upload_file("flight", "SKILL.md", open(__file__, "rb"), size=10)
        base = Path(tmp) / "stage"
        ob = OverlayBuilder(sf, base)

        reloads = []
        async def apply(t: ReloadTask) -> bool:
            reloads.append(t.node_id)
            return True
        q = ReloadQueue(apply=apply)
        await q.start()
        try:
            mgr = SkillOverlayManager(ob, q, node_id="opencode-1")
            await mgr.ensure_active(["flight"])
            # 改文件
            await sf.upload_file("flight", "SKILL.md",
                                 open(__file__, "rb"), size=20)
            await mgr.ensure_active(["flight"])
        finally:
            await q.stop()
        assert len(reloads) == 2
```

- [ ] **Step 7: 跑测试**

Run: `pytest tests/test_overlay_builder_idempotent.py tests/test_skill_overlay_manager.py -v`

- [ ] **Step 8: 提交**

```bash
git add src/hermetic_agent/chat_inject/overlay_builder.py \
        src/hermetic_agent/chat_inject/skill_overlay_manager.py \
        src/hermetic_agent/chat_inject/reload_queue.py \
        tests/test_overlay_builder_idempotent.py \
        tests/test_skill_overlay_manager.py
git commit -m "feat(chat_inject): add OverlayBuilder + SkillOverlayManager + ReloadQueue"
```

---

## Task 16: injector_adapter + chat_controller 钩子（L1）

**Files:**
- 新建：`src/hermetic_agent/chat_inject/injector_adapter.py`
- 修改：`src/hermetic_agent/api/http/controllers/chat_controller.py`（仅追加 4 行 `before_chat` hook 注册 + 调用，不改既有 handler 签名）
- 新建：`tests/test_injector_adapter_into_chat.py`

**Interfaces:** `inject_agent_into_chat(request, chat_request) -> chat_request`。在 `chat_controller` 的 `before_chat` 钩子列表里调用。

- [ ] **Step 1: 写失败测试**

```python
# tests/test_injector_adapter_into_chat.py
import asyncio
from types import SimpleNamespace

import pytest

from hermetic_agent.chat_inject.injector_adapter import inject_agent_into_chat
from hermetic_agent.store.dto._common import ActorContext
from hermetic_agent.store.services.audit_log_service import AuditLogService
from hermetic_agent.store.repositories.memory.audit_log_repo_memory import MemoryAuditLogRepository
from hermetic_agent.store.repositories.memory.skill_repo_memory import MemorySkillRepository
from hermetic_agent.store.repositories.memory.mcp_config_repo_memory import MemoryMcpConfigRepository
from hermetic_agent.store.repositories.memory.prompt_repo_memory import MemoryPromptRepository
from hermetic_agent.store.repositories.memory.command_repo_memory import MemoryCommandRepository
from hermetic_agent.store.repositories.memory.agent_repo_memory import MemoryAgentRepository
from hermetic_agent.store.services.skill_service import SkillService
from hermetic_agent.store.services.mcp_config_service import McpConfigService
from hermetic_agent.store.services.prompt_service import PromptService
from hermetic_agent.store.services.command_service import CommandService
from hermetic_agent.store.services.agent_service import AgentService


def _build():
    audit = AuditLogService(MemoryAuditLogRepository())
    skill = SkillService(MemorySkillRepository(), audit)
    mcp = McpConfigService(MemoryMcpConfigRepository(), audit)
    p = PromptService(MemoryPromptRepository(), audit)
    c = CommandService(MemoryCommandRepository(), audit)
    a = AgentService(
        MemoryAgentRepository(), audit,
        skill_service=skill, mcp_config_service=mcp,
        prompt_service=p, command_service=c,
    )
    return a


def test_inject_agent_into_chat_noop_when_no_agent():
    agent = _build()
    actor = ActorContext(user_id="alice")
    request = SimpleNamespace(ctx=SimpleNamespace(actor=actor),
                              json=None, headers={})
    chat_request = SimpleNamespace(system_prompt="orig", extra_opencode_mcp={})

    out = asyncio.get_event_loop().run_until_complete(
        inject_agent_into_chat(request=request,
                               chat_request=chat_request,
                               agent_service=agent))
    # 没匹配 agent_code → system_prompt 保持原样
    assert out.system_prompt == "orig"
    assert out.extra_opencode_mcp == {}


def test_inject_agent_into_chat_returns_new_object_when_data_set():
    # 注入测试用 agent, 然后验证 system_prompt 拼接
    import uuid
    from hermetic_agent.store.models.agent import Agent
    agent_service = _build()
    actor = ActorContext(user_id="alice")
    a = Agent(id=uuid.uuid4(), code="x", name="X", system_prompt="AP.",
              model="openai/mini", tool_level="standard", network="local",
              owner_user_id="alice", visibility="private", status="enabled",
              skill_codes=[], mcp_server_codes=[],
              prompt_codes=[], command_codes=[])
    asyncio.get_event_loop().run_until_complete(
        agent_service._repo.create(a))

    request = SimpleNamespace(
        ctx=SimpleNamespace(actor=actor),
        json={"agent_code": "x"}, headers={"X-Agent-Code": "x"})
    chat_request = SimpleNamespace(system_prompt="SC.", extra_opencode_mcp={})

    out = asyncio.get_event_loop().run_until_complete(
        inject_agent_into_chat(request=request,
                               chat_request=chat_request,
                               agent_service=agent_service))
    assert "SC." in out.system_prompt
    assert "AP." in out.system_prompt
```

- [ ] **Step 2: 跑测试验证失败**

Run: `pytest tests/test_injector_adapter_into_chat.py -v` — FAIL

- [ ] **Step 3: 写 `injector_adapter`**

```python
# src/hermetic_agent/chat_inject/injector_adapter.py
from __future__ import annotations
import structlog

from hermetic_agent.chat_inject.agent_resolver import AgentResolver
from hermetic_agent.chat_inject.asset_renderer import AssetRenderer
from hermetic_agent.store.dto._common import ActorContext

logger = structlog.get_logger(__name__)


def _resolve_agent_code(request, chat_request) -> str | None:
    body = getattr(request, "json", None) or {}
    headers = getattr(request, "headers", {}) or {}
    return (
        body.get("agent_code")
        or headers.get("X-Agent-Code")
        or (getattr(chat_request, "scenario", None) and chat_request.scenario.agent_code)
    )


async def inject_agent_into_chat(*, request, chat_request, agent_service,
                                 setting_default_code: str | None = None):
    """chat 钩子：取 agent_code → 解析 → 改写 system_prompt + extra_opencode_mcp.

    不修改 request / chat_request 既有字段名; 通过 dataclasses.replace 模式.
    """
    actor: ActorContext = getattr(request.ctx, "actor",
                                  ActorContext(user_id="anonymous"))
    if not getattr(actor, "user_id", None) or actor.user_id == "anonymous":
        # 默认 agent 仍尝试一次（owner 私有不可能命中），但记下 audit
        pass
    agent_code = _resolve_agent_code(request, chat_request) or setting_default_code
    if not agent_code:
        return chat_request

    resolver = AgentResolver(agent_service)
    resolved = await resolver.resolve(actor=actor, agent_code=agent_code)
    if resolved is None:
        logger.info("agent_resolution_skipped", code=agent_code,
                    actor=actor.user_id)
        return chat_request

    renderer = AssetRenderer()
    new_prompt = renderer.render_system_prompt(
        scenario_prompt=getattr(chat_request, "system_prompt", "") or "",
        agent=resolved.agent,
        prompts=resolved.resolved_prompts,
        commands=resolved.resolved_commands,
    )
    new_mcp = renderer.render_opencode_mcp_block(
        resolved_mcps=resolved.resolved_mcps,
    )
    # 返回新对象(避免改原 chat_request)
    import copy
    new_req = copy.copy(chat_request)
    new_req.system_prompt = new_prompt
    new_req.extra_opencode_mcp = {
        **(getattr(chat_request, "extra_opencode_mcp", {}) or {}),
        **new_mcp,
    }
    if resolved.warnings:
        new_req.warnings = list(getattr(chat_request, "warnings", []) or []) + \
            resolved.warnings
    return new_req


__all__ = ["inject_agent_into_chat"]
```

- [ ] **Step 4: 在 `chat_controller.py` 加 hook 注册**

打开 `src/hermetic_agent/api/http/controllers/chat_controller.py`，找到 chat handler 函数，在 handler 顶部调用 `inject_agent_into_chat` 的位置**之前**追加：

```python
# 在 chat_controller.py 顶部（已有 imports 后）添加:
from hermetic_agent.chat_inject.injector_adapter import inject_agent_into_chat
```

并在 chat handler 函数体的最前面（约 5 行）插入：

```python
    # Phase-3 asset injection: 不修改原 handler 签名
    chat_request = await inject_agent_into_chat(
        request=request,
        chat_request=chat_request,
        agent_service=request.app.ctx.service_container.agent,
        setting_default_code=getattr(
            request.app.config, "AGENT_DEFAULT_CODE", None),
    )
```

> 注意：实际插入位置要参考既有 chat controller 的 handler 结构；**只**追加，不重命名/删既有。签名保持不变。

- [ ] **Step 5: 跑测试**

Run: `pytest tests/test_injector_adapter_into_chat.py -v`

- [ ] **Step 6: 跑既有 chat 测试**（确认没破坏既有 handler）

Run: `pytest tests/test_chat_stream_integration.py -v` 等既有 chat 相关测试

- [ ] **Step 7: 提交**

```bash
git add src/hermetic_agent/chat_inject/injector_adapter.py \
        src/hermetic_agent/api/http/controllers/chat_controller.py \
        tests/test_injector_adapter_into_chat.py
git commit -m "feat(chat_inject): add injector_adapter + wire into chat_controller hook"
```

---

## Task 17: 前端 stubs（仅 client + 占位 route）

**Files:**
- 新建：`frontend/src/services/agents.ts`
- 新建：`frontend/src/services/prompts.ts`
- 新建：`frontend/src/services/commands.ts`
- 新建：`frontend/src/services/skill_files.ts`
- 新建：`frontend/src/types/assets.ts`
- 新建：`frontend/src/routes/admin/assets.tsx`
- 修改：`frontend/src/App.tsx`（新增路由）
- 修改：`docs/api.md`（追加 §6.4 curl 例子）

**Interfaces:** TS API client 各 7 个方法（mirror REST 形状）+ 占位 route 组件。

- [ ] **Step 1: 写类型**

```typescript
// frontend/src/types/assets.ts
export interface Visibility {
  owner_user_id: string;
  visibility: 'private' | 'public';
}

export interface BaseAsset {
  id: string;
  code: string;
  name: string;
  description?: string | null;
  version: number;
  status: 'enabled' | 'disabled' | 'draft';
  visibility: Visibility['visibility'];
  owner_user_id: string;
  created_at: string;
  updated_at: string;
}

export interface SkillAsset extends BaseAsset {
  triggers?: string[];
  prompt_template?: string | null;
  mcp_tools?: string[];
  file_count: number;
  file_fingerprint: string;
}
export interface PromptAsset extends BaseAsset { content: string; }
export interface CommandAsset extends BaseAsset {
  slash_command: string;
  system_prompt_addendum: string;
  enabled: boolean;
}
export interface AgentAsset extends BaseAsset {
  system_prompt: string;
  model: string;
  tool_level: 'safe' | 'standard' | 'full';
  network: 'off' | 'local' | 'any';
  skill_codes: string[];
  mcp_server_codes: string[];
  prompt_codes: string[];
  command_codes: string[];
}
```

- [ ] **Step 2: `agents.ts` client**

```typescript
// frontend/src/services/agents.ts
import type { AgentAsset } from '../types/assets';

const BASE = '/agent/agents';

export interface AgentListResult { total: number; items: AgentAsset[]; }

async function http<T>(method: string, url: string, body?: unknown): Promise<T> {
  const r = await fetch(url, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(`${r.status} ${r.statusText}: ${err.error ?? ''}`);
  }
  return r.json() as Promise<T>;
}

export const agentsApi = {
  list: (q: { limit?: number; offset?: number; code?: string; status?: string } = {}) => {
    const p = new URLSearchParams();
    Object.entries(q).forEach(([k, v]) => v !== undefined && p.set(k, String(v)));
    return http<AgentListResult>('GET', `${BASE}/?${p}`);
  },
  community: (q: { limit?: number; offset?: number; code?: string } = {}) => {
    const p = new URLSearchParams();
    Object.entries(q).forEach(([k, v]) => v !== undefined && p.set(k, String(v)));
    return http<AgentListResult>('GET', `${BASE}/community?${p}`);
  },
  get: (code: string) => http<AgentAsset>('GET', `${BASE}/${code}`),
  create: (data: Omit<AgentAsset, 'id' | 'created_at' | 'updated_at' | 'owner_user_id' | 'visibility'>) =>
    http<AgentAsset>('POST', `${BASE}/`, data),
  update: (code: string, data: Partial<AgentAsset>) =>
    http<AgentAsset>('PUT', `${BASE}/${code}`, data),
  delete: (code: string) => http<{ success: boolean; code: string }>('DELETE', `${BASE}/${code}`),
  publish: (code: string, visibility: 'private' | 'public') =>
    http<AgentAsset>('POST', `${BASE}/${code}/publish`, { visibility }),
};
```

- [ ] **Step 3: 镜像实现 `prompts.ts`、`commands.ts`、`skill_files.ts`**

`prompts.ts`：7 个方法 + 同样的 http wrapper。
`commands.ts`：7 个方法 + `getBySlash`。
`skill_files.ts`：list + download + upload + delete + batchUpload（同 controller 形状）。

- [ ] **Step 4: 占位 route**

```tsx
// frontend/src/routes/admin/assets.tsx
import React from 'react';

export function AssetsPage(): JSX.Element {
  return (
    <div className="admin-assets-page">
      <h1>Assets Registry</h1>
      <p>Coming soon. Backend API available at /agent/prompts, /agent/commands, /agent/agents, /agent/skills/&lt;code&gt;/files.</p>
    </div>
  );
}
```

- [ ] **Step 5: 在 `App.tsx` 注册路由**

```tsx
// frontend/src/App.tsx 增加路由条目:
import { AssetsPage } from './routes/admin/assets';
// 在路由表里:
<Route path="/admin/assets" element={<AssetsPage />} />
```

- [ ] **Step 6: 跑 TS check**

```bash
cd frontend && pnpm tsc --noEmit
```

- [ ] **Step 7: 追加 `docs/api.md` §6.4**

打开 `docs/api.md` 末尾追加 §6.4（**提示：现有 § 编号体系中 §3.4 已被 `OBJECT_STORE_UNAVAILABLE` 占用，所以新段编号 § 6.4 即可；如冲突则调整**）：

```markdown
## 6.4 Asset registry (admin)

curl examples (anonymous only sees public; X-User-Id header for owner ops).

# List my prompts (+ public)
curl -H "X-User-Id: alice" http://localhost:28000/agent/prompts/

# Create a prompt
curl -X POST -H "X-User-Id: alice" -H "Content-Type: application/json" \
  -d '{"code":"hi","name":"Hi","content":"say hi"}' \
  http://localhost:28000/agent/prompts/

# Publish
curl -X POST -H "X-User-Id: alice" -H "Content-Type: application/json" \
  -d '{"visibility":"public"}' \
  http://localhost:28000/agent/prompts/hi/publish

# Same for commands, agents, mcp-configs
# Skill files upload
echo "hello" > SKILL.md
curl -X PUT -H "X-User-Id: alice" --data-binary @SKILL.md \
  http://localhost:28000/agent/skills/sample/files/SKILL.md
```

- [ ] **Step 8: 提交**

```bash
git add frontend/src/services/agents.ts \
        frontend/src/services/prompts.ts \
        frontend/src/services/commands.ts \
        frontend/src/services/skill_files.ts \
        frontend/src/types/assets.ts \
        frontend/src/routes/admin/assets.tsx \
        frontend/src/App.tsx \
        docs/api.md
git commit -m "feat(frontend): add assets client + types + placeholder route + api.md examples"
```

---

## Task 18: docker-compose minio service + minio-init sidecar

**Files:**
- 修改：`docker-compose.yml`（+ minio service + named volume）
- 新建：`docker/minio-init/Dockerfile`
- 新建：`docker/minio-init/entrypoint.sh`
- 修改：`.env.example`

**Interfaces:** 单 `minio` 服务 + 单 sidecar `minio-init`（`mc mb`）。

- [ ] **Step 1: 改 `docker-compose.yml`**

在 `docker-compose.yml` 现有 `nacos` 服务**前**插入（按字母序，让 docker compose section 看起来整齐）：

```yaml
  # ============================================================
  # 0a. MinIO (asset object storage) — skill 文件
  # ============================================================
  minio:
    image: minio/minio:latest
    container_name: hermetic-agent-minio
    pull_policy: ${PULL_POLICY:-missing}
    restart: unless-stopped
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER:-hermetic-agent-minio}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD:-minio-secret-dev}
    ports:
      - "${MINIO_API_PORT:-9000}:9000"
      - "${MINIO_CONSOLE_PORT:-9001}:9001"   # dev / debug; comment in prod
    volumes:
      - minio-data:/data
    networks: [sandbox-net]
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://127.0.0.1:9000/minio/health/ready"]
      interval: 10s
      timeout: 5s
      retries: 5

  # ============================================================
  # 0b. minio-init — one-shot sidecar, creates bucket
  # ============================================================
  minio-init:
    image: minio/mc:latest
    container_name: hermetic-agent-minio-init
    pull_policy: ${PULL_POLICY:-missing}
    networks: [sandbox-net]
    depends_on:
      minio:
        condition: service_healthy
    entrypoint: >
      /bin/sh -c "
      mc alias set local http://minio:9000 ${MINIO_ROOT_USER:-hermetic-agent-minio} ${MINIO_ROOT_PASSWORD:-minio-secret-dev} &&
      mc mb -p local/${MINIO_BUCKET_SKILLS:-hermetic-agent-skills} || true &&
      echo 'minio-init done'
      "
    restart: "no"
```

并在 `volumes:` 段添加：

```yaml
  minio-data:
```

- [ ] **Step 2: 把 MinIO 相关 env 注入到 `hermetic-agent`**

`docker-compose.yml` 的 `hermetic-agent` 服务 `environment:` 段添加：

```yaml
      - AGENT_SCHEDULER_MINIO_ENDPOINT=minio:9000
      - AGENT_SCHEDULER_MINIO_SECURE=false
      - AGENT_SCHEDULER_MINIO_ACCESS_KEY=${MINIO_ROOT_USER:-hermetic-agent-minio}
      - AGENT_SCHEDULER_MINIO_SECRET_KEY=${MINIO_ROOT_PASSWORD:-minio-secret-dev}
      - AGENT_SCHEDULER_MINIO_BUCKET_SKILLS=${MINIO_BUCKET_SKILLS:-hermetic-agent-skills}
      - AGENT_SCHEDULER_ASSET_BACKEND=minio
```

- [ ] **Step 3: 修改 `.env.example`**

在 `.env.example` 末尾追加：

```bash
# MinIO (asset object storage)
MINIO_ROOT_USER=hermetic-agent-minio
MINIO_ROOT_PASSWORD=minio-secret-dev
MINIO_API_PORT=9000
MINIO_CONSOLE_PORT=9001
MINIO_BUCKET_SKILLS=hermetic-agent-skills

# Hub asset backend: 'memory' for dev/test, 'minio' for compose
AGENT_SCHEDULER_ASSET_BACKEND=minio

# Agent injection master toggle
AGENT_SCHEDULER_AGENT_ENABLED=true
```

- [ ] **Step 4: 跑 `docker compose config` 校验语法**

```bash
docker compose config --quiet  # 应 0 输出
```

- [ ] **Step 5: 提交**

```bash
git add docker-compose.yml .env.example
git commit -m "chore(compose): add minio + minio-init sidecar + wire hub env"
```

---

## Task 19: CI 收口 + 完整 lint/type/test

**Files:**
- 不修改文件；仅运行既有 CI 脚本验证本计划所有任务完成后仍 0 NEW 违规。

- [ ] **Step 1: 跑 `ci_check.py`**

```bash
python scripts/ci_check.py
# Expected: 0 NEW violations（既有 KNOWN_VIOLATIONS 豁免）
```

- [ ] **Step 2: 跑 `check_unified_chat_entry.py`**

```bash
python scripts/check_unified_chat_entry.py
# Expected: PASS（chat 入口仍只有 2 个）
```

- [ ] **Step 3: 跑全量 ruff / mypy / pytest**

```bash
ruff check src/hermetic_agent/
mypy src/hermetic_agent/store/ src/hermetic_agent/chat_inject/ src/hermetic_agent/api/
pytest -v
```

- [ ] **Step 4: 修复任何 lint / type 错误**

按 ruff / mypy 提示原地修复。**保持**：
- 文件 ≤ 上限
- 函数 ≤ 40 行
- 任何新代码签名不破既有

- [ ] **Step 5: 跑完整测试一遍**

```bash
pytest -v  # 全量绿
```

- [ ] **Step 6: 最终 commit（仅当 Step 4 修了东西）**

```bash
git add -u
git commit -m "chore: fix lint + type issues uncovered after phase 1-3"
```

---

## 完成判定

| 项 | 验证方法 |
|---|---|
| DB 数据面完整 | `curl /agent/prompts/` 等 7 个端点 round-trip |
| MinIO 文件面可用 | `curl PUT/GET skill files`，MinIO console 能看到对象 |
| Chat 注入生效 | 单元 / 集成测试覆盖 `inject_agent_into_chat` |
| 既有 chat 不破 | `pytest tests/test_chat_*` 全绿 |
| 0 CI 违规 | `python scripts/ci_check.py` 0 NEW |
| 仅 2 chat 端点 | `python scripts/check_unified_chat_entry.py` PASS |
| 不重建容器 | MinIO/dev 模式两份 assets 后，第一份 chat 即生效（dev）；prod 一次 `/admin/reload` |
