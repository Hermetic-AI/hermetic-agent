"""tests/test_question_sdk.py — P7: question SDK 包装 (mock httpx)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from openagent.providers.opencode import native_sdk as sdk

# ---------------------------------------------------------------------------
# question_list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_question_list_returns_list() -> None:
    """``question_list`` 把 ``/question`` 的 list 响应原样返回."""
    client = MagicMock()
    response = MagicMock(spec=httpx.Response)
    response.content = b'non-empty'
    response.json.return_value = [
        {"id": "q1", "sessionID": "s1", "questions": []},
        {"id": "q2", "sessionID": "s2", "questions": []},
    ]
    client.get = AsyncMock(return_value=response)

    items = await sdk.question_list(client)
    assert len(items) == 2
    assert items[0]["id"] == "q1"
    client.get.assert_awaited_once()
    call = client.get.await_args
    assert call.args[0] == "/question"
    assert call.kwargs["cast_to"] is httpx.Response


@pytest.mark.asyncio
async def test_question_list_empty_response_returns_empty_list() -> None:
    client = MagicMock()
    response = MagicMock(spec=httpx.Response)
    response.content = b""
    client.get = AsyncMock(return_value=response)

    assert await sdk.question_list(client) == []


@pytest.mark.asyncio
async def test_question_list_passes_directory_in_extra_query() -> None:
    client = MagicMock()
    response = MagicMock(spec=httpx.Response)
    response.content = b"[]"
    response.json.return_value = []
    client.get = AsyncMock(return_value=response)

    await sdk.question_list(client, directory="/path/to/project")
    options = client.get.await_args.kwargs["options"]
    assert options["extra_query"] == {"directory": "/path/to/project"}


# ---------------------------------------------------------------------------
# question_reply
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_question_reply_returns_true_on_200() -> None:
    client = MagicMock()
    response = MagicMock(spec=httpx.Response)
    response.status_code = 200
    client.post = AsyncMock(return_value=response)

    ok = await sdk.question_reply(
        client, "que_1", [["单程"], ["经济舱"]],
        directory="/p",
    )
    assert ok is True
    call = client.post.await_args
    assert call.args[0] == "/question/que_1/reply"
    assert call.kwargs["body"] == {"answers": [["单程"], ["经济舱"]]}
    assert call.kwargs["options"]["extra_query"] == {"directory": "/p"}


@pytest.mark.asyncio
async def test_question_reply_returns_false_on_404() -> None:
    client = MagicMock()
    response = MagicMock(spec=httpx.Response)
    response.status_code = 404
    client.post = AsyncMock(return_value=response)

    assert await sdk.question_reply(client, "missing", [["x"]]) is False


# ---------------------------------------------------------------------------
# question_reject
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_question_reject_returns_true_on_200() -> None:
    client = MagicMock()
    response = MagicMock(spec=httpx.Response)
    response.status_code = 200
    client.post = AsyncMock(return_value=response)

    assert await sdk.question_reject(client, "que_1", directory="/p") is True
    call = client.post.await_args
    assert call.args[0] == "/question/que_1/reject"
    assert call.kwargs["body"] == {}


# ---------------------------------------------------------------------------
# todo_list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_todo_list_returns_list() -> None:
    client = MagicMock()
    response = MagicMock(spec=httpx.Response)
    response.content = b"non-empty"
    response.json.return_value = [
        {"content": "T1", "status": "in_progress", "priority": "high"},
        {"content": "T2", "status": "pending", "priority": "low"},
    ]
    client.get = AsyncMock(return_value=response)

    items = await sdk.todo_list(client, "ses_1", directory="/p")
    assert len(items) == 2
    assert items[0]["status"] == "in_progress"
    call = client.get.await_args
    assert call.args[0] == "/session/ses_1/todo"
    assert call.kwargs["options"]["extra_query"] == {"directory": "/p"}


@pytest.mark.asyncio
async def test_todo_list_empty_response() -> None:
    client = MagicMock()
    response = MagicMock(spec=httpx.Response)
    response.content = b""
    client.get = AsyncMock(return_value=response)
    assert await sdk.todo_list(client, "ses_1") == []


# ---------------------------------------------------------------------------
# _options helper
# ---------------------------------------------------------------------------


def test_options_helper_omits_unset_fields() -> None:
    out = sdk._options()
    assert out == {}


def test_options_helper_includes_directory() -> None:
    out = sdk._options(directory="/p")
    assert out["extra_query"] == {"directory": "/p"}


def test_options_helper_includes_timeout() -> None:
    out = sdk._options(timeout=3.5)
    assert out["timeout"] == 3.5


def test_options_helper_combines() -> None:
    out = sdk._options(directory="/p", timeout=10.0)
    assert out == {"extra_query": {"directory": "/p"}, "timeout": 10.0}
