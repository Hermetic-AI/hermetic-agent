"""Unit tests for ``OpenCodeEventHub``.

These tests use a fake ``AsyncStream`` to avoid needing a real opencode
server.  They verify the hub's lifecycle, fanout, and concurrency
behaviors.
"""
from __future__ import annotations

import asyncio
import contextlib
from typing import Any, AsyncIterator

import pytest

from openagent.providers.opencode.event_hub import OpenCodeEventHub


class _FakeStream:
    """Minimal AsyncStream stand-in: yields events from an asyncio.Queue."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[Any] = asyncio.Queue()
        self._closed = False

    def __aiter__(self) -> AsyncIterator[Any]:
        return self._iter_impl()

    async def _iter_impl(self) -> AsyncIterator[Any]:
        while not self._closed:
            event = await self._queue.get()
            if event is _STOP:
                return
            yield event

    async def push(self, event: Any) -> None:
        await self._queue.put(event)

    async def close(self) -> None:
        self._closed = True
        await self._queue.put(_STOP)


_STOP = object()


def _make_client(stream: _FakeStream) -> Any:
    """Build a fake AsyncOpencode client that returns ``stream`` for event.list()."""

    class _FakeEventResource:
        async def list(self) -> _FakeStream:
            return stream

    class _FakeClient:
        event = _FakeEventResource()

    return _FakeClient()


@pytest.mark.asyncio
async def test_hub_opens_stream_on_first_subscribe() -> None:
    """First subscribe() for a key must call client.event.list()."""
    stream = _FakeStream()
    client = _make_client(stream)
    hub = OpenCodeEventHub()

    received: list[Any] = []
    sub_task = asyncio.create_task(_drain(hub, client, "agent1", "http://x", "s1", received))

    # Give the hub a tick to open + subscribe.
    await asyncio.sleep(0.01)
    assert "agent1:http://x" in hub._states  # type: ignore[attr-defined]

    # Push a fake event and confirm it reaches the subscriber.
    await stream.push({"type": "message.updated", "data": "hi"})
    await asyncio.sleep(0.01)
    assert received == [{"type": "message.updated", "data": "hi"}]

    # Close everything.
    sub_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await sub_task
    await _wait_idle(hub)


@pytest.mark.asyncio
async def test_hub_reuses_stream_for_same_key() -> None:
    """Two concurrent subscribes to the same (agent, base_url) must share one stream."""
    stream = _FakeStream()
    open_count = 0

    class _CountingEventResource:
        async def list(self) -> _FakeStream:
            nonlocal open_count
            open_count += 1
            return stream

    class _CountingClient:
        event = _CountingEventResource()

    client = _CountingClient()
    hub = OpenCodeEventHub()

    rec_a: list[Any] = []
    rec_b: list[Any] = []
    ta = asyncio.create_task(_drain(hub, client, "a", "http://x", "sa", rec_a))
    tb = asyncio.create_task(_drain(hub, client, "a", "http://x", "sb", rec_b))
    await asyncio.sleep(0.02)
    assert open_count == 1, "should have opened the stream exactly once"
    assert len(hub._states["a:http://x"].subscribers) == 2  # type: ignore[attr-defined]

    await stream.push("evt")
    await asyncio.sleep(0.01)
    # Both subscribers see the same event (they filter on session_id in their consumer).
    assert rec_a == ["evt"]
    assert rec_b == ["evt"]

    for t in (ta, tb):
        t.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await t
    await _wait_idle(hub)


@pytest.mark.asyncio
async def test_hub_closes_stream_when_last_subscriber_leaves() -> None:
    """After the last subscriber exits, the underlying stream should be closed."""
    stream = _FakeStream()
    client = _make_client(stream)
    hub = OpenCodeEventHub()

    rec: list[Any] = []
    t = asyncio.create_task(_drain(hub, client, "a", "http://x", "s", rec))
    await asyncio.sleep(0.01)
    t.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await t

    await _wait_idle(hub)
    assert "a:http://x" not in hub._states  # type: ignore[attr-defined]
    assert stream._closed is True


@pytest.mark.asyncio
async def test_hub_drops_event_on_full_subscriber_queue() -> None:
    """A slow subscriber should not block the fanout."""
    stream = _FakeStream()
    client = _make_client(stream)
    hub = OpenCodeEventHub()

    # Subscriber that never reads; queue will fill to maxsize=512.
    rec: list[Any] = []

    async def _slow_drain() -> None:
        async for _ in hub.subscribe(
            agent_name="a", base_url="http://x", client=client, session_id="s",
        ):
            pass  # intentionally never reaches here

    t = asyncio.create_task(_slow_drain())
    await asyncio.sleep(0.01)

    # Push 600 events.  Queue caps at 512; the rest are dropped with a warning.
    for i in range(600):
        await stream.push(i)
    # The fanout task is alive despite the dropped events.
    state = hub._states["a:http://x"]  # type: ignore[attr-defined]
    assert state.fanout_task.done() is False

    t.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await t
    await _wait_idle(hub)


async def _drain(
    hub: OpenCodeEventHub,
    client: Any,
    agent: str,
    base_url: str,
    session_id: str,
    out: list[Any],
) -> None:
    async for event in hub.subscribe(
        agent_name=agent, base_url=base_url, client=client, session_id=session_id,
    ):
        out.append(event)


async def _wait_idle(hub: OpenCodeEventHub) -> None:
    """Wait until the hub has no active streams."""
    for _ in range(50):
        if not hub._states:  # type: ignore[attr-defined]
            return
        await asyncio.sleep(0.01)
    raise AssertionError("hub did not become idle in time")
