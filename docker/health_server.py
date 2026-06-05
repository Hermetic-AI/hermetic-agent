"""容器内 /healthz HTTP 服务器 (供 Hub 探活).

跟 opencode serve 进程独立, 跑在 :7777.

健康检查契约:
- 200 OK  → 容器内 opencode 进程在, 可服务
- 503    → opencode 进程死了, 但容器还活着
- 进程挂掉 → docker healthcheck 连续失败, Hub 标 unhealthy

为什么不用 opencode serve 自己的 /health?
  opencode serve 在 :14096 暴露的是业务端口. 如果 opencode 挂掉,
  Hub 探 :14096 失败跟探 :7777 失败是一个效果, 但 :7777 独立
  进程能多给一个信号: "opencode 死了但容器还活着" (返回 503).

实现: 纯 Python http.server, 零依赖, 跟 opencode 进程同生命周期.
"""

from __future__ import annotations

import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _env_bool(key: str, default: bool) -> bool:
    val = os.environ.get(key, "").strip().lower()
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("0", "false", "no", "off"):
        return False
    return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, "").strip())
    except (TypeError, ValueError):
        return default


# 启动时间 (用于上报 uptime)
_STARTED_AT = time.time()

# opencode serve 进程状态 (通过 /proc 检测, 简单可靠)
def _opencode_alive() -> bool:
    """检查 opencode serve 进程是否在跑.

    简化版: 查 :14096 端口 listen 状态. 更可靠的版本是读 pidfile,
    但容器内 entrypoint 直接 exec opencode, 没单独的 pid file.

    host 用 OPENCODE_HOST (默认 0.0.0.0, 但 0.0.0.0 主动 connect 会被拒,
    所以这里用 127.0.0.1 强制走 loopback 探活 — health_server 跟 opencode 同容器).
    """
    import socket

    port = _env_int("OPENCODE_PORT", 14096)
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


class HealthHandler(BaseHTTPRequestHandler):
    """/healthz → 200 (opencode 活着) / 503 (opencode 死了)."""

    def do_GET(self) -> None:  # noqa: N802 — stdlib naming
        if self.path != "/healthz":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'{"error":"not_found","path":"' + self.path.encode() + b'"}')
            return

        opencode_alive = _opencode_alive()
        body = {
            "status": "ok" if opencode_alive else "degraded",
            "opencode_alive": opencode_alive,
            "uptime_seconds": int(time.time() - _STARTED_AT),
            "pid": os.getpid(),
        }
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(200 if opencode_alive else 503)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args) -> None:
        # 静默 stdout 日志 (entrypoint 已经有自己的日志)
        # 想看 health 访问日志: 把 stderr 写到 .health-access.log
        return


def main() -> int:
    port = _env_int("HEALTH_PORT", 7777)
    host = os.environ.get("HEALTH_HOST", "0.0.0.0")
    server = ThreadingHTTPServer((host, port), HealthHandler)
    print(f"[health_server] listening on {host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[health_server] shutting down", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    # 允许: python3 /opt/sandbox/health_server.py [port]
    if len(sys.argv) > 1:
        try:
            os.environ["HEALTH_PORT"] = str(int(sys.argv[1]))
        except ValueError:
            print(f"usage: {sys.argv[0]} [port]", file=sys.stderr)
            sys.exit(2)
    sys.exit(main())
