"""sandbox.runtime 单元测试 (不依赖真 docker, mock subprocess)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from openagent.sandbox.runtime import (
    AgentState,
    ContainerState,
    DockerNotFound,
    OpencodeNode,
    SandboxError,
    SandboxRuntime,
    SandboxSpec,
    SandboxStartFailed,
)


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


def _make_runtime(docker_bin: str = "docker") -> SandboxRuntime:
    """构造 runtime, mock shutil.which 返回 True (假装有 docker)."""
    with patch("openagent.sandbox.runtime.shutil.which", return_value="/usr/bin/docker"):
        return SandboxRuntime(docker_bin=docker_bin)


def _make_spec(**overrides) -> SandboxSpec:
    defaults = dict(
        image="opencode-sandbox:dev",
        name="opencode-1",
        workspace_host_path="/work/tenant-A/project-1",
        skills_ro_dir="/work/shared/skills",
        policy_file="/work/sandbox/policy.opencode-1.json",
        env={
            "ANTHROPIC_API_KEY": "sk-test-1",
            "OPENAI_API_KEY": "",  # 空值, 期望被跳过
            "OPENAI_BASE_URL": "https://api.deepseek.com/v1",
        },
    )
    defaults.update(overrides)
    return SandboxSpec(**defaults)


# ---------------------------------------------------------------------------
# 初始化
# ---------------------------------------------------------------------------


def test_init_no_docker_raises():
    with patch("openagent.sandbox.runtime.shutil.which", return_value=None):
        with pytest.raises(DockerNotFound):
            SandboxRuntime()


def test_init_with_docker_ok():
    with patch("openagent.sandbox.runtime.shutil.which", return_value="/usr/bin/docker"):
        rt = SandboxRuntime()
        assert rt._docker_bin == "docker"


# ---------------------------------------------------------------------------
# 命令构造 (纯单元, 不调 subprocess)
# ---------------------------------------------------------------------------


def test_build_env_args_skips_empty():
    rt = _make_runtime()
    args = rt._build_env_args({"FOO": "bar", "EMPTY": "", "NONE": None, "ZERO": "0"})
    # 0 不是空, 保留; None/空串跳过
    assert args == ["-e", "FOO=bar", "-e", "ZERO=0"]


def test_build_volume_args_with_all():
    rt = _make_runtime()
    spec = _make_spec()
    args = rt._build_volume_args(spec)
    # 主 workspace (rw) + skill 源 (ro) + policy.json (ro)
    assert any(":/work/tenant-A/project-1" in a for a in args)
    assert any(":/work/shared/skills:ro" in a for a in args)
    assert any(":/opt/sandbox/policy.json:ro" in a for a in args)


def test_build_volume_args_minimal():
    rt = _make_runtime()
    spec = _make_spec(skills_ro_dir=None, policy_file=None)
    args = rt._build_volume_args(spec)
    # 只剩主 workspace
    assert len(args) == 2  # "-v" + value
    assert args[1].count(":") == 1  # 只 source:target, 没有 :ro


def test_build_security_args_includes_cap_drop():
    rt = _make_runtime()
    args = rt._build_security_args()
    assert "--cap-drop" in args
    assert "ALL" in args
    assert "no-new-privileges" in " ".join(args)


# ---------------------------------------------------------------------------
# create_node
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_node_ok():
    rt = _make_runtime()
    spec = _make_spec()

    fake_stdout = b"abc123containerid\n"
    fake_run = AsyncMock(return_value=(fake_stdout, b"", 0))

    with patch.object(rt, "_run", fake_run):
        node = await rt.create_node(spec)

    # 校验返回值
    assert node.id == "opencode-1"
    assert node.container_id == "abc123containerid"
    assert node.container_state == ContainerState.RUNNING
    assert node.agent_state == AgentState.STARTING
    assert node.base_url == "http://opencode-1:14096"
    assert node.health_url == "http://opencode-1:7777/healthz"
    assert node.workspace_host_path == "/work/tenant-A/project-1"

    # 校验调用的 docker 命令
    cmd = fake_run.call_args[0][0]
    assert cmd[0] == "docker"
    assert "run" in cmd
    assert "-d" in cmd
    assert "--read-only" in cmd
    assert "--memory" in cmd
    assert "2g" in cmd
    assert "opencode-sandbox:dev" in cmd[-1]
    # env 注入
    assert any(a == "-e" and v.startswith("ANTHROPIC_API_KEY=") for a, v in zip(cmd, cmd[1:]))
    assert not any("OPENAI_API_KEY=" in v for v in cmd)  # 空值跳过


@pytest.mark.asyncio
async def test_create_node_docker_run_fails():
    rt = _make_runtime()
    spec = _make_spec()
    fake_run = AsyncMock(return_value=(b"", b"port already in use\n", 125))

    with patch.object(rt, "_run", fake_run):
        with pytest.raises(SandboxStartFailed, match="port already in use"):
            await rt.create_node(spec)


# ---------------------------------------------------------------------------
# rm / stop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_node_ok():
    rt = _make_runtime()
    spec = _make_spec()
    node = OpencodeNode(
        id=spec.name,
        name=spec.name,
        image=spec.image,
        container_id="cid",
        base_url="http://opencode-1:14096",
        health_url="http://opencode-1:7777/healthz",
        container_state=ContainerState.RUNNING,
        agent_state=AgentState.READY,
        workspace_host_path=spec.workspace_host_path,
    )
    fake_run = AsyncMock(return_value=(b"cid\n", b"", 0))
    with patch.object(rt, "_run", fake_run):
        await rt.stop_node(node)

    assert node.container_state == ContainerState.EXITED
    assert node.agent_state == AgentState.STOPPED

    cmd = fake_run.call_args[0][0]
    assert cmd[:3] == ["docker", "stop", "--time"]


@pytest.mark.asyncio
async def test_rm_node_stop_first_if_running():
    """rm 时如果还在跑, 先 stop."""
    rt = _make_runtime()
    node = OpencodeNode(
        id="opencode-1",
        name="opencode-1",
        image="opencode-sandbox:dev",
        container_id="cid",
        base_url="http://opencode-1:14096",
        health_url="http://opencode-1:7777/healthz",
        container_state=ContainerState.RUNNING,
        agent_state=AgentState.READY,
        workspace_host_path="/x",
    )
    fake_run = AsyncMock(side_effect=[
        (b"cid\n", b"", 0),  # stop
        (b"cid\n", b"", 0),  # rm
    ])
    with patch.object(rt, "_run", fake_run):
        await rt.rm_node(node)

    assert node.container_state == ContainerState.REMOVED
    assert node.container_id is None
    # 验证调了 stop 然后 rm
    assert len(fake_run.call_args_list) == 2
    assert fake_run.call_args_list[0][0][0][0] == "docker"
    assert fake_run.call_args_list[0][0][0][1] == "stop"
    assert fake_run.call_args_list[1][0][0][1] == "rm"


@pytest.mark.asyncio
async def test_rm_node_already_removed_noop():
    """container_id 是 None (已经被删过), 直接置 REMOVED."""
    rt = _make_runtime()
    node = OpencodeNode(
        id="opencode-1",
        name="opencode-1",
        image="x",
        container_id=None,  # 已经被删
        base_url="x",
        health_url="x",
        container_state=ContainerState.REMOVED,
        agent_state=AgentState.STOPPED,
        workspace_host_path="/x",
    )
    fake_run = AsyncMock()
    with patch.object(rt, "_run", fake_run):
        await rt.rm_node(node)
    fake_run.assert_not_called()  # 不调任何 docker


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_check_ok():
    rt = _make_runtime()
    node = OpencodeNode(
        id="opencode-1",
        name="opencode-1",
        image="x",
        container_id="cid",
        base_url="http://opencode-1:14096",
        health_url="http://opencode-1:7777/healthz",
        container_state=ContainerState.RUNNING,
        agent_state=AgentState.STARTING,
        workspace_host_path="/x",
    )
    fake_run = AsyncMock(return_value=(b'{"status":"ok"}', b"", 0))
    with patch.object(rt, "_run", fake_run):
        ok = await rt.health_check(node)

    assert ok is True
    assert node.agent_state == AgentState.READY
    assert node.last_health_check_ok is True
    assert node.last_error is None


@pytest.mark.asyncio
async def test_health_check_fail():
    rt = _make_runtime()
    node = OpencodeNode(
        id="opencode-1",
        name="opencode-1",
        image="x",
        container_id="cid",
        base_url="http://opencode-1:14096",
        health_url="http://opencode-1:7777/healthz",
        container_state=ContainerState.RUNNING,
        agent_state=AgentState.STARTING,
        workspace_host_path="/x",
    )
    fake_run = AsyncMock(return_value=(b"", b"connection refused\n", 7))
    with patch.object(rt, "_run", fake_run):
        ok = await rt.health_check(node)

    assert ok is False
    assert node.agent_state == AgentState.UNHEALTHY
    assert "connection refused" in (node.last_error or "")


@pytest.mark.asyncio
async def test_health_check_not_running_marks_stopped():
    rt = _make_runtime()
    node = OpencodeNode(
        id="opencode-1",
        name="opencode-1",
        image="x",
        container_id="cid",
        base_url="http://opencode-1:14096",
        health_url="http://opencode-1:7777/healthz",
        container_state=ContainerState.EXITED,  # 已停
        agent_state=AgentState.READY,
        workspace_host_path="/x",
    )
    ok = await rt.health_check(node)  # 不调 _run
    assert ok is False
    assert node.agent_state == AgentState.STOPPED
