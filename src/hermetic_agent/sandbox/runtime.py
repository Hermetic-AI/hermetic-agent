"""L4.5 sandbox runtime — Docker CLI 包装.

跟设计 (agent-sandbox-overview.md §1.4 / agent-sandbox-runtime-design.md §6.2) 一致:
- 1 docker 容器 = 1 opencode 节点
- Hub 端用 subprocess 调 ``docker run`` / ``docker stop`` / ``docker rm``
- 不引第三方 sandbox wrapper, 走原生 Docker CLI (v0.4 转向)

MVP 范围 (Phase 1):
- ``create_node``: docker run 起一个 opencode 容器, 返回 OpencodeNode (含 container_id)
- ``stop_node``: docker stop, 容器层保留
- ``rm_node``: docker rm, 容器层清 (workspace 还在, host bind mount)
- ``inspect_health``: docker inspect + curl :7777/healthz 探活

Phase 2+:
- 集群 (env OPENCODE_NODES 多节点)
- sticky_session 路由 (SessionTable)
- 4 种 RoutingStrategy
- heartbeat_loop 周期探活
- port forwarding
- clone mode

接口稳定: ``OpencodeNode`` 跟设计文档 dataclass 字段对齐, 后面只加字段不改名.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import shutil
import time
from dataclasses import dataclass, field
from enum import Enum

# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class SandboxError(Exception):
    """沙箱运行时错误基类."""


class DockerNotFound(SandboxError):
    """docker CLI 找不到 (PATH 没装, 或 PATH 缺 docker)."""


class SandboxStartFailed(SandboxError):
    """docker run 失败 (image 不存在, 端口冲突, mount 错等)."""


class SandboxNotRunning(SandboxError):
    """docker stop / docker rm 失败 — 容器已不在."""


# ---------------------------------------------------------------------------
# 状态枚举
# ---------------------------------------------------------------------------


class ContainerState(str, Enum):
    """容器 docker ps 状态 (跟 docker inspect .State.Status 对齐)."""

    CREATED = "created"
    RUNNING = "running"
    RESTARTING = "restarting"
    PAUSED = "paused"
    EXITED = "exited"
    DEAD = "dead"
    REMOVED = "removed"  # 不在 docker 状态机里, 我们自己加的"已删除"


class AgentState(str, Enum):
    """opencode 进程层状态 (跟 health_server /healthz 对齐)."""

    STARTING = "starting"  # 容器起了, opencode 还没好
    READY = "ready"  # opencode serve :14096 通了
    EXECUTING = "executing"  # 正在跑 chat (可省, Phase 2 加)
    UNHEALTHY = "unhealthy"  # healthz 连续 3 次 503
    STOPPED = "stopped"


# ---------------------------------------------------------------------------
# 数据类
# ---------------------------------------------------------------------------


@dataclass
class SandboxSpec:
    """启动一个沙箱节点需要的规格.

    跟 agent-sandbox-overview.md §1.4 / 设计 §3.1 对齐. Phase 1 只用最小集.

    所有 *_port / *_limit / network 默认值都从 settings 读
    (sandbox_network / sandbox_mem_limit / sandbox_cpu_limit /
    sandbox_pids_limit / sandbox_health_port / sandbox_opencode_port).
    这里保留 dataclass 字段级默认值 (字面量) 作为**兜底**, 让 dataclass
    实例化在 settings 不可用时仍工作.
    """

    image: str  # e.g. "opencode-sandbox:dev"
    name: str  # e.g. "opencode-1"
    workspace_host_path: str  # e.g. "/work/tenant-A/project-1"
    skills_ro_dir: str | None = None  # e.g. "/work/shared/skills"
    policy_file: str | None = None  # ro bind 进容器 /opt/sandbox/policy.json
    network: str = "hermetic_agent-sandbox-net"  # 跟 hub 共享的 bridge network
    mem_limit: str = "2g"
    cpu_limit: float = 2.0
    pids_limit: int = 128
    health_port: int = 7777
    opencode_port: int = 14096
    # env 透传 (LLM key 之类). 不写日志, 不进返回值.
    env: dict[str, str] = field(default_factory=dict)


def _sandbox_settings() -> tuple[str, str, float, int, int, int, float, int] | None:
    """从 settings 读 sandbox 默认值, 失败返回 None.

    返回 (network, mem_limit, cpu_limit, pids_limit, health_port,
    opencode_port, health_check_timeout, health_check_retries).
    """
    try:
        from hermetic_agent.config.settings import get_settings

        s = get_settings()
        return (
            s.sandbox_network,
            s.sandbox_mem_limit,
            s.sandbox_cpu_limit,
            s.sandbox_pids_limit,
            s.sandbox_health_port,
            s.sandbox_opencode_port,
            s.sandbox_health_check_timeout,
            s.sandbox_health_check_retries,
        )
    except Exception:  # pragma: no cover
        return None


@dataclass
class OpencodeNode:
    """一个 sandbox 节点 (1 个 docker 容器). 字段跟设计文档 §3.1 对齐."""

    id: str  # "opencode-1" (跟容器名一致)
    name: str  # docker container name
    image: str
    container_id: str | None  # docker run 返回的长 id
    base_url: str  # http://opencode-1:14096 (同网络内用 hostname, 不走 127.0.0.1)
    health_url: str  # http://opencode-1:7777/healthz
    container_state: ContainerState
    agent_state: AgentState
    workspace_host_path: str
    created_at: float = field(default_factory=time.time)
    last_health_check_at: float | None = None
    last_health_check_ok: bool | None = None
    last_error: str | None = None

    def is_healthy(self) -> bool:
        """粗粒度判断: 容器在跑 + agent 状态 ready/unhealthy (没死透)."""
        return self.container_state == ContainerState.RUNNING and self.agent_state in (
            AgentState.READY,
            AgentState.EXECUTING,
        )


# ---------------------------------------------------------------------------
# 运行时
# ---------------------------------------------------------------------------


class SandboxRuntime:
    """Sandbox 运行时 (Phase 1 单机版).

    包装 docker CLI 调用. 不持久化, 不并发, 适合 Hub 启动时 init.

    DOCKER_BIN / HEALTH_CHECK_TIMEOUT / HEALTH_CHECK_RETRIES / 默认 network
    全部从 settings 读 (docker_bin / sandbox_health_check_timeout /
    sandbox_health_check_retries / sandbox_network). 类属性保留作为兜底.
    """

    DOCKER_BIN_FALLBACK: str = "docker"
    HEALTH_CHECK_TIMEOUT_FALLBACK: float = 2.0
    HEALTH_CHECK_RETRIES_FALLBACK: int = 3

    # 向后兼容: 老代码 ``SandboxRuntime.DOCKER_BIN`` 仍可用 (兜底值).
    DOCKER_BIN: str = DOCKER_BIN_FALLBACK
    HEALTH_CHECK_TIMEOUT: float = HEALTH_CHECK_TIMEOUT_FALLBACK
    HEALTH_CHECK_RETRIES: int = HEALTH_CHECK_RETRIES_FALLBACK

    def __init__(
        self,
        docker_bin: str | None = None,
        network: str | None = None,
    ) -> None:
        sb = _sandbox_settings()
        if docker_bin is not None:
            self._docker_bin = docker_bin
        else:
            env_override = os.environ.get("DOCKER_BIN")
            if env_override:
                self._docker_bin = env_override
            else:
                try:
                    from hermetic_agent.config.settings import get_settings
                    self._docker_bin = get_settings().docker_bin
                except Exception:  # pragma: no cover
                    self._docker_bin = self.DOCKER_BIN_FALLBACK
        if network is not None:
            self._network = network
        else:
            self._network = (
                sb[0] if sb is not None else "hermetic_agent-sandbox-net"
            )
        if not shutil.which(self._docker_bin):
            raise DockerNotFound(
                f"docker CLI not found: {self._docker_bin!r}. "
                f"Install Docker Desktop / docker-ce, or set DOCKER_BIN env."
            )

    # ---------- 节点生命周期 ----------

    async def create_node(self, spec: SandboxSpec) -> OpencodeNode:
        """docker run 起一个 opencode 容器.

        Phase 1 简化: 不做 docker create + docker start 两步, 直接 -d run.
        Phase 2 再拆 create / start 分离 (per 设计 §3.1).
        """
        if spec.network != self._network:
            # 不强求, 但要 warn (hub 跟 node 不在同网络就 ping 不通)
            pass

        env_args = self._build_env_args(spec.env)
        volume_args = self._build_volume_args(spec)
        port_args = self._build_port_args(spec)
        security_args = self._build_security_args()

        cmd = [
            self._docker_bin, "run", "-d",
            "--name", spec.name,
            "--hostname", spec.name,
            "--network", spec.network,
            "--read-only",
            "--tmpfs", "/tmp:size=200m,mode=1777",
            "--memory", spec.mem_limit,
            "--cpus", str(spec.cpu_limit),
            "--pids-limit", str(spec.pids_limit),
            *security_args,
            *env_args,
            *volume_args,
            *port_args,
            spec.image,
        ]
        # 不传 command — 镜像 ENTRYPOINT 走 entrypoint.sh

        stdout, stderr, rc = await self._run(cmd, timeout=60)
        if rc != 0:
            raise SandboxStartFailed(
                f"docker run failed (rc={rc}): {stderr.decode(errors='replace').strip()}"
            )
        container_id = stdout.decode().strip()
        return OpencodeNode(
            id=spec.name,
            name=spec.name,
            image=spec.image,
            container_id=container_id,
            base_url=f"http://{spec.name}:{spec.opencode_port}",
            health_url=f"http://{spec.name}:{spec.health_port}/healthz",
            container_state=ContainerState.RUNNING,
            agent_state=AgentState.STARTING,
            workspace_host_path=spec.workspace_host_path,
        )

    async def stop_node(self, node: OpencodeNode) -> None:
        """docker stop (优雅, 等 opencode 收 SIGTERM 自己退).

        stop 保留容器层 (skill / history / installed packages), rm 才清.
        """
        if not node.container_id:
            raise SandboxNotRunning(f"node {node.id!r} has no container_id (was rm'd?)")
        cmd = [self._docker_bin, "stop", "--time", "10", node.container_id]
        _, stderr, rc = await self._run(cmd, timeout=20)
        if rc != 0:
            raise SandboxNotRunning(
                f"docker stop failed for {node.id}: {stderr.decode(errors='replace').strip()}"
            )
        node.container_state = ContainerState.EXITED
        node.agent_state = AgentState.STOPPED

    async def rm_node(self, node: OpencodeNode) -> None:
        """docker rm (清容器层, host workspace 不动 — workspace 是 bind mount).

        rm 前如果还在跑, 先 stop (避免 "container is running" 错).
        """
        if not node.container_id:
            node.container_state = ContainerState.REMOVED
            return
        if node.container_state == ContainerState.RUNNING:
            await self.stop_node(node)
        cmd = [self._docker_bin, "rm", node.container_id]
        _, stderr, rc = await self._run(cmd, timeout=10)
        if rc != 0:
            out = stderr.decode(errors="replace").strip()
            if "No such container" in out:
                # 已经被人手动删了, 接受
                pass
            else:
                raise SandboxNotRunning(f"docker rm failed for {node.id}: {out}")
        node.container_state = ContainerState.REMOVED
        node.container_id = None

    # ---------- 探活 ----------

    async def health_check(self, node: OpencodeNode) -> bool:
        """单次 /healthz 探活. 用 docker exec 避免跨网络 (容器间网络可能未就绪)."""
        if node.container_state != ContainerState.RUNNING or not node.container_id:
            node.agent_state = AgentState.STOPPED
            return False
        # 单次 /healthz 超时 (秒). 优先 settings, 兜底类常量.
        sb = _sandbox_settings()
        hc_timeout = (
            sb[6] if sb is not None else self.HEALTH_CHECK_TIMEOUT_FALLBACK
        )
        cmd = [
            self._docker_bin, "exec", node.container_id,
            "curl", "-fsS", "--max-time", str(int(hc_timeout)),
            f"http://127.0.0.1:{_node_health_port(node)}/healthz",
        ]
        _, stderr, rc = await self._run(cmd, timeout=hc_timeout + 2)
        ok = rc == 0
        node.last_health_check_at = time.time()
        node.last_health_check_ok = ok
        if ok:
            node.agent_state = AgentState.READY
        else:
            err = stderr.decode(errors="replace").strip()[:200]
            node.last_error = err or f"healthz rc={rc}"
            node.agent_state = AgentState.UNHEALTHY
        return ok

    # ---------- 内部: 命令构造 ----------

    def _build_env_args(self, env: dict[str, str]) -> list[str]:
        """构造 docker run 的 ``-e KEY=VAL`` 参数列表.

        P0 安全加固: Docker CLI 通过 argv 接收 ``-e KEY=VAL``, 不会走 shell,
        但 ``VAL`` 含 ``\n`` / 控制字符时仍可能误导 docker / runtime. 这里
        用 ``shlex.quote`` 包裹 VALUE, 拒绝含 shell metacharacter 的
        字符串 (注意: 进程 env 实际不解析, 只是保守起见, 避免 value 里
        含 ``;`` / ``$`` / 反引号等意外被下游 process 解释).
        """
        out: list[str] = []
        for k, v in env.items():
            if not v:
                continue  # 空值不传, 跟 design 一致 (Phase 1 简化)
            # 校验 key 只能含 [A-Za-z0-9_]; 拒绝含 =,空格,;,$ 等
            if not k.replace("_", "").isalnum():
                logger.warning(
                    "sandbox_env_key_invalid (key=%s, hint=env keys must match [A-Za-z0-9_]+)",
                    k,
                )
                continue
            # VALUE 用 shlex.quote 包裹; 未来如果 env 含空格/特殊字符,
            # 至少能在 docker CLI argv 层安全传递.
            quoted = shlex.quote(v)
            out += ["-e", f"{k}={quoted}"]
        return out

    def _build_volume_args(self, spec: SandboxSpec) -> list[str]:
        out: list[str] = []
        # 主 workspace (rw, host 绝对路径 bind 到同路径 — 设计 §3.3 v0.3 关键)
        out += ["-v", f"{spec.workspace_host_path}:{spec.workspace_host_path}"]
        # skill 源 (ro)
        if spec.skills_ro_dir:
            out += ["-v", f"{spec.skills_ro_dir}:/work/shared/skills:ro"]
        # policy.json (ro, 由 Hub 渲染)
        if spec.policy_file:
            out += ["-v", f"{spec.policy_file}:/opt/sandbox/policy.json:ro"]
        return out

    def _build_port_args(self, spec: SandboxSpec) -> list[str]:
        # 同 docker network 内部互通, 不需要 publish 到 host
        # (hub 在 sandbox-net 内, 直接用 hostname 访问)
        return [
            "--expose", str(spec.opencode_port),
            "--expose", str(spec.health_port),
        ]

    def _build_security_args(self) -> list[str]:
        return [
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
        ]

    async def _run(self, cmd: list[str], timeout: float) -> tuple[bytes, bytes, int]:
        """subprocess 跑 docker CLI. 返回 (stdout, stderr, rc)."""
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise SandboxError(f"docker cmd timeout: {' '.join(shlex.quote(c) for c in cmd[:6])}...")
        return stdout, stderr, proc.returncode if proc.returncode is not None else -1


def _node_health_port(node: OpencodeNode) -> int:
    """从 health_url 解析端口. 走 http://host:port/healthz.

    port 缺失时从 settings.sandbox_health_port 读, 兜底 7777.
    """
    from urllib.parse import urlparse

    p = urlparse(node.health_url)
    if p.port is not None:
        return p.port
    sb = _sandbox_settings()
    if sb is not None:
        return sb[4]
    return 7777


__all__ = [
    "SandboxError",
    "DockerNotFound",
    "SandboxStartFailed",
    "SandboxNotRunning",
    "ContainerState",
    "AgentState",
    "SandboxSpec",
    "OpencodeNode",
    "SandboxRuntime",
]
