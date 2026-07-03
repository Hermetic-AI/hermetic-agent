"""tests/test_opencode_event_mapping.py — P7: opencode 原生 event 映射.

覆盖 ``hermetic_agent.streaming.map_opencode_event`` 的 4 个新分支:
- ``question.asked``  -> StreamEvent.question_asked
- ``question.replied`` -> StreamEvent.question_replied
- ``question.rejected`` -> StreamEvent.question_rejected
- ``todo.updated`` -> StreamEvent.todo_updated
"""
from __future__ import annotations

from types import SimpleNamespace

from hermetic_agent.providers.streaming import OPENCODE_STREAM_END, StreamEvent, map_opencode_event


def _pydantic_like_event(etype: str, props):
    """造一个 SDK 风格的 EventListResponse — type + properties (Pydantic-like)."""
    return SimpleNamespace(type=etype, properties=props)


class _Mini:
    """Mock 一个 Pydantic v2 风格的 model, 有 ``model_dump()``."""

    def __init__(self, **kw):
        self.__dict__.update(kw)

    def model_dump(self):
        return dict(self.__dict__)


SESSION = "ses_test_1"


# ---------------------------------------------------------------------------
# question.asked
# ---------------------------------------------------------------------------


def test_question_asked_maps_to_stream_event() -> None:
    """``question.asked`` 带 questions[] 转 ``question_asked`` event."""
    q1 = _Mini(
        question="北京→上海 出行, 是否需要回程?",
        header="行程",
        options=[
            _Mini(label="单程", description="只订去程"),
            _Mini(label="往返", description="需要回程"),
        ],
        multiple=False,
        custom=True,
    )
    q2 = _Mini(
        question="舱等偏好?",
        header="舱等",
        options=[
            _Mini(label="经济舱", description="价格最低"),
            _Mini(label="公务舱", description="可平躺"),
        ],
        multiple=False,
        custom=False,
    )
    props = _Mini(
        id="que_test_1",
        sessionID=SESSION,
        questions=[q1, q2],
    )
    event = _pydantic_like_event("question.asked", props)

    out = map_opencode_event(event, SESSION, set())
    assert isinstance(out, StreamEvent)
    assert out.type == "question_asked"
    assert out.data["request_id"] == "que_test_1"
    assert out.data["session_id"] == SESSION
    assert len(out.data["questions"]) == 2
    assert out.data["questions"][0]["question"] == "北京→上海 出行, 是否需要回程?"
    assert out.data["questions"][0]["options"][0]["label"] == "单程"
    assert out.data["questions"][1]["header"] == "舱等"


def test_question_asked_filters_by_session_id() -> None:
    """``question.asked`` 来自其它 session 时被忽略."""
    props = _Mini(id="q1", sessionID="other_session", questions=[])
    event = _pydantic_like_event("question.asked", props)
    out = map_opencode_event(event, SESSION, set())
    assert out is None


def test_question_asked_with_dict_questions() -> None:
    """``question.asked`` 兼容 dict 格式 (SDK 旧版本或 mock)."""
    props = {
        "id": "q2",
        "sessionID": SESSION,
        "questions": [
            {
                "question": "Q?",
                "header": "h",
                "options": [{"label": "A", "description": "d"}],
            }
        ],
    }
    event = SimpleNamespace(type="question.asked", properties=props)
    out = map_opencode_event(event, SESSION, set())
    assert isinstance(out, StreamEvent)
    assert out.type == "question_asked"
    assert out.data["questions"][0]["options"][0]["label"] == "A"


# ---------------------------------------------------------------------------
# question.replied
# ---------------------------------------------------------------------------


def test_question_replied_maps_to_stream_event() -> None:
    """``question.replied`` 带 answers 转 ``question_replied`` event."""
    props = _Mini(
        sessionID=SESSION,
        requestID="que_test_1",
        answers=[["单程"], ["经济舱"]],
    )
    event = _pydantic_like_event("question.replied", props)
    out = map_opencode_event(event, SESSION, set())
    assert isinstance(out, StreamEvent)
    assert out.type == "question_replied"
    assert out.data["request_id"] == "que_test_1"
    assert out.data["answers"] == [["单程"], ["经济舱"]]


