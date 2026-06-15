"""存储层抽象与数据模型。

定义 ``Session`` / ``Message`` / ``Part`` 数据类，以及仓储接口
``SessionRepository`` 和后端工厂 ``SessionRepositoryFactory``。
具体实现见 ``memory.py`` 与 ``postgres.py``。
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class Part:
    """消息的一个组成片段（如文本、工具输入/输出等）。"""

    content: str
    part_type: str = "text"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典，便于持久化或跨进程传输。"""
        return {
            "content": self.content,
            "part_type": self.part_type,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Part:
        """从字典反序列化为 ``Part`` 实例。

        Args:
            data: 包含 ``content`` / ``part_type`` / ``metadata`` 的字典。

        Returns:
            重建的 ``Part`` 实例。
        """
        return cls(
            content=data.get("content", ""),
            part_type=data.get("part_type", "text"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Message:
    """会话中的一条消息，包含角色、内容、创建时间及组成片段。"""

    role: str
    content: str
    session_id: str | None = None
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = field(default_factory=datetime.utcnow)
    parts: list[Part] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典。"""
        return {
            "message_id": self.message_id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
            "parts": [p.to_dict() for p in self.parts],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Message:
        """从字典反序列化为 ``Message`` 实例。

        Args:
            data: 至少包含 ``role``；其余字段可缺省。

        Returns:
            重建的 ``Message`` 实例。
        """
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.utcnow()
        return cls(
            message_id=data.get("message_id", str(uuid.uuid4())),
            session_id=data.get("session_id"),
            role=data["role"],
            content=data.get("content", ""),
            created_at=created_at,
            parts=[Part.from_dict(p) for p in data.get("parts", [])],
            metadata=data.get("metadata", {}),
        )


@dataclass
class Session:
    """一次会话的聚合根，包含元数据与消息列表。"""

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    title: str = "New Session"
    model: str | None = None
    agent_name: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    messages: list[Message] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典。"""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "title": self.title,
            "model": self.model,
            "agent_name": self.agent_name,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "messages": [m.to_dict() for m in self.messages],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Session:
        """从字典反序列化为 ``Session`` 实例。

        Args:
            data: 会话字段字典；缺省值由 dataclass 字段工厂填充。

        Returns:
            重建的 ``Session`` 实例。
        """
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.utcnow()
        updated_at = data.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        elif updated_at is None:
            updated_at = datetime.utcnow()
        return cls(
            session_id=data.get("session_id", str(uuid.uuid4())),
            user_id=data.get("user_id", ""),
            title=data.get("title", "New Session"),
            model=data.get("model"),
            agent_name=data.get("agent_name", ""),
            created_at=created_at,
            updated_at=updated_at,
            messages=[Message.from_dict(m) for m in data.get("messages", [])],
            metadata=data.get("metadata", {}),
        )


class SessionRepository(ABC):
    """抽象会话/消息仓储（从 ``StorageBackend`` 改名而来）。

    命名遵循 ``*Repository`` 规则（见 architecture-enforcement §3）；
    旧名 ``StorageBackend`` 仍以别名形式保留。
    """

    @abstractmethod
    async def save_session(self, session: Session) -> None:
        """创建或更新一个会话。

        Args:
            session: 完整会话对象。
        """
        ...

    async def create_session(self, session: Session) -> None:
        """持久化一个新创建的会话。

        默认实现委托给 ``save_session``，后端可按需覆盖。

        Args:
            session: 新创建的会话对象。
        """
        await self.save_session(session)

    @abstractmethod
    async def get_session(self, session_id: str) -> Session | None:
        """按 ID 加载会话。

        Args:
            session_id: 会话 ID。

        Returns:
            找到时返回 ``Session``，否则 ``None``。
        """
        ...

    @abstractmethod
    async def list_sessions(
        self, user_id: str | None = None, limit: int = 100
    ) -> list[Session]:
        """列出最近更新的会话。

        Args:
            user_id: 可选的用户 ID 过滤。
            limit: 最多返回的会话数量。

        Returns:
            按 ``updated_at`` 倒序的会话列表。
        """
        ...

    @abstractmethod
    async def delete_session(self, session_id: str) -> bool:
        """删除指定会话及其消息。

        Args:
            session_id: 会话 ID。

        Returns:
            是否确实删除了一条记录。
        """
        ...

    @abstractmethod
    async def save_message(self, session_id: str, message: Message) -> None:
        """创建或更新一条消息。

        Args:
            session_id: 所属会话 ID。
            message: 消息对象。
        """
        ...

    async def create_message(self, message: Message) -> None:
        """持久化一条新消息。

        默认实现委托给 ``save_message``，并从 ``message.session_id`` 取
        会话 ID。

        Args:
            message: 新创建的消息。

        Raises:
            ValueError: 当 ``message.session_id`` 为空时。
        """
        if not message.session_id:
            raise ValueError("create_message requires message.session_id to be set")
        await self.save_message(message.session_id, message)

    @abstractmethod
    async def get_messages(
        self, session_id: str, limit: int = 100
    ) -> list[Message]:
        """按 ``created_at`` 升序加载指定会话的消息。

        Args:
            session_id: 所属会话 ID。
            limit: 最多返回的消息数量。

        Returns:
            消息列表。
        """
        ...


class SessionRepositoryFactory:
    """``SessionRepository`` 实现工厂（从 ``StorageBackendFactory`` 改名而来）。"""
    _registry: dict[str, type[SessionRepository]] = {}

    @classmethod
    def register(cls, name: str, backend_class: type[SessionRepository]) -> None:
        """注册一个仓储实现到工厂。

        Args:
            name: 后端标识，如 ``"postgres"`` / ``"memory"``。
            backend_class: 仓储类，必须继承 ``SessionRepository``。

        Raises:
            TypeError: 当 ``backend_class`` 不是 ABC 的子类时。
        """
        if not issubclass(backend_class, ABC):
            raise TypeError(f"{backend_class} must be an ABC")
        cls._registry[name] = backend_class
        logger.debug("storage_backend_registered", name=name, backend=backend_class.__name__)

    @classmethod
    def create(cls, name: str, settings: Any | None = None) -> SessionRepository:
        """根据名称实例化对应的仓储。

        Args:
            name: 已注册的后端标识。
            settings: 可选的 ``Settings`` 对象；``postgres`` 后端会从中
                读取 DSN 与连接池配置。

        Returns:
            初始化好的 ``SessionRepository`` 实例。

        Raises:
            ValueError: 当 ``name`` 未注册时。
        """
        if name not in cls._registry:
            available = list(cls._registry.keys())
            logger.error("storage_backend_not_found", name=name, available=available)
            raise ValueError(f"Unknown storage backend: {name}")
        backend_class = cls._registry[name]
        logger.info("creating_storage_backend", name=name)

        # Build kwargs per backend type
        if name == "postgres" and settings is not None:
            return backend_class(
                dsn=getattr(settings, "postgres_dsn", "postgresql://localhost:5432/openagent"),
                min_size=getattr(settings, "postgres_pool_min_size", 5),
                max_size=getattr(settings, "postgres_pool_max_size", 20),
            )
        if name == "mysql":
            from openagent.store.mysql import MySQLStorage

            return MySQLStorage(
                dsn=getattr(settings, "mysql_dsn", "mysql://root@127.0.0.1:3306/openagent"),
            )
        # memory backend takes no args
        return backend_class()

    @classmethod
    def list_backends(cls) -> list[str]:
        """列出所有已注册的后端标识。"""
        return list(cls._registry.keys())


# Back-compat aliases for callers still on the old names.
StorageBackend = SessionRepository
StorageBackendFactory = SessionRepositoryFactory
