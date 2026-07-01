"""Models 层 — 领域实体 (Tortoise ORM Model).

层次:
    Models 层 = 等同 Java DO/Entity = Tortoise ``Model`` 子类, schema 字段由
    ``tortoise.fields`` 直接描述, 启动期由 ``Tortoise.init()`` + 
    ``Tortoise.generate_schemas()`` 自动建表, 不再需要外部 DDL 文件.

字段命名约定:
    - 全部 snake_case, Python 属性 = DB 列名 (例如 ``metadata`` 字段对应
      ``metadata`` 列, ``id`` 字段对应 ``id`` 列)
    - FK 字段: ``scenario`` / ``session`` / ``turn`` / ``message`` / 
      ``user_message_id`` / ``assistant_message_id`` (后者是软引用, 不建 FK)
    - 软引用场景: ``ChatTurn.user_message_id`` / ``assistant_message_id`` 和
      ``AuditLog.resource_id`` 都是 ``CharField``, 不建 FK, 避免 ``generate_schemas``
      不支持的循环依赖
"""

# 在所有 Model 类已定义后, 修复已实例化 ``JSONField`` 的 ``encoder`` 默认值.
# 见 ``hermetic_agent.store.models._common._patch_existing_jsonfield_encoders`` 注释.
from hermetic_agent.store.models._common import _patch_existing_jsonfield_encoders
from hermetic_agent.store.models.agent import Agent
from hermetic_agent.store.models.audit_log import AuditLog
from hermetic_agent.store.models.chat_turn import ChatTurn
from hermetic_agent.store.models.command import Command
from hermetic_agent.store.models.mcp_config import McpConfig
from hermetic_agent.store.models.message import Message
from hermetic_agent.store.models.part import Part
from hermetic_agent.store.models.prompt import Prompt
from hermetic_agent.store.models.scenario import Scenario
from hermetic_agent.store.models.session import Session
from hermetic_agent.store.models.skill import Skill as SkillModel

_patch_existing_jsonfield_encoders()


__all__ = [
    "Scenario",
    "Session",
    "ChatTurn",
    "Message",
    "Part",
    "AuditLog",
    "SkillModel",
    "McpConfig",
    "Prompt",
    "Command",
    "Agent",
]
