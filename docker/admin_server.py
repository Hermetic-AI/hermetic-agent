"""opencode-sandbox 容器内 admin HTTP 服务器 (供 Hub / 运维调).

跑在 :7778, 跟 health_server (:7777) 同一个容器但不同进程.
零依赖 (纯 stdlib http.server), 跟 entrypoint 同一个 Python 工具链.

端点 (dev only, 没鉴权 - 容器在 docker 私有网络里):
- GET  /admin/policy           当前生效的 policy (baked + runtime overlay + env)
- POST /admin/policy           合并更新 policy 字段, 写入 policy.runtime.json
- POST /admin/reload           重新渲染 config.json + SIGTERM opencode (supervisor 自动重启)
- GET  /admin/opencode/status  opencode 进程状态 + 当前 active model
- GET  /admin/healthz          自我健康检查
- GET  /admin/env              当前生效的 env 变量 (注意: 不会返回 secret 值, 只返 key 名)
- POST /admin/env              直接覆盖 env 变量 (写 env.runtime, supervisor 读这个)
- GET  /openapi.json           OpenAPI 3.1 规范 (JSON)
- GET  /docs                    Swagger UI (HTML, 从 CDN 加载)

数据流:
  policy.json  (baked,  ro)        policy.runtime.json  (rw, 容器层, 可删)
              |                              |
              +--- merge (deep, 浅覆深) ---+
                              |
                              v
                     render_config.py
                              |
                              v
                   /root/.config/opencode/config.json (rw, 容器层)
                              |
                              v
                  opencode serve 启动时读 (重启后生效)

env 数据流 (新):
  docker-compose.yml env:OPENAI_API_KEY=xxx  ←  起步
              |
              v
  /opt/sandbox/env.runtime  (rw, 容器层, chmod 600)
              ↑                              ↑
       POST /admin/env                   entrypoint supervisor
              (user 改了)                (source 后启 opencode)

为什么用 overlay 而不是直接改 baked:
  - baked 是 ro bind mount (Dockerfile COPY), 改不动
  - runtime 是容器层, 改完了 docker rm 才清, 持久化在容器内
  - 重 build 镜像后 runtime 不会丢 (新容器从 baked 起步, 之后 runtime 又叠加)
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# 容器内固定路径, 跟 entrypoint.sh 保持一致.
# 注意: baked 路径在 /opt/sandbox (ro, Dockerfile COPY), runtime 路径必须在
# writable 目录 (/tmp/opencode-sandbox, tmpfs) — docker-compose 里 read_only=true
# 锁住 /opt/sandbox, 写进去会 OSError [Errno 30].
POLICY_BAKED_PATH = "/opt/sandbox/policy.json"
POLICY_RUNTIME_PATH = "/tmp/opencode-sandbox/policy.runtime.json"
ENV_RUNTIME_PATH = "/tmp/opencode-sandbox/env.runtime"
CONFIG_OUTPUT_PATH = "/root/.config/opencode/config.json"
RENDER_CONFIG_SCRIPT = "/opt/sandbox/render_config.py"

# Sensitive env keys (secret 值, GET /admin/env 不返值, 只返 key 名)
_SENSITIVE_ENV_KEYS = frozenset({
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "FLIGHT_API_KEY",
    "FLIGHT_API_KEY_HEADER", "X_MCP_TOKEN", "X_CRM_TOKEN",
    "CRM_TOKEN", "PASSWORD", "SECRET", "API_KEY",
})

# opencode 进程 PID 缓存. 容器里 pid 1 之前是 entrypoint.sh (用 exec), 现在改成
# supervisor 循环后 pid 1 仍是 shell, opencode 跑在子进程. 用纯 Python 扫 /proc
# 找最新的 opencode 子进程 (避免依赖 pgrep — 容器里不一定装了 procps).
def _pgrep_python(pattern: str) -> list[int]:
    """简易 pgrep: 扫 /proc, cmdline 用 pattern 匹配 (^ + re 语法)."""
    import re
    rx = re.compile(pattern)
    pids: list[int] = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/cmdline", "rb") as f:
                raw = f.read()
            # cmdline 元素用 NUL (\x00) 分隔; 末位通常也有 NUL, 统一替换成空格
            cmdline = raw.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()
            if rx.search(cmdline):
                pids.append(int(entry))
        except (OSError, ValueError):
            continue
    return sorted(pids)


def _opencode_pid() -> int | None:
    """返回最新启动的 ``opencode serve ...`` 进程 PID. 找不到返 None."""
    pids = _pgrep_python(r"^opencode serve")
    if not pids:
        # 兜底: opencode 跑在 node 包装器里, cmdline 可能以 "node /path/to/opencode ..." 开头
        pids = _pgrep_python(r"opencode serve")
    return pids[-1] if pids else None


def _read_baked_policy() -> dict:
    if not os.path.exists(POLICY_BAKED_PATH):
        return {}
    with open(POLICY_BAKED_PATH, encoding="utf-8") as f:
        return json.load(f)


def _read_runtime_overlay() -> dict:
    if not os.path.exists(POLICY_RUNTIME_PATH):
        return {}
    with open(POLICY_RUNTIME_PATH, encoding="utf-8") as f:
        return json.load(f)


def _read_effective_policy() -> dict:
    """baked (底)  + runtime overlay (顶, 浅覆深)."""
    return _deep_merge(_read_baked_policy(), _read_runtime_overlay())


def _deep_merge(base: dict, overlay: dict) -> dict:
    """把 overlay 的字段浅覆到 base 上. dict 字段递归, list 整体替换."""
    out = dict(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _write_runtime_overlay(overlay: dict) -> None:
    os.makedirs(os.path.dirname(POLICY_RUNTIME_PATH), exist_ok=True)
    with open(POLICY_RUNTIME_PATH, "w", encoding="utf-8") as f:
        json.dump(overlay, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _render_config() -> tuple[bool, str]:
    """调 render_config.py 重渲 config.json. 返 (ok, err_msg)."""
    try:
        result = subprocess.run(
            [
                "python3", RENDER_CONFIG_SCRIPT,
                "--policy", POLICY_RUNTIME_PATH,
                "--output", CONFIG_OUTPUT_PATH,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as e:
        return False, f"render_config not found: {e}"
    if result.returncode != 0:
        return False, (result.stderr or result.stdout).strip()
    return True, ""


def _restart_opencode() -> str:
    """SIGTERM 当前 opencode 子进程. entrypoint.sh 的 supervisor 循环会重启它,
    重启时它读新的 config.json (model 等都生效)."""
    pid = _opencode_pid()
    if pid is None:
        return "no opencode process found"
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return f"opencode pid={pid} already gone"
    return f"sent SIGTERM to opencode pid={pid}"


def _read_env_runtime() -> dict[str, str]:
    """读 /opt/sandbox/env.runtime, 返 {KEY: VALUE}. 格式:
    KEY1=VALUE1
    KEY2="VALUE WITH SPACES"
    # 注释行
    """
    if not os.path.exists(ENV_RUNTIME_PATH):
        return {}
    out: dict[str, str] = {}
    with open(ENV_RUNTIME_PATH, encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if "=" not in s:
                continue
            k, _, v = s.partition("=")
            k = k.strip()
            v = v.strip()
            # 去双引号 (entrypoint supervisor 的 source 会自己处理)
            if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
                v = v[1:-1]
            elif len(v) >= 2 and v[0] == "'" and v[-1] == "'":
                v = v[1:-1]
            if k:
                out[k] = v
    return out


def _validate_env_key(key: str) -> str | None:
    """校验 env var 名称 — 必须是全大写字母 + 数字 + 下划线, 且首字符是字母.

    返 None 表示合法, 返 str 表示错误信息.
    """
    if not key:
        return "empty key"
    if not all(c.isalnum() or c == "_" for c in key):
        return f"key {key!r} must contain only A-Z, 0-9, _ (no lowercase, no spaces)"
    if not key[0].isalpha():
        return f"key {key!r} must start with a letter"
    if key != key.upper():
        return f"key {key!r} must be UPPERCASE (env var convention)"
    return None


def _write_env_runtime(env_map: dict[str, str]) -> None:
    """把 env dict 写为 ``KEY=VALUE`` 格式 (一行一对, chmod 600).

    注意: 写文件时**不**加引号 — entrypoint.sh 用 bash ``source`` 读, 简单
    格式最安全. 含空格 / 特殊字符的值也由 source 自己处理 (POSIX shell
    标准下, 单引号包裹可以保留空格).
    """
    os.makedirs(os.path.dirname(ENV_RUNTIME_PATH), exist_ok=True)
    with open(ENV_RUNTIME_PATH, "w", encoding="utf-8") as f:
        f.write("# Generated by admin_server.py (docker/admin_server.py)\n")
        f.write("# Sourced by entrypoint.sh supervisor before launching opencode serve.\n")
        f.write("# Edits here are picked up on next /admin/reload.\n\n")
        for k, v in env_map.items():
            # key 校验: POSIX env var (UPPERCASE, 数字, 下划线, 字母开头)
            if _validate_env_key(k) is not None:
                continue  # 防御: 不合法 key 静默丢, 真实校验在 do_POST 里报 400
            # 如果值含空格/特殊字符, 用单引号包裹
            if any(c in v for c in " \t\"'$&;|<>(){}"):
                v_escaped = "'" + v.replace("'", "'\\''") + "'"
                f.write(f"{k}={v_escaped}\n")
            else:
                f.write(f"{k}={v}\n")
    # chmod 600 (root only) - 容器已经 root 跑, 收紧权限
    try:
        os.chmod(ENV_RUNTIME_PATH, 0o600)
    except OSError:
        pass


def _is_sensitive(key: str) -> bool:
    k = key.upper()
    if k in _SENSITIVE_ENV_KEYS:
        return True
    for pat in _SENSITIVE_ENV_KEYS:
        if pat in k:
            return True
    return False


class AdminHandler(BaseHTTPRequestHandler):
    """容器内 admin API."""

    def log_message(self, fmt: str, *args) -> None:
        # 默认 access log 太吵, 但我们有时想看 (reload / policy change 事件),
        # 简单点: 把所有请求打到 stderr 方便 docker logs 跟.
        sys.stderr.write("[admin_server] " + (fmt % args) + "\n")
        sys.stderr.flush()

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/admin/healthz":
            return self._json(200, {"status": "ok", "uptime": int(time.time() - _STARTED_AT)})

        if self.path == "/admin/policy":
            baked = _read_baked_policy()
            runtime = _read_runtime_overlay()
            effective = _read_effective_policy()
            return self._json(200, {
                "baked": baked,
                "runtime_overlay": runtime,
                "effective": effective,
                "sources": {
                    "baked_path": POLICY_BAKED_PATH,
                    "runtime_path": POLICY_RUNTIME_PATH,
                    "baked_exists": os.path.exists(POLICY_BAKED_PATH),
                    "runtime_exists": os.path.exists(POLICY_RUNTIME_PATH),
                },
            })

        if self.path == "/admin/env":
            # 返当前 env 变量, 但 secret 值 (key/token/密码) 用 "***" 遮蔽
            env = _read_env_runtime()
            safe: dict[str, object] = {}
            for k, v in env.items():
                if _is_sensitive(k):
                    safe[k] = "***" if v else ""
                else:
                    safe[k] = v
            return self._json(200, {
                "runtime_path": ENV_RUNTIME_PATH,
                "exists": os.path.exists(ENV_RUNTIME_PATH),
                "env": safe,
                "next": "POST /admin/reload to apply (kills opencode, supervisor re-sources env and restarts)",
            })

        if self.path == "/admin/opencode/status":
            pid = _opencode_pid()
            # 读渲染后的 config.json, 抽出 model 字段 (opencode 当前生效的)
            active_model = None
            if os.path.exists(CONFIG_OUTPUT_PATH):
                try:
                    with open(CONFIG_OUTPUT_PATH, encoding="utf-8") as f:
                        active_model = json.load(f).get("model")
                except (OSError, ValueError):
                    pass
            return self._json(200, {
                "opencode_alive": pid is not None,
                "opencode_pid": pid,
                "active_model": active_model,
            })

        if self.path == "/openapi.json":
            return self._serve_openapi()

        if self.path in ("/docs", "/docs/"):
            return self._serve_swagger_ui()

        return self._json(404, {"error": "not_found", "path": self.path})

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/admin/policy":
            body = self._read_body()
            if not isinstance(body, dict):
                return self._json(400, {"error": "body must be JSON object"})
            # 注意: body.env 走专用路径 (/opt/sandbox/env.runtime), 不写进 policy.runtime.json
            env_update = body.pop("env", None)
            # 合并而不是覆盖: 旧 runtime 字段保留, 新字段叠上去, 传 null 删除
            old_overlay = _read_runtime_overlay()
            for k, v in body.items():
                if v is None:
                    old_overlay.pop(k, None)
                else:
                    old_overlay[k] = v
            _write_runtime_overlay(old_overlay)
            response: dict = {
                "ok": True,
                "effective": _read_effective_policy(),
                "next": "POST /admin/reload to apply (kills opencode, supervisor restarts with new config)",
            }
            if env_update is not None:
                # 同时处理 env 字段 (可选). body.env 是 dict[str, str] 或者 null
                if not isinstance(env_update, dict):
                    return self._json(400, {"error": "body.env must be an object"})
                old_env = _read_env_runtime()
                for k, v in env_update.items():
                    if v is None:
                        old_env.pop(k, None)
                    else:
                        old_env[str(k)] = str(v)
                _write_env_runtime(old_env)
                response["env"] = "updated (chmod 600, not echoed back); POST /admin/reload to apply"
            return self._json(200, response)

        if self.path == "/admin/env":
            body = self._read_body()
            if not isinstance(body, dict):
                return self._json(400, {"error": "body must be JSON object"})
            # 严格 key 校验: 拒绝非 POSIX env var 格式 (exists / env / model / apiKey 等)
            invalid = []
            for k in body.keys():
                if not isinstance(k, str):
                    invalid.append(f"key {k!r} is not a string")
                    continue
                err = _validate_env_key(k)
                if err:
                    invalid.append(err)
            if invalid:
                return self._json(400, {
                    "error": "invalid_env_key",
                    "detail": "POST /admin/env body must be a flat dict of {UPPERCASE_KEY: value}",
                    "invalid_keys": invalid,
                    "examples": {
                        "ok": {"OPENAI_API_KEY": "sk-...", "OPENAI_BASE_URL": "https://..."},
                        "wrong": {
                            "exists": "True (lowercase + not env)",
                            "env": {"nested": "object not allowed, flatten it"},
                            "model": "goes in /admin/policy not /admin/env",
                        },
                    },
                })
            old_env = _read_env_runtime()
            for k, v in body.items():
                if v is None:
                    old_env.pop(k, None)
                else:
                    old_env[str(k)] = str(v)
            _write_env_runtime(old_env)
            return self._json(200, {
                "ok": True,
                "wrote": len(old_env),
                "next": "POST /admin/reload to apply (kills opencode, supervisor re-sources env.runtime and restarts)",
            })

        if self.path == "/admin/reload":
            # 1. 重渲 config.json
            ok, err = _render_config()
            if not ok:
                return self._json(500, {
                    "ok": False,
                    "stage": "render_config",
                    "error": err,
                })
            # 2. SIGTERM opencode (supervisor 自动重启)
            restart_msg = _restart_opencode()
            return self._json(200, {
                "ok": True,
                "render": "ok",
                "restart": restart_msg,
                "next": "opencode will restart in ~1s with the new config + env",
            })

        return self._json(404, {"error": "not_found", "path": self.path})

    # ------------------------------------------------------------------
    # OpenAPI / Swagger UI 静态服务
    # ------------------------------------------------------------------

    def _serve_openapi(self) -> None:
        # spec 文件跟 admin_server.py 同目录, 运行时再读 (避免 import 时的 f-string 复杂度)
        here = os.path.dirname(os.path.abspath(__file__))
        spec_path = os.path.join(here, "openapi.json")
        try:
            with open(spec_path, encoding="utf-8") as f:
                spec_bytes = f.read().encode("utf-8")
        except OSError as e:
            return self._json(500, {"error": f"openapi.json not found: {e}"})
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(spec_bytes)))
        # CORS: 容器内服务, 允许 host devtools / 浏览器跨源读
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(spec_bytes)

    def _serve_swagger_ui(self) -> None:
        html = _SWAGGER_HTML
        b = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


_STARTED_AT = time.time()


# Swagger UI 模板 (从 CDN 加载, 容器内无外网时本地 fallback)
# 设计: 直接用 unpkg 的 swagger-ui-dist (单 HTML), 避免 npm 构建
_SWAGGER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>opencode-sandbox admin API</title>
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5.17.14/swagger-ui.css" />
  <style>
    body { margin: 0; padding: 0; }
    .swagger-ui .info { margin: 30px 0; }
    .swagger-ui .info .title { font-size: 28px; }
  </style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5.17.14/swagger-ui-bundle.js" crossorigin></script>
  <script>
    window.onload = () => {
      window.ui = SwaggerUIBundle({
        url: "/openapi.json",
        dom_id: "#swagger-ui",
        deepLinking: true,
        presets: [
          SwaggerUIBundle.presets.apis,
        ],
      });
    };
  </script>
</body>
</html>
"""


def main() -> int:
    port = int(os.environ.get("ADMIN_PORT", "7778"))
    host = os.environ.get("ADMIN_HOST", "0.0.0.0")
    server = ThreadingHTTPServer((host, port), AdminHandler)
    print(f"[admin_server] listening on {host}:{port}", flush=True)
    print(f"[admin_server] baked policy:   {POLICY_BAKED_PATH}", flush=True)
    print(f"[admin_server] runtime overlay: {POLICY_RUNTIME_PATH}", flush=True)
    print(f"[admin_server] config output:  {CONFIG_OUTPUT_PATH}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[admin_server] shutting down", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1:
        try:
            os.environ["ADMIN_PORT"] = str(int(sys.argv[1]))
        except ValueError:
            print(f"usage: {sys.argv[0]} [port]", file=sys.stderr)
            sys.exit(2)
    sys.exit(main())
