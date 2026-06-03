"""流式事件与 SSE 序列化工具。

为 OpenCode SDK 和 Claude Code SDK 提供统一的事件模型
``StreamEvent``，以及到 Server-Sent Events 字符串的转换辅助。
"""

from dataclasses import dataclass, field, asdict
from typing import Literal, Any
import json

# Sentinel returned by map_opencode_event to signal stream termination.
OPENCODE_STREAM_END = "__opencode_stream_end__"


StreamEventType = Literal[
    "scenario", "session", "text", "reasoning", "tool_use", "tool_result",
    "card", "state", "suspend", "resume", "done", "error",
]


@dataclass
class StreamEvent:
    """统一的流式事件，是 SDK 适配器对外暴露的事件 API。

    通过工厂方法（``text`` / ``reasoning`` / ``tool_use`` 等）构造，
    序列化后通过 SSE 推送给前端消费者。
    """
    type: StreamEventType
    data: dict = field(default_factory=dict)

    def to_sse(self) -> str:
        """序列化为 ``data: <json>\\n\\n`` 形式的 SSE 字符串。"""
        return f"data: {json.dumps(asdict(self))}\n\n"

    @classmethod
    def scenario(
        cls,
        name: str,
        version: str = "",
        matched_by: str = "default",
        **kwargs,
    ) -> "StreamEvent":
        """Create a scenario event (P6: 路由结果)."""
        return cls(
            type="scenario",
            data={"name": name, "version": version, "matched_by": matched_by, **kwargs},
        )

    @classmethod
    def session(cls, session_id: str, **kwargs) -> "StreamEvent":
        """构造一个表示会话已建立的 ``session`` 事件。

        Args:
            session_id: 会话 ID。
            **kwargs: 附加字段，会合并到 ``data`` 中。
        """
        return cls(type="session", data={"session_id": session_id, **kwargs})

    @classmethod
    def text(cls, content: str, **kwargs) -> "StreamEvent":
        """构造一个模型文本增量事件。"""
        return cls(type="text", data={"content": content, **kwargs})

    @classmethod
    def reasoning(cls, content: str, **kwargs) -> "StreamEvent":
        """构造一个模型推理/思考事件。"""
        return cls(type="reasoning", data={"content": content, **kwargs})

    @classmethod
    def tool_use(cls, tool_name: str, input_data: dict, **kwargs) -> "StreamEvent":
        """构造一个工具调用发起事件。

        Args:
            tool_name: 工具名。
            input_data: 工具入参。
        """
        return cls(type="tool_use", data={"tool_name": tool_name, "input": input_data, **kwargs})

    @classmethod
    def tool_result(cls, tool_name: str, output: Any, **kwargs) -> "StreamEvent":
        """构造一个工具调用结果事件。

        Args:
            tool_name: 工具名。
            output: 工具返回结果。
        """
        return cls(type="tool_result", data={"tool_name": tool_name, "output": output, **kwargs})

    @classmethod
    def done(cls, **kwargs) -> "StreamEvent":
        """构造一个流式结束事件（不携带错误信息）。"""
        return cls(type="done", data=kwargs)

    @classmethod
    def error(cls, message: str, **kwargs) -> "StreamEvent":
        """构造一个错误事件。

        Args:
            message: 人类可读的错误描述。
        """
        return cls(type="error", data={"message": message, **kwargs})

    @classmethod
    def card(
        cls,
        card_id: str,
        card_type: str,
        card: dict,
        correlation_id: str = "",
        **kwargs,
    ) -> "StreamEvent":
        """构造 card 事件 (AUIP / A2UI)."""
        return cls(
            type="card",
            data={
                "card_id": card_id,
                "card_type": card_type,
                "card": card,
                "correlation_id": correlation_id,
                **kwargs,
            },
        )

    @classmethod
    def state(cls, state: str, **kwargs) -> "StreamEvent":
        """构造 state 事件 (业务状态切换)."""
        return cls(type="state", data={"state": state, **kwargs})

    @classmethod
    def suspend(
        cls,
        checkpoint_id: str,
        card: dict,
        correlation_id: str,
        input_schema: dict | None = None,
        timeout_at: float | None = None,
        **kwargs,
    ) -> "StreamEvent":
        """构造 suspend 事件 (HITL 挂起)."""
        return cls(
            type="suspend",
            data={
                "checkpoint_id": checkpoint_id,
                "card": card,
                "correlation_id": correlation_id,
                "input_schema": input_schema or {},
                "timeout_at": timeout_at,
                **kwargs,
            },
        )

    @classmethod
    def resume(cls, checkpoint_id: str = "", **kwargs) -> "StreamEvent":
        """构造 resume 事件 (HITL 恢复)."""
        return cls(type="resume", data={"checkpoint_id": checkpoint_id, **kwargs})


