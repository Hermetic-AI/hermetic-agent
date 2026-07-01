"""DTO 层公共类型与转换辅助.

DTO = 等同 Java DTO/VO = 跨层数据传递载体.
特点:
- 用 ``pydantic BaseModel`` (校验 + 序列化)
- 入参 DTO 在 Service 层校验, 出参 DTO 在 Service 层 from_model(model) 转换
- DTO 不应暴露内部 Model 字段(如 created_at 由系统填, DTO 不接受外部传入)
- Model 现在是 Tortoise ORM, 转换工厂里读属性 (m.id / m.user_id / m.metadata 等),
  Tortoise Model 的字段访问跟 dataclass 一致, 不需要额外适配

ID 兼容: Tortoise ``UUIDField(binary=False)`` 在 Python 里返回 ``uuid.UUID`` 对象
(虽然 DB 里是 CHAR(36) 字符串), Service 层传 ``s.id`` 给 DTO 时会撞 Pydantic 的
``str`` 校验. 这里的 ``_coerce_uuid`` field validator 统一把 ``UUID`` 强转成
``str``, 业务层就不用关心类型.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DTOMixin(BaseModel):
    """DTO 公共基类.

    - 禁用额外字段 (extra=forbid) — 业务 DTO 拒绝未知字段
    - ORM 模式关闭 (Pydantic v2 用 from_attributes=True), 但我们手动写
      ``from_model`` 工厂更可控, 字段映射 + Decimal 转 float 在那里集中
    - ``_coerce_uuid`` validator: 任何标注为 ``str`` 的字段, 接受 ``UUID`` 自动转
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    @field_validator("*", mode="before")
    @classmethod
    def _coerce_uuid(cls, value: Any) -> Any:
        if isinstance(value, uuid.UUID):
            return str(value)
        return value


def iso_or_none(dt: datetime | None) -> str | None:
    """``datetime`` -> ISO 字符串, None 原样返回. 序列化到 JSON 时用."""
    return dt.isoformat() if dt else None


@dataclass
class ActorContext:
    """调用方身份上下文 — 资产 CRUD / resolve 时的权限判断来源.

    通过 dataclass 而非 pydantic BaseModel 是因为它跨 Service / Controller
    多层传递, 用纯数据载体更轻; 业务字段(roles)用 default_factory 避开
    可变默认值.
    """

    user_id: str
    tenant_id: Optional[str] = None
    roles: list[str] = field(default_factory=list)

    def is_anonymous(self) -> bool:
        return self.user_id == "anonymous"


__all__ = [
    "DTOMixin",
    "iso_or_none",
    "Field",
    "ActorContext",
]
