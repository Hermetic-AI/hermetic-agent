"""logCompress — 仿照 fh-ai app/commons/log/logCompress.

阈值常量 :data:`THRESHOLD_BYTES` = 20 * 1024.

>20KB 的 ``logInfo`` 做 gzip+base64 压缩, 置 ``compress=True``,
``infoSize`` 保留**原始字节数**. 平台消费侧: ``base64.b64decode →
gzip.decompress → utf-8``.
"""
from __future__ import annotations

import base64
import gzip

THRESHOLD_BYTES: int = 20 * 1024


def maybe_compress(log_info: str | None) -> tuple[str | None, int, bool]:
    """如果 ``logInfo > 20KB``, gzip+base64. 否则原样返回.

    Returns:
        ``(content_or_b64, info_size_original, compress_flag)``
    """
    if log_info is None:
        return None, 0, False
    raw = log_info.encode("utf-8")
    if len(raw) <= THRESHOLD_BYTES:
        return log_info, len(raw), False
    encoded = base64.b64encode(gzip.compress(raw)).decode("ascii")
    return encoded, len(raw), True


def maybe_decompress(content: str | None, compress: bool) -> str | None:
    """平台消费侧: 解压. Hub 端用不到, 但放这里方便测试."""
    if content is None or not compress:
        return content
    return gzip.decompress(base64.b64decode(content.encode("ascii"))).decode("utf-8")
