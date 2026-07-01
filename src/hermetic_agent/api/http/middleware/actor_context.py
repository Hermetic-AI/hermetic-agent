"""ActorContextMiddleware — 从请求 headers 提取调用方身份.

行为:
1. 读取 ``X-User-Id`` header; 不存在则尝试 ``Authorization: Bearer <token>``
   (用 token 当 user_id, 生产应校验 JWT 签名后取 sub claim).
2. 都没有则用 ``"anonymous"`` 兜底.
3. 顺手提取 ``X-Tenant-Id`` 和 ``X-Roles`` (逗号分隔) 写入 ``ActorContext``.
4. 把 ``ActorContext`` 挂到 ``request.ctx.actor`` 供下游 controller / service
   做权限判断与审计.
"""
from __future__ import annotations

from sanic import Sanic
from sanic.request import Request

from hermetic_agent.store.dto._common import ActorContext


class ActorContextMiddleware:
    HEADER_USER_ID = "X-User-Id"
    HEADER_TENANT_ID = "X-Tenant-Id"
    HEADER_ROLES = "X-Roles"
    HEADER_AUTH = "Authorization"

    def __init__(self, app: Sanic) -> None:
        app.register_middleware(self, "request")

    async def __call__(self, request: Request) -> None:
        user_id = request.headers.get(self.HEADER_USER_ID)
        if user_id is None:
            auth = request.headers.get(self.HEADER_AUTH, "")
            if auth.lower().startswith("bearer "):
                user_id = auth.split(" ", 1)[1].strip() or None
        if user_id is None:
            user_id = "anonymous"
        tenant_id = request.headers.get(self.HEADER_TENANT_ID)
        roles_header = request.headers.get(self.HEADER_ROLES, "")
        roles = [r for r in roles_header.split(",") if r.strip()] if roles_header else []
        request.ctx.actor = ActorContext(
            user_id=user_id, tenant_id=tenant_id, roles=roles)


__all__ = ["ActorContextMiddleware"]
