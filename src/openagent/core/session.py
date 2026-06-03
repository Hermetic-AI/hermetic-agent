"""Session Manager - 会话管理器

封装 opencode serve 的 Session API，负责会话的完整生命周期管理。

支持的操作：
- 创建新会话（create）
- 向会话发送消息并获取回复（chat）
- 获取会话历史消息（messages）
- 中止正在运行的会话（abort）
- 回退/恢复会话（revert / unrevert）
- 摘要会话（summarize）
- 删除会话（delete）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional
from uuid import uuid4

import structlog

# Try to import the official opencode Python SDK, fall back to stub if not available.
try:
    from opencode_ai import AsyncOpencode  # type: ignore
    from opencode_ai.types.text_part_input_param import TextPartInputParam  # type: ignore
except ImportError:
    from openagent._vendor.opencode import AsyncOpencode  # type: ignore
    TextPartInputParam = dict  # type: ignore

from openagent.core.agent_pool import AgentInstance, AgentPoolManager

logger = structlog.get_logger(__name__)


@dataclass
class SessionInfo:
    """会话信息"""

    session_id: str
    agent_name: str
    agent_base_url: str
    model: Optional[str] = None


class SessionManager:
    """会话管理器

    封装 opencode serve 的 Session API，提供会话生命周期管理。

    Usage:
        sessions = SessionManager(pool)
        session_id = await sessions.create("agent-shanghai", model="claude-sonnet")
        response = await sessions.chat(session_id, "帮我分析这份代码")
        history = await sessions.get_messages(session_id)
        await sessions.delete(session_id)
    """

    def __init__(self, pool: AgentPoolManager) -> None:
        self._pool = pool
        self._sessions: dict[str, SessionInfo] = {}
        self._clients: dict[str, AsyncOpencode] = {}

    def _get_or_create_client(self, instance: AgentInstance) -> AsyncOpencode:
        """获取或创建指定实例的 OpenCode 客户端"""
        if instance.name not in self._clients:
            self._clients[instance.name] = AsyncOpencode(base_url=instance.base_url)
        return self._clients[instance.name]

    async def create(
        self,
        agent_name: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> SessionInfo:
        """创建新会话

        Args:
            agent_name: 注册的 Agent 实例名称
            model: 可选，指定模型
            system_prompt: 可选，系统提示词
            session_id: 可选，指定会话 ID（用于恢复已有会话）

        Returns:
            SessionInfo 对象，包含会话 ID 和关联的 Agent 信息

        Raises:
            ValueError: 如果指定的 Agent 不存在
            RuntimeError: 如果创建会话失败
        """
        instance = self._pool.get_instance(agent_name)
        if instance is None:
            raise ValueError(f"Agent '{agent_name}' not found in pool")

        client = self._get_or_create_client(instance)

        try:
            if session_id:
                # 恢复已有会话
                session_id_str = session_id
                session_info = SessionInfo(
                    session_id=session_id_str,
                    agent_name=agent_name,
                    agent_base_url=instance.base_url,
                    model=model,
                )
            else:
                # 创建新会话
                result = await client.session.create()
                session_id_str = result.id

                session_info = SessionInfo(
                    session_id=session_id_str,
                    agent_name=agent_name,
                    agent_base_url=instance.base_url,
                    model=model,
                )

                instance.current_session_id = session_id_str

            self._sessions[session_id_str] = session_info
            logger.info(
                "session_created",
                session_id=session_id_str,
                agent_name=agent_name,
                model=model,
            )

            return session_info

        except Exception as e:
            logger.error("session_create_failed", agent_name=agent_name, error=str(e))
            raise RuntimeError(f"Failed to create session: {e}") from e

    async def chat(
        self,
        session_id: str,
        message: str,
        timeout: Optional[float] = None,
    ) -> dict[str, Any]:
        """向会话发送消息并获取回复

        Args:
            session_id: 会话 ID
            message: 用户消息
            timeout: 可选，超时时间（秒）

        Returns:
            包含回复内容的字典

        Raises:
            ValueError: 如果会话不存在
            RuntimeError: 如果发送消息失败
        """
        session_info = self._sessions.get(session_id)
        if session_info is None:
            raise ValueError(f"Session '{session_id}' not found")

        instance = self._pool.get_instance(session_info.agent_name)
        if instance is None:
            raise RuntimeError(f"Agent '{session_info.agent_name}' not found")

        client = self._get_or_create_client(instance)

        try:
            result = await client.session.chat(
                session_id,
                model_id=session_info.model or "default",
                provider_id="opencode",
                parts=[TextPartInputParam(text=message, type="text", id=f"prt_{str(uuid4())[:20]}")],
                timeout=timeout,
            )

            logger.info("session_chat", session_id=session_id, message_length=len(message))
            return result.model_dump() if hasattr(result, "model_dump") else {"result": result}

        except Exception as e:
            logger.error("session_chat_failed", session_id=session_id, error=str(e))
            raise RuntimeError(f"Failed to send message: {e}") from e

    async def chat_stream(
        self,
        session_id: str,
        message: str,
        timeout: Optional[float] = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """向会话发送消息并获取流式回复

        Args:
            session_id: 会话 ID
            message: 用户消息
            timeout: 可选，超时时间（秒）

        Yields:
            实时事件字典

        Raises:
            ValueError: 如果会话不存在
        """
        session_info = self._sessions.get(session_id)
        if session_info is None:
            raise ValueError(f"Session '{session_id}' not found")

        instance = self._pool.get_instance(session_info.agent_name)
        if instance is None:
            raise RuntimeError(f"Agent '{session_info.agent_name}' not found")

        client = self._get_or_create_client(instance)

        try:
            async with client.session.with_streaming_response.chat(
                session_id,
                model_id=session_info.model or "default",
                provider_id="opencode",
                parts=[TextPartInputParam(text=message, type="text", id=f"prt_{str(uuid4())[:20]}")],
                timeout=timeout,
            ) as response:
                async for line in response.iter_lines():
                    if line:
                        import json
                        try:
                            data = json.loads(line)
                            yield data
                        except json.JSONDecodeError:
                            yield {"raw": line}

        except Exception as e:
            logger.error("session_chat_stream_failed", session_id=session_id, error=str(e))
            raise RuntimeError(f"Failed to stream message: {e}") from e

    async def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        """获取会话历史消息

        Args:
            session_id: 会话 ID

        Returns:
            消息列表

        Raises:
            ValueError: 如果会话不存在
        """
        session_info = self._sessions.get(session_id)
        if session_info is None:
            raise ValueError(f"Session '{session_id}' not found")

        instance = self._pool.get_instance(session_info.agent_name)
        if instance is None:
            raise RuntimeError(f"Agent '{session_info.agent_name}' not found")

        client = self._get_or_create_client(instance)

        try:
            result = await client.session.messages(session_id=session_id)
            messages = result.messages if hasattr(result, "messages") else result
            return [m.model_dump() if hasattr(m, "model_dump") else m for m in messages]

        except Exception as e:
            logger.error("session_get_messages_failed", session_id=session_id, error=str(e))
            raise RuntimeError(f"Failed to get messages: {e}") from e

    async def abort(self, session_id: str) -> bool:
        """中止正在运行的会话

        Args:
            session_id: 会话 ID

        Returns:
            是否成功中止

        Raises:
            ValueError: 如果会话不存在
        """
        session_info = self._sessions.get(session_id)
        if session_info is None:
            raise ValueError(f"Session '{session_id}' not found")

        instance = self._pool.get_instance(session_info.agent_name)
        if instance is None:
            raise RuntimeError(f"Agent '{session_info.agent_name}' not found")

        client = self._get_or_create_client(instance)

        try:
            await client.session.abort(session_id=session_id)
            logger.info("session_aborted", session_id=session_id)
            return True

        except Exception as e:
            logger.error("session_abort_failed", session_id=session_id, error=str(e))
            return False

    async def revert(self, session_id: str) -> bool:
        """回退会话到上一个状态

        Args:
            session_id: 会话 ID

        Returns:
            是否成功回退

        Raises:
            ValueError: 如果会话不存在
        """
        session_info = self._sessions.get(session_id)
        if session_info is None:
            raise ValueError(f"Session '{session_id}' not found")

        instance = self._pool.get_instance(session_info.agent_name)
        if instance is None:
            raise RuntimeError(f"Agent '{session_info.agent_name}' not found")

        client = self._get_or_create_client(instance)

        try:
            await client.session.revert(session_id=session_id)
            logger.info("session_reverted", session_id=session_id)
            return True

        except Exception as e:
            logger.error("session_revert_failed", session_id=session_id, error=str(e))
            return False

    async def summarize(self, session_id: str) -> Optional[str]:
        """对会话进行摘要

        Args:
            session_id: 会话 ID

        Returns:
            摘要内容

        Raises:
            ValueError: 如果会话不存在
        """
        session_info = self._sessions.get(session_id)
        if session_info is None:
            raise ValueError(f"Session '{session_id}' not found")

        instance = self._pool.get_instance(session_info.agent_name)
        if instance is None:
            raise RuntimeError(f"Agent '{session_info.agent_name}' not found")

        client = self._get_or_create_client(instance)

        try:
            result = await client.session.summarize(session_id=session_id)
            summary = result.summary if hasattr(result, "summary") else str(result)
            logger.info("session_summarized", session_id=session_id, summary_length=len(summary))
            return summary

        except Exception as e:
            logger.error("session_summarize_failed", session_id=session_id, error=str(e))
            return None

    async def delete(self, session_id: str) -> bool:
        """删除会话

        Args:
            session_id: 会话 ID

        Returns:
            是否成功删除

        Raises:
            ValueError: 如果会话不存在
        """
        session_info = self._sessions.pop(session_id, None)
        if session_info is None:
            raise ValueError(f"Session '{session_id}' not found")

        instance = self._pool.get_instance(session_info.agent_name)
        if instance is None:
            logger.warning("delete_session_agent_not_found", agent_name=session_info.agent_name)
            return True

        client = self._get_or_create_client(instance)

        try:
            await client.session.delete(session_id=session_id)
            logger.info("session_deleted", session_id=session_id)
            return True

        except Exception as e:
            logger.error("session_delete_failed", session_id=session_id, error=str(e))
            return False

    def get_session(self, session_id: str) -> Optional[SessionInfo]:
        """获取指定会话的信息"""
        return self._sessions.get(session_id)

    def list_sessions(self) -> dict[str, SessionInfo]:
        """列出所有会话"""
        return self._sessions.copy()
