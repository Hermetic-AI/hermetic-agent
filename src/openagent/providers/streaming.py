"""流式事件与 SSE 序列化工具。

为 OpenCode SDK 和 Claude Code SDK 提供统一的事件模型
``StreamEvent``，以及到 Server-Sent Events 字符串的转换辅助。
"""
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

# Sentinel returned by map_opencode_event to signal stream termination.
OPENCODE_STREAM_END = "__opencode_stream_end__"


# ---------------------------------------------------------------------------
# Internal helpers (private)
# ---------------------------------------------------------------------------


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """兼容 dict 和 Pydantic-like 对象的属性读取.

    opencode-ai SDK 的事件 ``properties`` 可能是 Pydantic 模型或纯 dict
    (取决于 SDK 版本或 mock). 这里统一处理, 避免 ``AttributeError``.
    """
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _json_default(obj: Any) -> Any:
    """``json.dumps(..., default=...)`` 的兜底序列化器.

    集中处理 ``StreamEvent.data`` 里可能出现的非 JSON 原生类型.
    历史: ``dataclasses.asdict`` 会递归 dataclass 但碰到 datetime 会爆.
    现在显式处理常见类型, 未识别的转 repr 让排错友好.

    注意: 此函数必须在 ``StreamEvent`` 类**之前**定义 (避免 Python 把
    任何顶层 def 当成"类结束"的隐式终止). 这是修复 P0 #streaming 时的
    关键排版.
    """
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, (set, frozenset)):
        return sorted(obj)  # type: ignore[arg-type]
    if isinstance(obj, bytes):
        try:
            return obj.decode("utf-8")
        except UnicodeDecodeError:
            return obj.hex()
    # 兜底: 让 json 报 "TypeError: Object of type X is not JSON serializable"
    # 而非静默漏字段
    raise TypeError(
        f"Object of type {type(obj).__name__!r} is not JSON serializable; "
        f"register a custom serializer in streaming._json_default if needed."
    )


def _to_dict(obj: Any) -> dict:
    """把 Pydantic-like / dict 对象递归转成 dict, 嵌套 list/dict/model 都会扁平化.

    兼容 3 种输入:
    - ``None``              -> ``{}``
    - ``dict``              -> 递归 (嵌套值也转 dict)
    - Pydantic v2 / 自定义 -> 调 ``.model_dump()`` 然后递归
    - 其它                 -> 尽力 ``vars()`` 转 dict

    不递归纯字符串/数字/布尔 — 这些原样返回.
    """
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return {k: _normalize(v) for k, v in obj.items()}
    if hasattr(obj, "model_dump"):
        d = obj.model_dump()
        return {k: _normalize(v) for k, v in d.items()}
    if hasattr(obj, "__dict__"):
        d = {k: v for k, v in vars(obj).items() if not k.startswith("_")}
        return {k: _normalize(v) for k, v in d.items()}
    return {}


def _normalize(v: Any) -> Any:
    """递归展开嵌套结构 (dict / list / 模型对象), 标量原样返回."""
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, dict):
        return _to_dict(v)
    if isinstance(v, (list, tuple)):
        return [_normalize(x) for x in v]
    if hasattr(v, "model_dump"):
        return _to_dict(v)
    if hasattr(v, "__dict__") and not isinstance(v, type):
        return _to_dict(v)
    return v