def test_question_replied_filters_by_session_id() -> None:
    props = _Mini(sessionID="other", requestID="x", answers=[["a"]])
    event = _pydantic_like_event("question.replied", props)
    assert map_opencode_event(event, SESSION, set()) is None


# ---------------------------------------------------------------------------
# question.rejected
# ---------------------------------------------------------------------------


def test_question_rejected_maps_to_stream_event() -> None:
    props = _Mini(sessionID=SESSION, requestID="que_test_1")
    event = _pydantic_like_event("question.rejected", props)
    out = map_opencode_event(event, SESSION, set())
    assert isinstance(out, StreamEvent)
    assert out.type == "question_rejected"
    assert out.data["request_id"] == "que_test_1"
    assert out.data["session_id"] == SESSION


def test_question_rejected_filters_by_session_id() -> None:
    props = _Mini(sessionID="other", requestID="x")
    event = _pydantic_like_event("question.rejected", props)
    assert map_opencode_event(event, SESSION, set()) is None


# ---------------------------------------------------------------------------
# todo.updated
# ---------------------------------------------------------------------------


def test_todo_updated_maps_to_stream_event() -> None:
    todos = [
        _Mini(content="解析用户需求", status="in_progress", priority="high"),
        _Mini(content="查询航班", status="pending", priority="high"),
        _Mini(content="整理 3 个方案", status="pending", priority="medium"),
    ]
    props = _Mini(sessionID=SESSION, todos=todos)
    event = _pydantic_like_event("todo.updated", props)
    out = map_opencode_event(event, SESSION, set())
    assert isinstance(out, StreamEvent)
    assert out.type == "todo_updated"
    assert out.data["session_id"] == SESSION
    assert len(out.data["todos"]) == 3
    assert out.data["todos"][0]["content"] == "解析用户需求"
    assert out.data["todos"][0]["status"] == "in_progress"
    assert out.data["todos"][0]["priority"] == "high"


def test_todo_updated_filters_by_session_id() -> None:
    props = _Mini(sessionID="other", todos=[])
    event = _pydantic_like_event("todo.updated", props)
    assert map_opencode_event(event, SESSION, set()) is None


def test_todo_updated_with_dict_payload() -> None:
    """兼容纯 dict 形式的 todo payload."""
    props = {
        "sessionID": SESSION,
        "todos": [
            {"content": "T1", "status": "pending", "priority": "low"},
        ],
    }
    event = SimpleNamespace(type="todo.updated", properties=props)
    out = map_opencode_event(event, SESSION, set())
    assert isinstance(out, StreamEvent)
    assert out.data["todos"][0]["priority"] == "low"


# ---------------------------------------------------------------------------
# 兜底: 其它未知事件返回 None, 不抛错
# ---------------------------------------------------------------------------


def test_unknown_event_type_returns_none() -> None:
    event = _pydantic_like_event("file.edited", _Mini())
    assert map_opencode_event(event, SESSION, set()) is None


def test_session_idle_returns_stream_end_sentinel() -> None:
    """保留: ``session.idle`` 仍返 OPENCODE_STREAM_END 哨兵."""
    event = _pydantic_like_event("session.idle", _Mini(session_id=SESSION))
    assert map_opencode_event(event, SESSION, set()) is OPENCODE_STREAM_END


# ---------------------------------------------------------------------------
# 工厂方法存在性
# ---------------------------------------------------------------------------


def test_stream_event_factories_exist() -> None:
    """P7 4 个工厂方法存在且签名正确."""
    qa = StreamEvent.question_asked(
        request_id="r1", session_id="s1",
        questions=[{"question": "q", "header": "h", "options": []}],
    )
    assert qa.type == "question_asked"
    assert qa.data["request_id"] == "r1"
    assert qa.data["session_id"] == "s1"

    qr = StreamEvent.question_replied(
        session_id="s1", request_id="r1", answers=[["a"]],
    )
    assert qr.type == "question_replied"
    assert qr.data["answers"] == [["a"]]

    qj = StreamEvent.question_rejected(session_id="s1", request_id="r1")
    assert qj.type == "question_rejected"

    tu = StreamEvent.todo_updated(
        session_id="s1",
        todos=[{"content": "x", "status": "pending", "priority": "high"}],
    )
    assert tu.type == "todo_updated"
    assert tu.data["todos"][0]["priority"] == "high"
