"""Models 层公共工具 + Tortoise ORM 初始化.

每个 Model 都是 ``tortoise.models.Model`` 子类, schema 字段直接由字段类型
描述, 启动期由 ``Tortoise.init()`` + ``Tortoise.generate_schemas()`` 自动建表,
不再依赖外部 DDL 文件 (docs/db/hermetic_agent-schema.sql).
"""
from __future__ import annotations

import functools
import json
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from tortoise import Tortoise


#: 注册到 Tortoise 的 model 模块路径 (``modules={"models": [...]}``).
#: ``Tortoise.init`` 会 import 这些 module 并收集 ``tortoise.models.Model`` 子类.
MODULES_PATH: list[str] = [
    "hermetic_agent.store.models",
]


def utcnow() -> datetime:
    """UTC naive ``datetime`` — 业务层需要时显式 ``.replace(tzinfo=timezone.utc)``.

    保持跟旧 @dataclass 模型同样的工厂函数签名, Repository 层业务方法还在用.
    """
    return datetime.utcnow()


def _json_default(value: Any) -> Any:
    """``JSONField`` 序列化时的兜底.

    Tortoise 默认的 ``JSON_DUMPS`` 不带 ``default=`` 回调, ``UUID`` / ``Decimal``
    / ``datetime`` 这类对象 ``json.dumps`` 直接 ``TypeError``. 业务里
    ``AuditLog.after_data`` 会带 UUID (FK 列写回时是 ``uuid.UUID`` 实例),
    没有这个兜底 audit 写入会全炸.
    """
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _patch_json_dumps() -> None:
    """替换 ``tortoise.fields.data.JSON_DUMPS``, 让所有 ``JSONField`` 序列化时支持 UUID.

    注意: Tortoise 的 ``JSONField.__init__`` 把 ``JSON_DUMPS`` 当作 **默认参数值**
    (Python 函数默认值在 ``def`` 时求值), 后续给 ``Tortoise.JSON_DUMPS = ...`` 赋值
    不会影响已经存在的 ``JSONField`` 实例. 必须直接 patch 源模块的全局变量,
    且在任何 ``JSONField`` 实例化前生效.

    本模块 ``_common.py`` 在 ``hermetic_agent.store.models`` 子包导入时第一时间执行,
    所有 Model 在子模块中定义时 ``JSONField()`` 已用到 patched 版本.
    """
    from tortoise import fields as _tortoise_fields
    _tortoise_fields.data.JSON_DUMPS = functools.partial(
        json.dumps, separators=(",", ":"), default=_json_default,
    )


_patch_json_dumps()


def _patch_existing_jsonfield_encoders() -> None:
    """事后修复: 把已经存在的 ``JSONField`` 实例的 ``encoder`` 替换成 patched 版本.

    原因: Tortoise 的 ``JSONField.__init__`` 把 ``JSON_DUMPS`` 当作默认参数值,
    默认值在 ``def`` 时求值. 即便我们 patch 了 ``tortoise.fields.data.JSON_DUMPS``,
    已经创建的 ``JSONField`` 实例仍然持有旧 ``JSON_DUMPS`` 引用.

    本函数遍历 ``Model.Meta.fields_map`` 中所有 ``JSONField`` 实例, 把 ``encoder``
    属性替换成新的 ``json.dumps(..., default=_json_default)``. 调用时机:
    在所有 Model 类被 import + 定义完之后 (在 ``__init__.py`` 末尾).
    """
    from tortoise import fields as _tortoise_fields
    from tortoise.models import Model

    new_encoder = _tortoise_fields.data.JSON_DUMPS
    patched = 0
    for model_cls in Model.__subclasses__():
        for field_obj in getattr(model_cls._meta, "fields_map", {}).values():
            if isinstance(field_obj, _tortoise_fields.JSONField):
                if field_obj.encoder is not new_encoder:
                    field_obj.encoder = new_encoder
                    patched += 1
    from structlog import get_logger
    get_logger(__name__).debug("jsonfield_encoders_patched", count=patched)


async def init_tortoise(
    db_url: str,
    *,
    generate_schemas: bool = True,
) -> None:
    """初始化 Tortoise + (可选) 建表.

    Args:
        db_url: 数据库 DSN. 形如 ``mysql://user:pass@host:port/db`` 或
            ``sqlite://:memory:`` (测试用).
        generate_schemas: True 时自动建表 (开发 / 容器部署); False 时
            跳过 (生产用 Alembic 迁移时).

    Raises:
        ConfigurationError: db_url 格式错 / 模块路径找不到 model.
    """
    await Tortoise.init(
        db_url=db_url,
        modules={"models": MODULES_PATH},
        use_tz=False,
        timezone="UTC",
        # Sanic + Tortoise 1.1.7: 启动期 (lifecycle startup hook) 和 请求期
        # (controller handler) 跑在不同 asyncio task, 默认 ``Tortoise.init()``
        # 不开 global fallback 会报 "No TortoiseContext is currently active".
        # 开这个 flag 让 ``get_current_context()`` 退回到 _global_context, 跟
        # ``tortoise.contrib.fastapi.RegisterTortoise`` 一样的处理.
        _enable_global_fallback=True,
    )
    if generate_schemas:
        await Tortoise.generate_schemas()
        from structlog import get_logger
        get_logger(__name__).info(
            "tortoise_schemas_generated",
            db_url=_safe_url(db_url),
        )


async def close_tortoise() -> None:
    """关闭所有 DB 连接. 应用退出 / 测试 teardown 调."""
    await Tortoise.close_connections()


def _safe_url(url: str) -> str:
    """脱敏: 去掉 DSN 里的密码 (日志/审计用)."""
    try:
        from urllib.parse import urlparse, urlunparse
    except ImportError:
        return url
    p = urlparse(url)
    if p.password is None:
        return url
    netloc = f"{p.username}:***@{p.hostname}"
    if p.port:
        netloc += f":{p.port}"
    return urlunparse(p._replace(netloc=netloc))


__all__ = [
    "MODULES_PATH",
    "utcnow",
    "init_tortoise",
    "close_tortoise",
]
