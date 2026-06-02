"""OpenCode Python SDK - Stub

This is a stub module used when the opencode-ai package is not installed.
In production, install the actual SDK: pip install --pre opencode-ai
"""

from __future__ import annotations

from typing import Any, AsyncIterator


class AsyncOpencode:
    """Stub for opencode-ai AsyncOpencode client"""

    def __init__(self, base_url: str, username: str | None = None, password: str | None = None) -> None:
        self.base_url = base_url
        self.session = _SessionStub()


class _SessionStub:
    """Stub for session management"""

    async def create(self, **kwargs: Any) -> Any:
        raise NotImplementedError("opencode-ai not installed")

    async def chat(self, **kwargs: Any) -> Any:
        raise NotImplementedError("opencode-ai not installed")

    async def chat_stream(self, **kwargs: Any) -> AsyncIterator[Any]:
        raise NotImplementedError("opencode-ai not installed")

    async def messages(self, **kwargs: Any) -> Any:
        raise NotImplementedError("opencode-ai not installed")

    async def abort(self, **kwargs: Any) -> None:
        raise NotImplementedError("opencode-ai not installed")

    async def revert(self, **kwargs: Any) -> None:
        raise NotImplementedError("opencode-ai not installed")

    async def summarize(self, **kwargs: Any) -> Any:
        raise NotImplementedError("opencode-ai not installed")

    async def delete(self, **kwargs: Any) -> None:
        raise NotImplementedError("opencode-ai not installed")
