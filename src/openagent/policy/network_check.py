"""URL 网络白名单 — L5 Infrastructure Layer.

三档:
  - off   : 任何 URL 都不允许
  - local : 只允许私有 IP (RFC1918 + loopback + IPv6 UL/fc00)
  - any   : 允许所有 (仅在 tool_level=full 下使用)
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

# 端口元组: local 模式下也允许的常用出网目标 (DNS / local services)
_ALLOWED_LOCAL_PORTS = frozenset({80, 443, 53, 8080, 8443, 3000, 5000, 5432, 6379})


def _extract_host(url: str) -> str | None:
    """从 url 拿到 host (小写). 失败返回 None."""
    try:
        parsed = urlparse(url)
    except (ValueError, TypeError):
        return None
    return parsed.hostname.lower() if parsed.hostname else None


def _is_local_ip(host: str) -> bool:
    """host 是否是 loopback / 私有 IP (v4 + v6)."""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # 不是 IP 字面量, 当 hostname (如 `localhost`, `db.local`).
        # 保守起见: localhost 算 local, 其他 FQDN 算 public.
        return host in ("localhost", "ip6-localhost", "ip6-loopback")

    if isinstance(ip, ipaddress.IPv4Address):
        # 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 127.0.0.0/8
        return (
            ip.is_loopback
            or ip.is_private
            or ip.is_link_local
            or ip.is_reserved
        )
    # IPv6
    # ::1 / 64:ff9b::/96 / 100::/64 / 2001::/23 / fc00::/7 / fe80::/10
    return ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved


def is_url_allowed(url: str, network_level: str = "off") -> tuple[bool, str]:
    """判定 url 是否被 network_level 允许.

    返回 (allowed, reason). reason 是简短的中英说明, 便于日志 / 错误展示.
    """
    if network_level == "off":
        return False, "network=off blocks all URLs"

    if not url or not url.strip():
        return False, "empty url"

    host = _extract_host(url)
    if host is None:
        return False, f"cannot parse host from url: {url!r}"

    if network_level == "any":
        return True, "network=any allows everything"

    if network_level == "local":
        if not _is_local_ip(host):
            return False, f"host {host!r} is not a local/private IP"
        return True, f"host {host!r} is local"

    return False, f"unknown network level: {network_level!r}"


__all__ = [
    "is_url_allowed",
]
