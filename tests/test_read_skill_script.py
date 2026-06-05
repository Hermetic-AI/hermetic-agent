"""tests/test_read_skill_script.py — docker/read_skill.py 单元测试 (v2 持久循环).

read_skill.py 是个 persistent JSON-line MCP server: opencode spawn 一次,
之后每条请求走 stdin 一行, 回 stdout 一行. 测试用 subprocess 模拟.

环境变量: 通过 ``READ_SKILL_ROOT`` 覆盖默认的 /work/shared/skills.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.resolve()
SCRIPT = REPO_ROOT / "docker" / "read_skill.py"


class SkillServer:
    """启动 read_skill.py 子进程, 提供 send()/recv() 同步方法.

    模拟 opencode MCP local 协议: 子进程常驻, 通过 stdin/stdout 收发
    JSON-lines.
    """

    def __init__(self, skill_root: Path) -> None:
        env = os.environ.copy()
        env["READ_SKILL_ROOT"] = str(skill_root)
        self.proc = subprocess.Popen(
            [sys.executable, str(SCRIPT)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(REPO_ROOT),
            env=env,
            text=True,
            bufsize=1,  # line-buffered
            encoding="utf-8",  # 避免 Windows GBK 编码问题 (中文 SKILL 内容)
            errors="replace",
        )
        # 等子进程启动 log ("[read_skill] starting persistent MCP loop")
        # 这条信息没 \n, 但 stderr 是无缓冲的, 启动后会立刻 flush.
        # 实际不阻塞业务; 直接开始 send/recv.

    def send(self, payload: dict) -> dict:
        line = json.dumps(payload, ensure_ascii=False)
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(line + "\n")
        self.proc.stdin.flush()
        # 读一行 stdout. 脚本是 line-buffered, 应该立即可读.
        response_line = self.proc.stdout.readline()
        if not response_line:
            stderr = self.proc.stderr.read() if self.proc.stderr else ""
            raise AssertionError(
                f"server closed stdout unexpectedly; stderr: {stderr}"
            )
        return json.loads(response_line)

    def close(self) -> None:
        if self.proc.stdin and not self.proc.stdin.closed:
            self.proc.stdin.close()
        try:
            self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()


@pytest.fixture
def skill_root(tmp_path: Path) -> Path:
    """建一个临时 skill 树:
    <tmp>/flight-query-v3/SKILL.md
    <tmp>/flight-query-v3/fragments/detail.md
    <tmp>/flight-query-v3/flight-query-v3.iata_icao_codes/SKILL.md
    """
    p = tmp_path / "flight-query-v3"
    p.mkdir()
    (p / "SKILL.md").write_text("# MAIN\nflight-query-v3 core", encoding="utf-8")
    (p / "fragments").mkdir()
    (p / "fragments" / "detail.md").write_text("FRAGMENT-DETAIL", encoding="utf-8")
    sub = p / "flight-query-v3.iata_icao_codes"
    sub.mkdir()
    (sub / "SKILL.md").write_text("# IATA/ICAO\nBJS=北京 SHA=上海", encoding="utf-8")
    return tmp_path


# ----- tests --------------------------------------------------------------


def test_persistent_loop_handles_multiple_requests(skill_root: Path) -> None:
    """v2 关键不变量: 子进程不退, 同一连接处理 N 条请求."""
    srv = SkillServer(skill_root)
    try:
        r1 = srv.send({"name": "flight-query-v3"})
        assert r1["ok"] is True
        assert "MAIN" in r1["content"]

        r2 = srv.send({"name": "flight-query-v3", "fragment": "detail"})
        assert r2["ok"] is True
        assert r2["content"] == "FRAGMENT-DETAIL"

        r3 = srv.send({"name": "flight-query-v3.iata_icao_codes"})
        assert r3["ok"] is True
        assert "BJS=北京" in r3["content"]

        # 进程应还活着 (没中途退出)
        assert srv.proc.poll() is None
    finally:
        srv.close()


def test_missing_name_returns_hint(skill_root: Path) -> None:
    srv = SkillServer(skill_root)
    try:
        out = srv.send({})
        assert out["ok"] is False
        assert out["error_code"] == "MISSING_NAME"
        assert srv.proc.poll() is None  # server 仍存活
    finally:
        srv.close()


def test_skill_not_found(skill_root: Path) -> None:
    srv = SkillServer(skill_root)
    try:
        out = srv.send({"name": "nonexistent"})
        assert out["ok"] is False
        assert out["error_code"] == "SKILL_NOT_FOUND"
    finally:
        srv.close()


def test_full_body(skill_root: Path) -> None:
    srv = SkillServer(skill_root)
    try:
        out = srv.send({"name": "flight-query-v3"})
        assert out["ok"] is True
        assert "flight-query-v3 core" in out["content"]
        assert "MAIN" in out["content"]
    finally:
        srv.close()


def test_sub_skill_via_dot(skill_root: Path) -> None:
    """P0-2: 形如 "parent.sub" 的 skill 名解析到嵌套路径."""
    srv = SkillServer(skill_root)
    try:
        out = srv.send({"name": "flight-query-v3.iata_icao_codes"})
        assert out["ok"] is True
        assert "BJS=北京" in out["content"]
    finally:
        srv.close()


def test_fragment_loaded(skill_root: Path) -> None:
    srv = SkillServer(skill_root)
    try:
        out = srv.send({"name": "flight-query-v3", "fragment": "detail"})
        assert out["ok"] is True
        assert out["fragment"] == "detail"
        assert out["content"] == "FRAGMENT-DETAIL"
    finally:
        srv.close()


def test_fragment_not_found(skill_root: Path) -> None:
    srv = SkillServer(skill_root)
    try:
        out = srv.send({"name": "flight-query-v3", "fragment": "nope"})
        assert out["ok"] is False
        assert out["error_code"] == "FRAGMENT_NOT_FOUND"
        assert "nope.md" in out["expected_path"]
    finally:
        srv.close()


def test_invalid_json_line_returns_error(skill_root: Path) -> None:
    """v2: server 收到非法 JSON 不崩, 返 error 让 opencode 收到结果."""
    srv = SkillServer(skill_root)
    try:
        # 直接往 stdin 写一行垃圾
        assert srv.proc.stdin
        srv.proc.stdin.write("not valid json\n")
        srv.proc.stdin.flush()
        line = srv.proc.stdout.readline()
        out = json.loads(line)
        assert out["ok"] is False
        assert out["error_code"] == "INVALID_JSON"
        # server 仍存活
        assert srv.proc.poll() is None
    finally:
        srv.close()


def test_real_workdir_flight_query_v3_loads() -> None:
    """端到端: 用项目真实的 work/shared/skills 跑一次, 验证 main 分支."""
    real_root = REPO_ROOT / "work" / "shared" / "skills"
    if not real_root.is_dir():
        pytest.skip("work/shared/skills not present")
    srv = SkillServer(real_root)
    try:
        out = srv.send({"name": "flight-query-v3"})
        assert out["ok"] is True
        assert "queryFlightBasic" in out["content"]
    finally:
        srv.close()
