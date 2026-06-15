"""存储层 (Domain) 入口.

层次结构(自下而上):

    exceptions.py     异常体系
    models/           Models 层 = Tortoise Model (6 个实体) — schema 自动生成
    dto/              DTO 层 = pydantic 入参/出参 (Create/Update/Response)
    repositories/     Repositories 层 = ABC + Tortoise/MySQL/Memory 实现 (6 个实体)
    services/         Services 层 = 业务编排 + 跨 Repository 协作

公开 API:
    from openagent.store import (
        # Models
        Scenario, Session, ChatTurn, Message, Part, AuditLog,
        # DTO
        CreateScenarioRequest, ScenarioResponse, ...
        # 工厂
        ServiceContainer, build_default_container, build_container_from_settings,
        # 旧版(向后兼容, 给老 caller 用)
        SessionRepository, MemorySessionRepository, MySQLScenarioRepository, ...
    )

ORM: Tortoise ORM (tortoise-orm[asyncmy]). ``Tortoise.init()`` + ``Tortoise.generate_schemas()``
在启动期自动建表, 不再需要外部 ``docs/db/openagent-schema.sql`` 文件.
"""

from openagent.store import dto, models, repositories, services
from openagent.store.base import (
    Message as LegacyMessage,
)
from openagent.store.base import (
    Part as LegacyPart,
)
from openagent.store.base import (
    Session as LegacySession,
)
from openagent.store.base import (
    SessionRepository as LegacySessionRepository,
)
from openagent.store.base import (
    SessionRepositoryFactory,
    StorageBackend,
    StorageBackendFactory,
)
from openagent.store.exceptions import (
    DriverError,
    DuplicateError,
    NotFoundError,
    StoreError,
    TransactionError,
    ValidationError,
)
from openagent.store.memory import MemorySessionRepository as LegacyMemorySessionRepository
from openagent.store.memory import MemoryStorage
from openagent.store.mysql import MySQLStorage
from openagent.store.mysql import MySQLStorage as LegacyMySQLSessionRepository
from openagent.store.postgres import PostgresSessionRepository as LegacyPostgresSessionRepository
from openagent.store.postgres import PostgresStorage

# Auto-register legacy ``SessionRepositoryFactory`` backends so callers
# (``api/lifecycle/lifecycle.py``, ``AgentBridge`` adapters) can ``create(name)``
# without depending on import side-effects from subpackages. ``mysql`` is the
# v2 default — registered here so the lifecycle startup succeeds end-to-end.
SessionRepositoryFactory.register("memory", MemoryStorage)
SessionRepositoryFactory.register("postgres", PostgresStorage)
SessionRepositoryFactory.register("mysql", MySQLStorage)
from openagent.store.services import (
    AuditLogService,
    ChatTurnService,
    MessageService,
    PartService,
    ScenarioService,
    ServiceContainer,
    SessionService,
    build_container,
    build_container_from_settings,
    build_default_container,
)

# Re-export Models
Scenario = models.Scenario
Session = models.Session
ChatTurn = models.ChatTurn
Message = models.Message
Part = models.Part
AuditLog = models.AuditLog

# Re-export 常用 DTO
CreateScenarioRequest = dto.CreateScenarioRequest
UpdateScenarioRequest = dto.UpdateScenarioRequest
ScenarioResponse = dto.ScenarioResponse
CreateSessionRequest = dto.CreateSessionRequest
UpdateSessionRequest = dto.UpdateSessionRequest
SessionResponse = dto.SessionResponse
CreateChatTurnRequest = dto.CreateChatTurnRequest
UpdateChatTurnRequest = dto.UpdateChatTurnRequest
ChatTurnResponse = dto.ChatTurnResponse
CreateMessageRequest = dto.CreateMessageRequest
MessageResponse = dto.MessageResponse
CreatePartRequest = dto.CreatePartRequest
BatchCreatePartRequest = dto.BatchCreatePartRequest
PartResponse = dto.PartResponse
CreateAuditLogRequest = dto.CreateAuditLogRequest
AuditLogResponse = dto.AuditLogResponse

# Re-export Repository ABC
ScenarioRepository = repositories.ScenarioRepository
SessionRepository = repositories.SessionRepository
ChatTurnRepository = repositories.ChatTurnRepository
MessageRepository = repositories.MessageRepository
PartRepository = repositories.PartRepository
AuditLogRepository = repositories.AuditLogRepository

# Re-export MySQL 实现
MySQLScenarioRepository = repositories.MySQLScenarioRepository
MySQLSessionRepository = repositories.MySQLSessionRepository
MySQLChatTurnRepository = repositories.MySQLChatTurnRepository
MySQLMessageRepository = repositories.MySQLMessageRepository
MySQLPartRepository = repositories.MySQLPartRepository
MySQLAuditLogRepository = repositories.MySQLAuditLogRepository

# Re-export Memory 实现
MemoryScenarioRepository = repositories.MemoryScenarioRepository
MemorySessionRepository = repositories.MemorySessionRepository
MemoryChatTurnRepository = repositories.MemoryChatTurnRepository
MemoryMessageRepository = repositories.MemoryMessageRepository
MemoryPartRepository = repositories.MemoryPartRepository
MemoryAuditLogRepository = repositories.MemoryAuditLogRepository

__all__ = [
    # 异常
    "StoreError",
    "NotFoundError",
    "DuplicateError",
    "ValidationError",
    "TransactionError",
    "DriverError",
    # Models
    "Scenario",
    "Session",
    "ChatTurn",
    "Message",
    "Part",
    "AuditLog",
    # DTO
    "CreateScenarioRequest",
    "UpdateScenarioRequest",
    "ScenarioResponse",
    "CreateSessionRequest",
    "UpdateSessionRequest",
    "SessionResponse",
    "CreateChatTurnRequest",
    "UpdateChatTurnRequest",
    "ChatTurnResponse",
    "CreateMessageRequest",
    "MessageResponse",
    "CreatePartRequest",
    "BatchCreatePartRequest",
    "PartResponse",
    "CreateAuditLogRequest",
    "AuditLogResponse",
    # Repository ABC
    "ScenarioRepository",
    "SessionRepository",
    "ChatTurnRepository",
    "MessageRepository",
    "PartRepository",
    "AuditLogRepository",
    # MySQL Repository
    "MySQLScenarioRepository",
    "MySQLSessionRepository",
    "MySQLChatTurnRepository",
    "MySQLMessageRepository",
    "MySQLPartRepository",
    "MySQLAuditLogRepository",
    # Memory Repository
    "MemoryScenarioRepository",
    "MemorySessionRepository",
    "MemoryChatTurnRepository",
    "MemoryMessageRepository",
    "MemoryPartRepository",
    "MemoryAuditLogRepository",
    # Services
    "ScenarioService",
    "SessionService",
    "ChatTurnService",
    "MessageService",
    "PartService",
    "AuditLogService",
    "ServiceContainer",
    "build_container",
    "build_default_container",
    "build_container_from_settings",
    # 子包
    "models",
    "dto",
    "repositories",
    "services",
    # 兼容老 API (旧版 base/memory/postgres 暴露的符号, 旧代码 import 不破)
    "SessionRepositoryFactory",
    "StorageBackend",
    "StorageBackendFactory",
    "MemoryStorage",
    "PostgresStorage",
    "MySQLStorage",
    "LegacyMessage",
    "LegacyPart",
    "LegacySession",
    "LegacySessionRepository",
    "LegacyMemorySessionRepository",
    "LegacyPostgresSessionRepository",
    "LegacyMySQLSessionRepository",
]
