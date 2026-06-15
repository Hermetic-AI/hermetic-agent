"""存储层异常体系.

层次:
    StoreError                根异常
    ├─ NotFoundError          实体不存在 (get_by_id 返回 None 时)
    ├─ DuplicateError         唯一约束冲突 (uk_scenarios_code_version 等)
    ├─ ValidationError        入参校验失败 (业务规则)
    ├─ TransactionError       事务回滚 / 死锁
    └─ DriverError            底层驱动异常包装 (asyncmy errors)
"""

from __future__ import annotations


class StoreError(Exception):
    """存储层根异常.

    所有 Repository / Service 抛出的异常都继承自本类, 业务层可统一捕获.
    """


class NotFoundError(StoreError):
    """实体不存在.

    Repository.get_by_id() / get_by_*() 找不到时抛, 不再返回 None.
    Service 层负责把"业务找不到"包装成更具体的消息.
    """

    def __init__(self, entity: str, key: str) -> None:
        super().__init__(f"{entity} not found: {key}")
        self.entity = entity
        self.key = key


class DuplicateError(StoreError):
    """唯一约束冲突.

    例: scenarios (code, version) 已存在; sessions.id 重复 INSERT.
    """


class ValidationError(StoreError):
    """入参校验失败(超出 DTO pydantic 范围, 在 Service / Repository 层加的额外业务规则)."""


class TransactionError(StoreError):
    """事务回滚 / 死锁 / 超时."""


class DriverError(StoreError):
    """底层驱动异常(asyncmy / 内存实现)包装.

    一般不应该 catch 后重抛, 让其透传, 上层统一打日志.
    """
