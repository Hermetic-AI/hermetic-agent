"""DTO 层公共类型与转换辅助.

DTO = 等同 Java DTO/VO = 跨层数据传递载体.
特点:
- 用 ``pydantic BaseModel`` (校验 + 序列化)
- 入参 DTO 在 Service 层校验, 出参 DTO 在 Service 层 from_model(model) 转换
- DTO 不应暴露内部 Model 字段(如 created_at 由系统填, DTO 不接受外部传入)
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DTOMixin(BaseModel):
    """DTO 公共基类.

    - 禁用额外字段 (extra=forbid) — 业务 DTO 拒绝未知字段
    - ORM 模式关闭 (Pydantic v2 用 from_attributes=True), 但 Model 是 dataclass 不是 ORM,
      我们手动写 ``from_model`` 工厂更可控
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )


def model_to_dict(model: Any) -> dict[str, Any]:
    """``@dataclass`` Model 转 dict. 处理 Decimal -> str (pydantic 友好)."""

    from dataclasses import asdict, is_dataclass

    if not is_dataclass(model):
        raise TypeError(f"Expected dataclass, got {type(model).__name__}")
    d = asdict(model)
    return _normalize(d)


def _normalize(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _normalize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_normalize(v) for v in obj]
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


def iso_or_none(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


__all__ = [
    "DTOMixin",
    "model_to_dict",
    "iso_or_none",
    "Field",
]
