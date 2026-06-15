"""Models 层 — 领域实体 dataclass.

层次:
    Models 层 = 等同 Java DO/Entity = 纯数据载体, 与 DB schema 1:1.
    规则:
        - 全部 ``@dataclass(frozen=False)``, 字段可变(Repository 写完会改 is_deleted 等)
        - 字段命名 = DB 列名 (snake_case)
        - 字段类型用 Python 原生 (str / int / Decimal / datetime / dict)
        - 必填字段在 ``__init__`` 上无默认值
        - 可选字段用 ``field(default=None)`` 或 ``field(default_factory=...)``
        - 每个 Model 提供 ``to_db_dict()`` / ``from_db_dict()`` 两个方法,
          处理 bool <-> 0/1 转换. datetime / dict / Decimal 由 asyncmy 自动处理.
"""

from openagent.store.models.audit_log import AuditLog
from openagent.store.models.chat_turn import ChatTurn
from openagent.store.models.message import Message
from openagent.store.models.part import Part
from openagent.store.models.scenario import Scenario
from openagent.store.models.session import Session

__all__ = [
    "Scenario",
    "Session",
    "ChatTurn",
    "Message",
    "Part",
    "AuditLog",
]
