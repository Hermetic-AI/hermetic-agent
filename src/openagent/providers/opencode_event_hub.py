"""OpenCode long-lived event stream hub (TTFT optimization).

For each ``(agent_name, base_url)`` pair, this module keeps ONE persistent
``client.event.list()`` subscription open to the opencode server.  When a
``stream_chat`` call needs to receive events for a session, it subscribes
to the hub and gets its own queue; the hub's single fanout task copies
each event from the open stream into every subscriber queue.

Why:  the opencode-ai SDK's ``client.event.list()`` is a fresh HTTP GET
per call whose handshake costs ~50-200ms.  On a busy agent that means
N handshakes per N chats.  With this hub, the FIRST chat pays the
handshake; every subsequent chat (within the same agent+base_url pair)
piggy-backs on the existing stream.

Fallback:  if the hub's fanout task dies (e.g. opencode server restarts),
the affected ``subscribe()`` block exits with a sentinel and the next
``subscribe()`` re-opens the stream automatically.

Layer:  L4 (provider extension).  Lives next to ``opencode_chat.py`` so
the adapter wiring stays colocated.  File is intentionally < 200 lines
per the project layering rule.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from opencode_ai import AsyncOpencode, AsyncStream

logger = structlog.get_logger(__name__)


# Sentinel pushed to a subscriber's queue to tell its async generator
# to stop iterating.  We do NOT raise — that would surface as an error
# to callers who are just done with their stream.
_SHUTDOWN: object = object()


@dataclass(eq=False)
class _Subscriber:
    """A single stream_chat's view onto the shared event stream."""

    session_id: str
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=512))


@dataclass(eq=False)
class _StreamState:
    """Per-(agent,base_url) state held by the hub."""

    stream: AsyncStream
    fanout_task: asyncio.Task | None
    subscribers: set[_Subscriber] = field(default_factory=set)
    refcount: int = 0


class OpenCodeEventHub:
    """Process-wide hub multiplexing one opencode event stream to N callers.

    Thread/loop safety:  one instance per event loop.  Designed to be
    stored on ``OpenCodeAdapter`` (which is also loop-local).  Public API
    is fully async.
    """

    def __init__(self) -> None:
        self._states: dict[str, _StreamState] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _key(agent_name: str, base_url: str) -> str:
        return f"{agent_name}:{base_url}"

    async def subscribe(
        self,
        *,
        agent_name: str,
        base_url: str,
        client: AsyncOpencode,
        session_id: str,
    ) -> AsyncIterator[Any]:
        """Yield opencode events scoped to ``session_id``.

        On entry, registers a per-caller queue.  On exit (normal or
        exceptional), unregisters it.  When the last subscriber leaves,
        the long-lived stream is closed; the next ``subscribe()`` reopens.
        """
        key = self._key(agent_name, base_url)
        sub = _Subscriber(session_id=session_id)
        state = await self._ensure_state(key, client)
        state.subscribers.add(sub)
        state.refcount += 1
        logger.debug(
            "event_hub_subscribed",
            key=key,
            session_id=session_id,
            subscribers=len(state.subscribers),
        )
        try:
            while True:
                event = await sub.queue.get()
                if event is _SHUTDOWN:
                    return
                yield event
        finally:
            await self._release(key, sub)

    def subscription(
        self,
        *,
        agent_name: str,
        base_url: str,
        client: AsyncOpencode,
        session_id: str,
    ) -> "_HubSubscription":
        """``async with`` 形式的订阅包装 — 比 ``async for ... in hub.subscribe()`` 整洁.

        Example::

            async with hub.subscription(...) as sub:
                async for event in sub:
                    ...

        在 ``__aexit__`` 时调 ``gen.aclose()`` 触发 ``subscribe`` 的 finally 释放订阅.
        """
        return _HubSubscription(
            hub=self,
            agent_name=agent_name,
            base_url=base_url,
            client=client,
            session_id=session_id,
        )

    async def _ensure_state(self, key: str, client: AsyncOpencode) -> _StreamState:
        """Open the long-lived stream for ``key`` if not already open.

        The lock prevents two concurrent first-subscribers from both
        opening a stream.  Once a state exists, the lock is no longer
        held during fanout — fanout is owned by its own background task.
        """
        async with self._lock:
            state = self._states.get(key)
            if state is None:
                stream = await client.event.list()
                # Build state with fanout_task=None first so it can be put
                # in the registry BEFORE the background task starts running.
                # The task captures ``state`` by reference, so it sees the
                # fully-populated object as soon as it is scheduled.
                state = _StreamState(stream=stream, fanout_task=None)
                self._states[key] = state
                state.fanout_task = asyncio.create_task(
                    self._fanout(key, state),
                    name=f"opencode-event-hub:{key}",
                )
                logger.info("event_hub_stream_opened", key=key)
            return state

    async def _fanout(self, key: str, state: _StreamState) -> None:
        """Background task: read the stream, push each event to all subs."""
        try:
            async for event in state.stream:
                # Snapshot: subscribers may join/leave during iteration.
                for sub in list(state.subscribers):
                    try:
                        sub.queue.put_nowait(event)
                    except asyncio.QueueFull:
                        # Slow consumer: skip rather than block the whole fanout.
                        logger.warning(
                            "event_hub_queue_full",
                            key=key,
                            session_id=sub.session_id,
                        )
        except Exception as e:
            logger.error("event_hub_fanout_failed", key=key, error=str(e))
        finally:
            await self._shutdown_state(key, state)

    async def _release(self, key: str, sub: _Subscriber) -> None:
        """Remove a subscriber; close the stream if it was the last one."""
        state = self._states.get(key)
        if state is None:
            return
        state.subscribers.discard(sub)
        state.refcount -= 1
        logger.debug(
            "event_hub_released",
            key=key,
            session_id=sub.session_id,
            subscribers=len(state.subscribers),
        )
        if state.refcount <= 0 and not state.subscribers:
            await self._shutdown_state(key, state)

    async def _shutdown_state(self, key: str, state: _StreamState) -> None:
        """Tear down the stream + fanout for ``key`` (idempotent)."""
        # Idempotency: only the first caller actually closes the stream;
        # subsequent callers see the key already gone from ``_states``.
        if self._states.get(key) is not state:
            return
        self._states.pop(key, None)
        if state.fanout_task is not None and not state.fanout_task.done():
            state.fanout_task.cancel()
        try:
            await state.stream.close()
        except Exception as e:
            logger.debug("event_hub_stream_close_warn", key=key, error=str(e))
        # Wake up any subscribers still parked on the queue so they
        # can see the SHUTDOWN sentinel and bail.
        for sub in list(state.subscribers):
            try:
                sub.queue.put_nowait(_SHUTDOWN)
            except asyncio.QueueFull:
                pass


class _HubSubscription:
    """``async with`` 包装 ``OpenCodeEventHub.subscribe`` 的一次性订阅."""

    def __init__(
        self,
        *,
        hub: OpenCodeEventHub,
        agent_name: str,
        base_url: str,
        client: AsyncOpencode,
        session_id: str,
    ) -> None:
        self._gen = hub.subscribe(
            agent_name=agent_name,
            base_url=base_url,
            client=client,
            session_id=session_id,
        )

    def __aiter__(self) -> AsyncIterator[Any]:
        return self._gen

    def __anext__(self) -> Any:
        return self._gen.__anext__()

    async def __aenter__(self) -> "_HubSubscription":
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self._gen.aclose()


__all__ = ["OpenCodeEventHub"]
