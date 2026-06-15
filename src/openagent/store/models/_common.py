"""Models 层公共类型与转换辅助.

每个 Model 都是 ``@dataclass``, 与 ``openagent/store/schema/openagent-schema.sql`` v2 schema 1:1 对应.

字段类型映射 (Python <-> MySQL):
- ``str``             <-> VARCHAR / CHAR / TEXT / MEDIUMTEXT
- ``int``             <-> INT / INT UNSIGNED
- ``Decimal``         <-> DECIMAL(12,6)
- ``datetime``        <-> DATETIME(6) (naive, 无时区; DB 端存 UTC)
- ``bool``            <-> TINYINT(1) (0/1, asyncmy 自动转, 但读出是 int)
- ``dict | None``     <-> JSON (asyncmy 读出是 str, 需 to_db_json / from_db_json 转换)
- ``None``            <-> NULL
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any


def to_db_bool(value: bool | int | None) -> int:
    """Python ``bool`` -> MySQL ``TINYINT(1)`` (0/1)."""
    if value is None:
        return 0
    return 1 if value else 0


def from_db_bool(value: int | bool | None) -> bool:
    """MySQL ``TINYINT(1)`` -> Python ``bool``."""
    if value is None:
        return False
    return bool(value)


def to_db_json(value: Any) -> str | None:
    """``dict`` / ``list`` -> JSON 字符串 (MySQL JSON 列接受 str, 自动 parse).

    asyncmy 不能直接传 dict 到 SQL 参数, 必须先 ``json.dumps``.
    """
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str)


def from_db_json(value: Any) -> Any:
    """MySQL JSON 列读出的 str -> Python ``dict`` / ``list``.

    asyncmy 把 JSON 列读为 str, 不自动 ``json.loads``. 此处兜底:
    - 已经是 dict/list: 直接返回 (兼容未来驱动)
    - 是 str: 尝试 parse, 失败返回 None
    - 其他: 原样返回
    """
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return None
    return value


def utcnow() -> datetime:
    """UTC naive ``datetime`` — 与 MySQL ``DATETIME(6)`` 默认 ``CURRENT_TIMESTAMP(6)`` 口径一致.

    返回无时区的 datetime, 业务层需要时显式 ``.replace(tzinfo=timezone.utc)``.
    """
    now = datetime.utcnow()
    return now