def map_opencode_part(part: dict) -> StreamEvent | None:
    """将 OpenCode part/delta 字典映射为 ``StreamEvent``。

    OpenCode part 的典型形态：
    ``{"type": "text", "text": "hello"}``、``{"type": "tool_use", ...}`` 等。
    未知类型返回 ``None`` 表示忽略。

    Args:
        part: OpenCode 事件载荷字典。

    Returns:
        映射后的 ``StreamEvent``，无法识别时返回 ``None``。
    """
    part_type = part.get("type", "")
    if part_type == "text":
        return StreamEvent.text(content=part.get("text", ""))
    if part_type == "reasoning":
        return StreamEvent.reasoning(content=part.get("text", ""))
    if part_type == "tool_use":
        return StreamEvent.tool_use(
            tool_name=part.get("name", "unknown"),
            input_data=part.get("input", {}),
        )
    if part_type == "tool_result":
        return StreamEvent.tool_result(
            tool_name=part.get("name", "unknown"),
            output=part.get("output", ""),
        )
    if part_type == "session":
        return StreamEvent.session(session_id=part.get("session_id", ""))
    return None


def map_opencode_event(
    event: Any,
    session_id: str,
    assistant_message_ids: set[str],
) -> StreamEvent | Literal["__opencode_stream_end__"] | None:
    """将 opencode-ai SDK 的类型化事件映射为 ``StreamEvent`` 或控制信号。

    opencode-ai SDK 官方通过 ``client.event.list()`` 暴露长连接的
    Server-Sent Events 流，每个事件都是 ``EventListResponse`` 判别联合中的
    Pydantic 模型（``message.updated``、``message.part.updated``、
    ``session.idle``、``session.error`` 等）。

    本函数按 ``session_id`` 过滤事件，并把相关事件转换为内部
    ``StreamEvent`` 形态：

    - ``message.updated``（assistant）-> 维护 ``assistant_message_ids``
      集合，便于后续 part 归属；user 消息会被跳过。
    - ``message.part.updated``（text）-> ``StreamEvent.text``，携带当前
      完整文本；增量检测/去重由调用方负责。
    - ``message.part.updated``（tool, running）-> ``StreamEvent.tool_use``
    - ``message.part.updated``（tool, completed）-> ``StreamEvent.tool_result``
    - ``session.idle``（匹配 session）-> 返回 ``OPENCODE_STREAM_END``
      哨兵，让调用方跳出迭代循环。
    - ``session.error``（匹配 session）-> ``StreamEvent.error`` 后再返回
      ``OPENCODE_STREAM_END``。

    其余事件（``server.connected``、``file.edited``、``lsp.*`` 等）会被
    忽略，消费者继续迭代。

    Args:
        event: ``client.event.list()`` 返回的 Pydantic 事件模型。
        session_id: 仅产生该会话相关的事件。
        assistant_message_ids: 跟踪 assistant 消息 ID 的可变集合，用于过滤
            属于 user 消息的 part。

    Returns:
        - 推送给消费者的 ``StreamEvent`` 实例，或
        - ``OPENCODE_STREAM_END`` 哨兵以终止流，或
        - ``None`` 跳过事件继续迭代。
    """
    etype = getattr(event, "type", None)
    props = getattr(event, "properties", None)

    if etype == "message.updated":
        info = getattr(props, "info", None) if props is not None else None
        if info is not None:
            role = getattr(info, "role", None)
            msg_session_id = getattr(info, "session_id", None)
            if role == "assistant" and msg_session_id == session_id:
                msg_id = getattr(info, "id", "")
                if msg_id:
                    assistant_message_ids.add(msg_id)
        return None

    if etype == "message.part.updated":
        part = getattr(props, "part", None) if props is not None else None
        if part is None:
            return None
        if getattr(part, "session_id", None) != session_id:
            return None
        if getattr(part, "message_id", None) not in assistant_message_ids:
            return None
        ptype = getattr(part, "type", None)
        if ptype == "text":
            return StreamEvent.text(content=getattr(part, "text", "") or "")
        if ptype == "tool":
            tool_name = getattr(part, "tool", "unknown")
            state = getattr(part, "state", None)
            status = getattr(state, "status", None) if state is not None else None
            if status == "running":
                inp = getattr(state, "input", None) if state is not None else None
                return StreamEvent.tool_use(
                    tool_name=tool_name,
                    input_data=inp if isinstance(inp, dict) else {},
                )
            if status == "completed":
                out = getattr(state, "output", "") if state is not None else ""
                return StreamEvent.tool_result(
                    tool_name=tool_name,
                    output=out,
                )
        return None

    if etype == "session.idle":
        if getattr(props, "session_id", None) == session_id:
            return OPENCODE_STREAM_END
        return None

    if etype == "session.error":
        if getattr(props, "session_id", None) == session_id:
            err = getattr(props, "error", None) if props is not None else None
            err_name = getattr(err, "name", "session.error") if err is not None else "session.error"
            return StreamEvent.error(message=str(err_name))
        return None

    return None

