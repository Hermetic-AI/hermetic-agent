"""MySQL 驱动封装 — asyncmy 连接池 + 事务 + 启动期 DDL 幂等执行.

层次:
    MySQLConfig         数据类, 装 host/port/user/password/db 等
    MySQLPool           连接池封装 (acquire / execute / fetch / init_schema)
    transaction()       上下文管理器, 自动 commit / rollback

设计要点:
- 启动期 ``init_schema(ddl)`` 幂等执行 DDL (v2 schema 全部 IF NOT EXISTS)
- ``transaction()`` 用 asyncmy 的 begin/commit/rollback 包装
- 所有 SQL 走 ``%s`` 占位符 (asyncmy 风格, 与 asyncpg 的 $1 不同)
- ``fetch_*`` 统一返回 ``dict`` 行 (列名 -> 值), 上层 Repository 不感知驱动细节
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote_plus, unquote, urlparse

import asyncmy
import structlog
from asyncmy.errors import Error as AsyncmyError
from asyncmy.pool import Pool

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class MySQLConfig:
    """MySQL 连接配置(从 DSN 字符串解析).

    Attributes:
        host: 数据库主机
        port: 端口
        user: 用户名
        password: 密码
        database: 数据库名
        charset: 字符集 (默认 utf8mb4)
    """

    host: str
    port: int
    user: str
    password: str
    database: str
    charset: str = "utf8mb4"

    @classmethod
    def from_dsn(cls, dsn: str, default_db: str = "openagent") -> MySQLConfig:
        """从 DSN 字符串解析: ``mysql://user:pass@host:port/db?charset=utf8mb4``.

        Args:
            dsn: DSN 字符串
            default_db: 没指定 db 时使用

        Returns:
            解析后的 ``MySQLConfig``

        Raises:
            ValueError: DSN 格式非法时
        """
        if not dsn:
            raise ValueError("MySQL DSN is empty")
        if "://" not in dsn:
            raise ValueError(f"Invalid MySQL DSN (missing scheme): {dsn!r}")
        parsed = urlparse(dsn)
        if parsed.scheme not in ("mysql", "mysql+asyncmy"):
            raise ValueError(f"Unsupported MySQL DSN scheme: {parsed.scheme!r}")
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 3306
        user = unquote(parsed.username) if parsed.username else "root"
        password = unquote(parsed.password) if parsed.password else ""
        database = (parsed.path or "").lstrip("/") or default_db
        charset = "utf8mb4"
        if parsed.query:
            for kv in parsed.query.split("&"):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    if k == "charset":
                        charset = v
        return cls(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            charset=charset,
        )

    def to_url_safe(self) -> str:
        """生成无密码 URL(日志/审计用)."""
        return f"mysql://{self.user}@{self.host}:{self.port}/{self.database}"


class MySQLPool:
    """asyncmy 连接池封装.

    用法:
        pool = MySQLPool(MySQLConfig.from_dsn("mysql://..."))
        await pool.init_schema(DDL_SQL)
        async with pool.acquire() as conn:
            await conn.cursor().execute("SELECT 1")
        await pool.close()
    """

    def __init__(
        self,
        config: MySQLConfig,
        *,
        min_size: int = 5,
        max_size: int = 20,
        echo: bool = False,
    ) -> None:
        """初始化连接池配置(不建连).

        Args:
            config: 数据库连接配置
            min_size: 连接池最小尺寸
            max_size: 连接池最大尺寸
            echo: 是否在 DEBUG 日志打印每条 SQL
        """
        self._config = config
        self._min_size = min_size
        self._max_size = max_size
        self._echo = echo
        self._pool: Pool | None = None

    @property
    def config(self) -> MySQLConfig:
        return self._config

    @property
    def is_initialized(self) -> bool:
        return self._pool is not None

    async def connect(self) -> None:
        """建立连接池(幂等)."""
        if self._pool is not None:
            return
        self._pool = await asyncmy.create_pool(
            host=self._config.host,
            port=self._config.port,
            user=self._config.user,
            password=self._config.password,
            db=self._config.database,
            charset=self._config.charset,
            minsize=self._min_size,
            maxsize=self._max_size,
            autocommit=True,
        )
        logger.info(
            "mysql_pool_created",
            url=self._config.to_url_safe(),
            min=self._min_size,
            max=self._max_size,
        )

    async def close(self) -> None:
        """关闭连接池."""
        if self._pool is None:
            return
        self._pool.close()
        await self._pool.wait_closed()
        self._pool = None
        logger.info("mysql_pool_closed", url=self._config.to_url_safe())

    async def init_schema(self, ddl_sql: str) -> None:
        """启动期幂等执行 DDL(v2 schema 全部 IF NOT EXISTS).

        Args:
            ddl_sql: 多语句 DDL, 用 ``;`` 分隔. 拆分逐条执行, 单条失败不影响其他.

        Raises:
            RuntimeError: 未 ``connect()`` 时
        """
        if self._pool is None:
            raise RuntimeError("MySQLPool not connected. Call connect() first.")
        for stmt in _split_ddl(ddl_sql):
            if not stmt.strip():
                continue
            try:
                async with self._pool.acquire() as conn, conn.cursor() as cur:
                    await cur.execute(stmt)
                logger.debug("mysql_ddl_executed", head=stmt[:80])
            except AsyncmyError as e:
                logger.error("mysql_ddl_failed", stmt=stmt[:200], err=str(e))
                raise

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[Any]:
        """获取一个连接(作用域结束自动归还)."""
        if self._pool is None:
            raise RuntimeError("MySQLPool not connected. Call connect() first.")
        async with self._pool.acquire() as conn:
            yield conn

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Any]:
        """事务上下文管理器(异常回滚, 正常提交).

        注意: asyncmy 池连接默认 autocommit=True, 这里显式 begin/commit 包裹.
        """
        if self._pool is None:
            raise RuntimeError("MySQLPool not connected. Call connect() first.")
        async with self._pool.acquire() as conn:
            await conn.begin()
            try:
                yield conn
            except Exception:
                await conn.rollback()
                raise
            else:
                await conn.commit()

    async def execute(self, sql: str, params: tuple[Any, ...] | list[Any] | None = None) -> int:
        """执行非查询 SQL, 返回受影响行数.

        Args:
            sql: SQL 语句(``%s`` 占位符)
            params: 位置参数

        Returns:
            受影响行数 (INSERT/UPDATE/DELETE)
        """
        if self._echo:
            logger.debug("mysql_execute", sql=sql[:200], params=params)
        async with self.acquire() as conn, conn.cursor() as cur:
            return await cur.execute(sql, params or ())

    async def fetch_one(
        self, sql: str, params: tuple[Any, ...] | list[Any] | None = None
    ) -> dict[str, Any] | None:
        """取单行, 返回 ``dict[列名, 值]`` 或 ``None``.

        Args:
            sql: SQL 语句
            params: 位置参数

        Returns:
            单行字典, 无结果返回 ``None``
        """
        if self._echo:
            logger.debug("mysql_fetch_one", sql=sql[:200], params=params)
        async with self.acquire() as conn, conn.cursor() as cur:
            await cur.execute(sql, params or ())
            row = await cur.fetchone()
            if row is None:
                return None
            return _row_to_dict(cur, row)

    async def fetch_all(
        self, sql: str, params: tuple[Any, ...] | list[Any] | None = None
    ) -> list[dict[str, Any]]:
        """取多行, 返回 ``list[dict]``.

        Args:
            sql: SQL 语句
            params: 位置参数

        Returns:
            行字典列表(空表返回空列表)
        """
        if self._echo:
            logger.debug("mysql_fetch_all", sql=sql[:200], params=params)
        async with self.acquire() as conn, conn.cursor() as cur:
            await cur.execute(sql, params or ())
            rows = await cur.fetchall()
            if not rows:
                return []
            return [_row_to_dict(cur, r) for r in rows]


def _row_to_dict(cursor: Any, row: tuple[Any, ...]) -> dict[str, Any]:
    """把 asyncmy 的 ``(values...)`` 行 + ``cursor.description`` 拼成 dict."""
    if not cursor.description:
        return {}
    cols = [d[0] for d in cursor.description]
    return dict(zip(cols, row, strict=False))


def _split_ddl(ddl: str) -> list[str]:
    """DDL 拆分: 先去掉所有 ``--`` 注释行(避免注释里的 ``;`` 被误切), 再按 ``;`` 切.

    仅用于启动期 DDL, 不处理存储过程/触发器里的 ``;`` (我们的 v2 schema 没有).
    """
    # 1) 去注释行 — 避免注释里的 ; 误切
    cleaned_lines = []
    for line in ddl.splitlines():
        # 去掉行内注释, 但保留字符串字面量 (我们的 DDL 没有, 简化处理)
        idx = line.find("--")
        if idx >= 0:
            line = line[:idx]
        cleaned_lines.append(line)
    cleaned = "\n".join(cleaned_lines)

    # 2) 按 ; 切
    out: list[str] = []
    for raw in cleaned.split(";"):
        stmt = raw.strip()
        if stmt:
            out.append(stmt)
    return out


def quote_password(raw: str) -> str:
    """密码里含 ``:`` / ``@`` / ``/`` 时手动 URL 编码(供 .env 用)."""
    return quote_plus(raw)
