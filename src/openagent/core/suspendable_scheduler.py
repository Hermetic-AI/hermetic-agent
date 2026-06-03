"""core/suspendable_scheduler.py — HITL 调度器 (L3).

设计文档 §3 / §8.1 / §12.3. 拦截 AI 调 ``ask_user``, 推送 Card,
写 Checkpoint, 等 ``resume()`` 时按 ``correlation_id`` 续跑.

P5 简化: ``run_turn`` 不调 provider, 直接构造 ask_user tool_use 测
协议 + Checkpoint 链路; 生产版 (P6+) 替换 provider 事件流.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from openagent.auip.cards import CARD_TYPES_SET, Card
from openagent.auip.errors import TurnNotFound
from openagent.auip.events import TurnEvent, TurnEventType
from openagent.core.turn_store import (
    TURN_STATUS_DONE,
    TURN_STATUS_SUSPENDED,
    Checkpoint,
    InMemoryTurnStore,
    TurnStore,
)
from openagent.skill_runtime.manifest import SkillManifest
from openagent.skill_runtime.state_guard import StateGuard

# ask_user 工具 schema (暴露给 provider, 让 LLM 知道有哪些 card_type 可选)
ASK_USER_TOOL: dict[str, Any] = {
    "name": "ask_user",
    "description": (
        "Pause the current turn and ask the user for structured input via a UI card."
    ),
    "input_schema": {
        "type": "object",
        "required": ["card_type"],
        "properties": {
            "card_type": {
                "type": "string",
                "enum": sorted(CARD_TYPES_SET),
                "description": "Which kind of UI card to show the user",
            },
            "title": {"type": "string"},
            "body": {"type": "object"},
            "options": {"type": "array"},
            "decision_buttons": {"type": "array"},
            "actions": {"type": "array"},
        },
    },
}


# Data models + Scheduler


@dataclass
class SuspendPoint:
    """Suspend 时的状态描述 (供前端 / 调试使用).

    ``correlation_id`` 与 ask_user 的 tool_use_id 对应, 用于把用户答复
    路由回正确的 ask_user 调用.
    """

    turn_id: str
    checkpoint_id: str
    state: str
    card: Card
    correlation_id: str
    timeout_at: float | None = None


@dataclass
class UserInput:
    """用户对一张卡片的答复 (P5 简化: 不带文件 / 多模态)."""

    correlation_id: str
    action_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


class SuspendableScheduler:
    """HITL 调度器: 拦截 ask_user, 推送 Card, 写 Checkpoint, suspend.

    与 LegacyScheduler 共存: 不修改 ``core/scheduler.py`` (P5 仅测试,
    路由在 P6 接入).
    """

    def __init__(
        self,
        turn_store: TurnStore | None = None,
        manifest: SkillManifest | None = None,
    ) -> None:
        """初始化.

        Args:
            turn_store: 缺省 ``InMemoryTurnStore``.
            manifest: 缺省 ``SkillManifest.empty()`` (非 ask_user 工具均拒).
        """
        self._turn_store: TurnStore = turn_store or InMemoryTurnStore()
        self._manifest = manifest or SkillManifest.empty()
        # turn_id -> {tool_use_id, card, state}; 仅保留"已 suspend 未 resume"
        self._open_ask_user: dict[str, dict[str, Any]] = {}

    @property
    def turn_store(self) -> TurnStore:
        return self._turn_store

    @property
    def manifest(self) -> SkillManifest:
        return self._manifest

    # ----- run_turn ----------------------------------------------------------

    async def run_turn(
        self,
        turn_id: str,
        session_id: str,
        prompt: str,
        skill_ctx: dict[str, Any] | None = None,
    ) -> AsyncIterator[TurnEvent]:
        """驱动一个 turn: 模拟事件流, 在 ask_user 时挂起.

        P5 测试模式: 不调 provider, 直接构造一个 ask_user tool_use.
        生产版本 (P6+) 会替换 provider 事件流.
        """
        ctx = dict(skill_ctx or {})
        current_state = ctx.get("current_state") or self._manifest.initial_state
        # ⭐ seq 从已有事件续号, 同一 turn 多次 run/resume 严格单调递增
        seq = await self._next_seq(turn_id)

        # 1. SESSION
        yield await self._emit(turn_id, seq, TurnEventType.SESSION, {"session_id": session_id})
        seq += 1
        # 2. STATE
        yield await self._emit(turn_id, seq, TurnEventType.STATE, {"state": current_state})
        seq += 1
        # 3. TEXT (开场白)
        yield await self._emit(turn_id, seq, TurnEventType.TEXT, {"text": prompt})
        seq += 1

        # 4. StateGuard 校验 ask_user
        guard = StateGuard(self._manifest, current_state)
        ok, reason = guard.can_call_tool("ask_user")
        if not ok:
            err = await self._emit(turn_id, seq, TurnEventType.ERROR, {
                "code": "STATE_VIOLATION", "message": reason,
            })
            yield err
            await self._turn_store.update_turn_status(turn_id, "error", current_state)
            return

        # 5. 构造 ask_user tool_use
        tool_use_id = str(uuid.uuid4())
        card_input = self._build_default_card_input(prompt)
        tu = await self._emit(turn_id, seq, TurnEventType.TOOL_USE, {
            "id": tool_use_id, "name": "ask_user", "input": card_input,
        })
        yield tu
        seq += 1

        # 6. 构造 Card
        card = Card.from_dict({
            "card_id": str(uuid.uuid4()),
            "schema_version": "1.0",
            **card_input,
        })

        # 7. emit CARD
        yield await self._emit(turn_id, seq, TurnEventType.CARD, {
            "card_id": card.card_id,
            "card": card.to_dict(),
            "correlation_id": tool_use_id,
        })
        seq += 1

        # 8. 准备 Checkpoint (先构造, 在 SUSPEND 之后写, 这样
        #    last_event_seq 是 SUSPEND 事件的 seq)
        checkpoint = Checkpoint(
            checkpoint_id=str(uuid.uuid4()),
            turn_id=turn_id,
            state=current_state,
            skill_ctx=ctx,
            open_tool_calls=[{
                "id": tool_use_id, "name": "ask_user", "input": card_input,
            }],
            messages_snapshot=[{"role": "user", "content": prompt}],
            last_event_seq=seq,  # SUSPEND 即将占用的 seq
            created_at=time.time(),
        )

                # 9. 记录待恢复 + 标 suspended (BEFORE yield SUSPEND, 让消费者 break 后立刻 resume 也能找到)
        self._open_ask_user[turn_id] = {
            "tool_use_id": tool_use_id,
            "card": card,
            "state": current_state,
        }
        await self._turn_store.update_turn_status(
            turn_id, TURN_STATUS_SUSPENDED, current_state,
        )

        # 10. emit SUSPEND (含 checkpoint_id, 让前端可关联)
        yield await self._emit(turn_id, seq, TurnEventType.SUSPEND, {
            "checkpoint_id": checkpoint.checkpoint_id,
            "card": card.to_dict(),
            "input_schema": ASK_USER_TOOL["input_schema"],
            "correlation_id": tool_use_id,
        })
        seq += 1

        # 11. 持久化 Checkpoint (放在最后, 让 last_event_seq = SUSPEND.seq)
        await self._turn_store.save_checkpoint(checkpoint)

    # ----- resume ------------------------------------------------------------

    async def resume(
        self,
        turn_id: str,
        user_input: UserInput,
    ) -> AsyncIterator[TurnEvent]:
        """从最近 suspend 恢复: emit RESUME → TOOL_RESULT → STATE → DONE."""
        if turn_id not in self._open_ask_user:
            raise TurnNotFound(
                f"Turn {turn_id!r} has no pending suspend",
                action="Check turn_id or start a new turn.",
            )
        open_au = self._open_ask_user.pop(turn_id)
        seq = await self._next_seq(turn_id)

        # 1. RESUME
        checkpoint = await self._turn_store.get_latest_checkpoint(turn_id)
        yield await self._emit(turn_id, seq, TurnEventType.RESUME, {
            "checkpoint_id": checkpoint.checkpoint_id if checkpoint else None,
            "state": open_au["state"],
        })
        seq += 1

        # 2. TOOL_RESULT (模拟 ask_user 工具被回填)
        yield await self._emit(turn_id, seq, TurnEventType.TOOL_RESULT, {
            "id": open_au["tool_use_id"],
            "output": {
                "user_input": user_input.data,
                "action_id": user_input.action_id,
            },
        })
        seq += 1

        # 3. STATE 转移
        yield await self._emit(turn_id, seq, TurnEventType.STATE, {
            "state": open_au["state"], "transition": "resume",
        })
        seq += 1

        # 4. DONE
        yield await self._emit(turn_id, seq, TurnEventType.DONE, {
            "stop_reason": "end_turn",
        })
        await self._turn_store.update_turn_status(turn_id, TURN_STATUS_DONE)

    # ----- helpers -----------------------------------------------------------

    async def _next_seq(self, turn_id: str) -> int:
        """下一个 seq = max(existing seqs) + 1, 无事件则从 0 起."""
        events = await self._turn_store.get_events(turn_id)
        if not events:
            return 0
        return max(e.seq for e in events) + 1

    async def _emit(
        self,
        turn_id: str,
        seq: int,
        type_: TurnEventType,
        data: dict[str, Any],
    ) -> TurnEvent:
        """构造事件 → 持久化 → 返回 (caller 自行 yield)."""
        evt = TurnEvent(
            seq=seq, turn_id=turn_id, type=type_, data=data, ts=time.time(),
        )
        await self._turn_store.save_event(turn_id, evt)
        return evt

    def _build_default_card_input(self, prompt: str) -> dict[str, Any]:
        """P5 测试模式默认 ask_user 参数 (OD_INPUT 卡片)."""
        return {
            "card_type": "OD_INPUT",
            "title": "请告诉我出发地 / 目的地",
            "body": {
                "message": "为了查询航班, 我需要知道城市和日期",
                "prompt": prompt,
            },
        }


__all__ = [
    "ASK_USER_TOOL",
    "SuspendPoint",
    "SuspendableScheduler",
    "UserInput",
]
