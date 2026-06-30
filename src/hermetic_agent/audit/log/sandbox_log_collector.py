"""sandbox_log_collector — opencode 沙箱日志采集基础.

把 opencode 沙箱容器的日志转换为 BusiLog, 写入平台日志通道.

三种采集模式 (按优先级):

1. **Hub 代理** (推荐): Hub 通过 sandbox admin API (``:7778/admin/logs``)
   拉取沙箱日志, 转为 BusiLog 写入 ObjectLogWriter.
2. **沙箱直写**: 沙箱容器直接配置 ``LOG_USE_REDIS_LOG=true``,
   写入同一个 Redis List.
3. **Filebeat 采集**: 沙箱 stdout 输出 JSON 格式日志,
   Filebeat 采集后写入 ELK.

当前实现模式 1 的基础框架. 沙箱 admin API 的 ``/admin/logs`` 端点
需要 opencode 侧配合实现, 本模块提供调用方.

用法::

    from hermetic_agent.audit.log.sandbox_log_collector import collect_sandbox_logs

    await collect_sandbox_logs(
        sandbox_url="http://opencode-1:7778",
        session_id="ses_xxx",
    )
"""
from __future__ import annotations

from typing import Any

import httpx
import structlog

from hermetic_agent.audit.log.busi_logger import get_busi_logger
from hermetic_agent.audit.log.log_markers import LM

logger = structlog.get_logger(__name__)

_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)


async def collect_sandbox_logs(
    sandbox_url: str,
    session_id: str,
    *,
    since: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """从沙箱 admin API 拉取日志, 转为 BusiLog 写入平台通道.

    Args:
        sandbox_url: 沙箱 admin API base URL (例 ``http://opencode-1:7778``).
        session_id: 会话 ID, 用于关联 BusiLog.reqSeqNo.
        since: ISO 时间戳, 只拉取此时间之后的日志.
        limit: 最大拉取条数.

    Returns:
        拉取到的日志条目列表 (已写入平台通道).
    """
    busi = get_busi_logger()
    params: dict[str, Any] = {"session_id": session_id, "limit": limit}
    if since:
        params["since"] = since

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{sandbox_url}/admin/logs", params=params)
            resp.raise_for_status()
            entries = resp.json()
    except httpx.HTTPStatusError as e:
        logger.warning(
            LM.SANDBOX_LOG,
            sandbox_url=sandbox_url,
            status=e.response.status_code,
            error=str(e),
        )
        return []
    except Exception as e:
        logger.warning(
            LM.SANDBOX_LOG,
            sandbox_url=sandbox_url,
            error=str(e),
        )
        return []

    if not isinstance(entries, list):
        entries = entries.get("logs", []) if isinstance(entries, dict) else []

    for entry in entries:
        if busi:
            busi.info(
                LM.SANDBOX_LOG,
                session_id=session_id,
                source=_extract_source(sandbox_url),
                level=str(entry.get("level", "INFO")),
                message=str(entry.get("message", "")),
                event=str(entry.get("event", "")),
            )

    logger.debug(
        LM.SANDBOX_LOG,
        sandbox_url=sandbox_url,
        session_id=session_id,
        count=len(entries),
    )
    return entries


async def check_sandbox_health(sandbox_url: str) -> bool:
    """检查沙箱健康状态.

    Args:
        sandbox_url: 沙箱 admin API base URL.

    Returns:
        True 如果健康, False 否则.
    """
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{sandbox_url}/healthz")
            return resp.status_code == 200
    except Exception as e:
        logger.warning(
            LM.SANDBOX_HEALTH,
            sandbox_url=sandbox_url,
            error=str(e),
        )
        return False


def _extract_source(sandbox_url: str) -> str:
    """从 URL 提取沙箱名称 (例 ``http://opencode-1:7778`` → ``opencode-1``)."""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(sandbox_url)
        return parsed.hostname or "unknown"
    except Exception:
        return "unknown"