StreamEventType = Literal[
    "scenario", "session", "text", "reasoning", "tool_use", "tool_result",
    "card", "state", "suspend", "resume", "done", "error",
    # P7: opencode 原生 question / todo 事件 (透传, 前端按 opencode UI 渲染)
    "question_asked", "question_replied", "question_rejected", "todo_updated",
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
        """序列化为 ``data: <json>\\n\\n`` 形式的 SSE 字符串。

        使用 ``ensure_ascii=False`` 让中文等内容直接以 UTF-8 字符出现在 SSE 流里，
        而不是 ``\\u67e5\\u8be2...`` 这种 escape 序列 —— 否则终端和日志都读不懂。

        P0 重构: 不再 ``dataclasses.asdict()``, 改用 ``json.dumps(..., default=...)``
        + 自定义序列化器, 避免 ``asdict`` 在以下场景的陷阱:
        - 嵌套 dataclass 行为不一致
        - ``datetime`` / ``UUID`` / ``Path`` 等非 JSON 原生类型直接抛 TypeError
        - ``field(metadata=...)`` 元数据被错误地序列化为 body 字段
        """
        payload = {"type": self.type, "data": self.data}
        return f"data: {json.dumps(payload, ensure_ascii=False, default=_json_default)}\n\n"

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

    @classmethod
    def question_asked(
        cls,
        request_id: str,
        session_id: str,
        questions: list[dict],
        **kwargs,
    ) -> "StreamEvent":
        """构造 ``question.asked`` 透传事件.

        来自 opencode ``EventQuestionAsked``: LLM 调 question 工具时触发,
        携带待回答问题列表(每项含 question/header/options/multiple/custom).
        前端用 QuestionCard 渲染 (仿 opencode UI).
        """
        return cls(
            type="question_asked",
            data={
                "request_id": request_id,
                "session_id": session_id,
                "questions": questions,
                **kwargs,
            },
        )

    @classmethod
    def question_replied(
        cls,
        session_id: str,
        request_id: str,
        answers: list[list[str]],
        **kwargs,
    ) -> "StreamEvent":
        """构造 ``question.replied`` 透传事件 (用户提交答案)."""
        return cls(
            type="question_replied",
            data={
                "session_id": session_id,
                "request_id": request_id,
                "answers": answers,
                **kwargs,
            },
        )

    @classmethod
    def question_rejected(
        cls,
        session_id: str,
        request_id: str,
        **kwargs,
    ) -> "StreamEvent":
        """构造 ``question.rejected`` 透传事件 (用户忽略)."""
        return cls(
            type="question_rejected",
            data={"session_id": session_id, "request_id": request_id, **kwargs},
        )

    @classmethod
    def todo_updated(
        cls,
        session_id: str,
        todos: list[dict],
        **kwargs,
    ) -> "StreamEvent":
        """构造 ``todo.updated`` 透传事件.

        来自 opencode ``EventTodoUpdated``: LLM 调 todowrite 工具时触发,
        携带任务清单 (每项含 content/status/priority). 前端用 TodoListCard
        按 status 分组渲染.
        """
        return cls(
            type="todo_updated",
            data={"session_id": session_id, "todos": todos, **kwargs},
        )


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
        info = _get(props, "info")
        if info is not None:
            role = _get(info, "role")
            msg_session_id = _get(info, "session_id")
            if role == "assistant" and msg_session_id == session_id:
                msg_id = _get(info, "id", "")
                if msg_id:
                    assistant_message_ids.add(msg_id)
        return None

    if etype == "message.part.updated":
        part = _get(props, "part")
        if part is None:
            return None
        if _get(part, "session_id") != session_id:
            return None
        if _get(part, "message_id") not in assistant_message_ids:
            return None
        ptype = _get(part, "type")
        if ptype == "text":
            return StreamEvent.text(content=_get(part, "text", "") or "")
        if ptype == "tool":
            tool_name = _get(part, "tool", "unknown")
            state = _get(part, "state")
            status = _get(state, "status") if state is not None else None
            if status == "running":
                inp = _get(state, "input") if state is not None else None
                return StreamEvent.tool_use(
                    tool_name=tool_name,
                    input_data=inp if isinstance(inp, dict) else {},
                )
            if status == "completed":
                out = _get(state, "output", "") if state is not None else ""
                return StreamEvent.tool_result(
                    tool_name=tool_name,
                    output=out,
                )
        return None

    if etype == "session.idle":
        if _get(props, "session_id") == session_id:
            return OPENCODE_STREAM_END
        return None

    if etype == "session.error":
        if _get(props, "session_id") == session_id:
            err = _get(props, "error")
            err_name = _get(err, "name", "session.error") if err is not None else "session.error"
            return StreamEvent.error(message=str(err_name))
        return None

    # ---- P7: opencode 原生 question / todo 事件透传 ----

    if etype == "question.asked":
        if _get(props, "sessionID") != session_id:
            return None
        questions_raw = _get(props, "questions", []) or []
        questions = [_to_dict(q) for q in questions_raw]
        return StreamEvent.question_asked(
            request_id=str(_get(props, "id", "")),
            session_id=str(_get(props, "sessionID", "")),
            questions=questions,
        )

    if etype == "question.replied":
        if _get(props, "sessionID") != session_id:
            return None
        answers_raw = _get(props, "answers", []) or []
        answers: list[list[str]] = []
        for a in answers_raw:
            if isinstance(a, (list, tuple)):
                answers.append([str(x) for x in a])
            elif isinstance(a, str):
                answers.append([a])
            else:
                answers.append([])
        return StreamEvent.question_replied(
            session_id=str(_get(props, "sessionID", "")),
            request_id=str(_get(props, "requestID", "")),
            answers=answers,
        )

    if etype == "question.rejected":
        if _get(props, "sessionID") != session_id:
            return None
        return StreamEvent.question_rejected(
            session_id=str(_get(props, "sessionID", "")),
            request_id=str(_get(props, "requestID", "")),
        )

    if etype == "todo.updated":
        if _get(props, "sessionID") != session_id:
            return None
        todos_raw = _get(props, "todos", []) or []
        todos = [_to_dict(t) for t in todos_raw]
        return StreamEvent.todo_updated(
            session_id=str(_get(props, "sessionID", "")),
            todos=todos,
        )

    return None

