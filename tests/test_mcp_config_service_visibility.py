"""tests/test_mcp_config_service_visibility.py — McpConfigService visibility/list paths.

Phase 4 of asset-registry plan: Service-level wrapper around
``McpConfigRepository.list_visible_to`` / ``list_public`` / ``set_visibility``.

Only Memory backend is exercised (no external DB dependency).
"""
from __future__ import annotations

import uuid

import pytest

from hermetic_agent.store.dto._common import ActorContext
from hermetic_agent.store.models.mcp_config import McpConfig
from hermetic_agent.store.repositories.memory.audit_log_repo_memory import (
    MemoryAuditLogRepository,
)
from hermetic_agent.store.repositories.memory.mcp_config_repo_memory import (
    MemoryMcpConfigRepository,
)
from hermetic_agent.store.services.audit_log_service import AuditLogService
from hermetic_agent.store.services.mcp_config_service import McpConfigService


@pytest.mark.asyncio
async def test_mcp_config_service_list_visible_only_returns_owner_and_public() -> None:
    repo = MemoryMcpConfigRepository()
    audit = AuditLogService(MemoryAuditLogRepository())
    svc = McpConfigService(repo, audit)

    pub = McpConfig(
        id=uuid.uuid4(), code="pub", name="P",
        owner_user_id="bob", visibility="public", status="enabled",
        mcp_type="http", url="http://x",
    )
    priv = McpConfig(
        id=uuid.uuid4(), code="priv", name="P",
        owner_user_id="bob", visibility="private", status="enabled",
        mcp_type="http", url="http://x",
    )
    repo._store[pub.id] = pub
    repo._store[priv.id] = priv

    alice = ActorContext(user_id="alice")
    items = await svc.list(actor=alice, limit=10, offset=0)
    assert {c.code for c in items} == {"pub"}


@pytest.mark.asyncio
async def test_mcp_config_service_list_public_returns_all_public() -> None:
    repo = MemoryMcpConfigRepository()
    audit = AuditLogService(MemoryAuditLogRepository())
    svc = McpConfigService(repo, audit)

    a = McpConfig(
        id=uuid.uuid4(), code="a", name="A",
        owner_user_id="alice", visibility="public", status="enabled",
        mcp_type="http", url="http://a",
    )
    b = McpConfig(
        id=uuid.uuid4(), code="b", name="B",
        owner_user_id="bob", visibility="public", status="enabled",
        mcp_type="http", url="http://b",
    )
    c = McpConfig(
        id=uuid.uuid4(), code="c", name="C",
        owner_user_id="alice", visibility="private", status="enabled",
        mcp_type="http", url="http://c",
    )
    repo._store[a.id] = a
    repo._store[b.id] = b
    repo._store[c.id] = c

    items = await svc.list_public(limit=10, offset=0)
    assert {c.code for c in items} == {"a", "b"}


@pytest.mark.asyncio
async def test_mcp_config_service_set_visibility_owner_only() -> None:
    repo = MemoryMcpConfigRepository()
    audit = AuditLogService(MemoryAuditLogRepository())
    svc = McpConfigService(repo, audit)
    a, b = ActorContext(user_id="alice"), ActorContext(user_id="bob")
    c = McpConfig(
        id=uuid.uuid4(), code="x", name="X", owner_user_id="alice",
        visibility="private", status="enabled",
        mcp_type="http", url="http://x",
    )
    repo._store[c.id] = c
    assert (await svc.set_visibility(str(c.id), "public", actor=b)) is None
    assert (await svc.set_visibility(str(c.id), "public", actor=a)).visibility == "public"
