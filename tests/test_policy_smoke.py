"""L5 Policy Engine 关键场景冒烟测试.

跑通 5 个最关键场景:
  1. 路径白名单 (workspace 内允许, 外拒绝, .env 永远拒绝)
  2. 命令白/黑名单 (rm -rf 拒绝, 标准命令允许)
  3. 网络三档 (off / local / any)
  4. merge 收紧不能放松
  5. 审计脱敏
"""

from __future__ import annotations

import os

import pytest

from hermetic_agent.policy.audit import InMemoryAuditLogger, redact_path
from hermetic_agent.policy.engine import EffectivePolicy, PolicyEngine, merge
from hermetic_agent.policy.errors import (
    CommandNotAllowed,
    NetworkNotAllowed,
    PathNotAllowed,
)


def test_smoke_1_path_whitelist(tmp_path) -> None:
    """1. 路径白名单."""
    ws = str(tmp_path / "project")
    os.makedirs(ws, exist_ok=True)
    good = os.path.join(ws, "src", "main.py")
    os.makedirs(os.path.dirname(good), exist_ok=True)
    with open(good, "w") as f:
        f.write("x")

    p = EffectivePolicy(workspace_dirs=[ws], deny_dirs=[])
    engine = PolicyEngine(policy=p, audit=InMemoryAuditLogger())

    # workspace 内文件 OK
    assert engine.check_path(good) is True

    # .env 永远拒绝
    env = os.path.join(ws, ".env")
    with open(env, "w") as f:
        f.write("SECRET=x")
    with pytest.raises(PathNotAllowed):
        engine.check_path(env)

    # workspace 外拒绝
    with pytest.raises(PathNotAllowed):
        engine.check_path("/etc/passwd")


def test_smoke_2_command_allow_deny() -> None:
    """2. 命令白/黑名单."""
    p = EffectivePolicy(
        tool_level="standard",
        allowed_commands=["ls", "cat", "git"],
        denied_commands=["rm -rf", "sudo", "dd"],
    )
    engine = PolicyEngine(policy=p, audit=InMemoryAuditLogger())

    assert engine.check_command("ls -la") is True
    assert engine.check_command("git status") is True
    with pytest.raises(CommandNotAllowed):
        engine.check_command("rm -rf /")
    with pytest.raises(CommandNotAllowed):
        engine.check_command("sudo apt install")


def test_smoke_3_network_three_levels() -> None:
    """3. 网络三档."""
    off_eng = PolicyEngine(policy=EffectivePolicy(network="off"))
    local_eng = PolicyEngine(policy=EffectivePolicy(network="local"))
    any_eng = PolicyEngine(policy=EffectivePolicy(network="any"))

    with pytest.raises(NetworkNotAllowed):
        off_eng.check_url("https://api.openai.com")
    assert local_eng.check_url("http://10.0.0.1:8080") is True
    with pytest.raises(NetworkNotAllowed):
        local_eng.check_url("https://api.openai.com")
    assert any_eng.check_url("https://api.openai.com") is True


def test_smoke_4_merge_cannot_relax() -> None:
    """4. merge 收紧不能放松."""
    base = EffectivePolicy(
        tool_level="safe", network="off", workspace_dirs=["/a", "/b"]
    )
    # 想把 tool_level 提升到 full → 被拒绝, 保留 safe
    merged = merge(base, {"tool_level": "full", "network": "any"})
    assert merged.tool_level == "safe"
    assert merged.network == "off"
    # workspace_dirs 取交集: 传 ["/a"] → 得到 ["/a"]
    merged2 = merge(base, {"workspace_dirs": ["/a"]})
    assert merged2.workspace_dirs == ["/a"]


def test_smoke_5_audit_redaction() -> None:
    """5. 审计脱敏."""
    audit = InMemoryAuditLogger()
    p = EffectivePolicy(workspace_dirs=["/work"])
    engine = PolicyEngine(policy=p, audit=audit)

    # 触发一次 .env 拒绝
    try:
        engine.check_path("/work/proj/.env")
    except PathNotAllowed:
        pass

    events = audit.all()
    assert len(events) == 1
    d = events[0].to_dict()
    # 路径被脱敏
    assert "<redacted:env-file>" in d["target"]
    # 原始路径不在 event dict 里
    assert "/work/proj/.env" not in d["target"]


def test_smoke_helper_redact_path_basic() -> None:
    """单独验证 redact_path 的基本分类."""
    assert redact_path("/x/.env") == "<redacted:env-file>"
    assert redact_path("/x/cert.pem") == "<redacted:pem>"
    assert redact_path("/x/srv.key") == "<redacted:ssh-key>"
    # secrets/ 目录下的文件被识别为 generic
    assert redact_path("/x/secrets/x.yaml") == "<redacted:generic>"
    assert redact_path("/x/credentials/db.json") == "<redacted:generic>"
    assert redact_path("/x/normal.py") == "/x/normal.py"
