"""End-to-end Service 编排测试: session -> turn -> message -> parts + 聚合自动更新 + 审计."""

from __future__ import annotations

import pytest

from openagent.store import (
    BatchCreatePartRequest,
    CreateChatTurnRequest,
    CreateMessageRequest,
    CreatePartRequest,
    CreateSessionRequest,
)


@pytest.mark.asyncio
async def test_full_chat_turn_lifecycle(service_container):
    """完整流程: 创建 session -> 创建 turn -> 启动 -> 发 user message + parts -> 完成 turn(累加 session 聚合) -> 校验 audit_log."""
    container = service_container

    # 1. 建 session
    sess = await container.session.create(
        CreateSessionRequest(
            user_id="u-1",
            title="lifecycle test",
            model="claude-sonnet-4-5",
            agent_name="default",
        ),
        actor_id="tester",
    )
    assert sess.message_count == 0
    assert sess.cost == 0

    # 2. 建 turn
    turn = await container.chat_turn.create(
        CreateChatTurnRequest(session_id=sess.id, agent_name="default", model="claude-sonnet-4-5"),
        actor_id="tester",
    )
    assert turn.status == "pending"
    assert turn.started_at is None

    # 3. 启动 turn
    started = await container.chat_turn.start(turn.id)
    assert started.status == "running"
    assert started.started_at is not None

    # 4. 发 user message + parts
    user_msg = await container.message.create(
        CreateMessageRequest(
            session_id=sess.id,
            turn_id=turn.id,
            role="user",
            content="帮我订一张北京到上海的机票",
        ),
        actor_id="tester",
    )
    # 单独再批量发 2 个 part
    await container.part.batch_create(
        BatchCreatePartRequest(
            message_id=user_msg.id,
            session_id=sess.id,
            parts=[
                CreatePartRequest(
                    message_id=user_msg.id,
                    session_id=sess.id,
                    part_type="text",
                    content="帮我订一张北京到上海的机票",
                    position=0,
                ),
                CreatePartRequest(
                    message_id=user_msg.id,
                    session_id=sess.id,
                    part_type="tool_call",
                    content='{"name":"query_flight"}',
                    position=1,
                    metadata={"tool_id": "tc-1"},
                ),
            ],
        ),
        actor_id="tester",
    )

    # 5. 发 assistant message
    await container.message.create(
        CreateMessageRequest(
            session_id=sess.id,
            turn_id=turn.id,
            role="assistant",
            content="好的,正在查询...",
        ),
        actor_id="tester",
    )

    # 6. 完成 turn(累加聚合)
    await container.chat_turn.complete(
        turn.id,
        cost=0.003,
        tokens_input=150,
        tokens_output=80,
        tokens_reasoning=20,
        tokens_cache_read=100,
    )

    # 7. 校验: session 聚合已更新
    sess_after = await container.session.get_by_id(sess.id)
    assert sess_after.message_count == 2  # user + assistant
    assert sess_after.tokens_input == 150
    assert sess_after.tokens_output == 80
    assert sess_after.tokens_reasoning == 20
    assert float(sess_after.cost) == 0.003

    # 8. 校验: turn 已完成
    turn_after = await container.chat_turn.get_by_id(turn.id)
    assert turn_after.status == "success"
    assert turn_after.finished_at is not None
    assert turn_after.duration_ms is not None
    assert turn_after.duration_ms >= 0

    # 9. 校验: 消息可按 session 拉 + parts 一起拉
    msgs = await container.message.list_by_session_with_parts(sess.id)
    assert len(msgs) == 2
    user_m, user_parts = msgs[0]
    asst_m, asst_parts = msgs[1]
    assert user_m.role == "user"
    assert len(user_parts) == 2
    assert user_parts[0].part_type == "text"
    assert user_parts[1].part_type == "tool_call"
    assert asst_m.role == "assistant"
    assert len(asst_parts) == 0  # assistant 消息没发 parts

    # 10. 校验: audit_log 写了多条 (create session / create turn / create msg*2 / batch parts / state_change)
    sess_audits = await container.audit_log.list_by_resource("session", sess.id)
    assert any(a.action == "create" for a in sess_audits)

    turn_audits = await container.audit_log.list_by_resource("turn", turn.id)
    actions = [a.action for a in turn_audits]
    assert "create" in actions
    assert "state_change" in actions


@pytest.mark.asyncio
async def test_chat_turn_fail_records_error(service_container):
    """turn 失败时: status=failed + error_code/message 写入."""
    container = service_container

    sess = await container.session.create(
        CreateSessionRequest(user_id="u-2", title="fail-test", agent_name="default")
    )
    turn = await container.chat_turn.create(
        CreateChatTurnRequest(session_id=sess.id)
    )
    await container.chat_turn.start(turn.id)
    failed = await container.chat_turn.fail(
        turn.id, error_code="llm_timeout", error_message="request timeout after 30s"
    )
    assert failed.status == "failed"
    assert failed.error_code == "llm_timeout"
    assert "timeout" in (failed.error_message or "")
    assert failed.duration_ms is not None


@pytest.mark.asyncio
async def test_session_close_status_transition(service_container):
    """session.close 把状态置 closed, 写 audit."""
    container = service_container
    sess = await container.session.create(
        CreateSessionRequest(user_id="u-3", title="close-test", agent_name="default")
    )
    closed = await container.session.close(sess.id, actor_id="tester")
    assert closed.status == "closed"
    audits = await container.audit_log.list_by_resource("session", sess.id)
    update_audits = [a for a in audits if a.action == "update"]
    assert any("status" in (a.after_data or {}) for a in update_audits)
