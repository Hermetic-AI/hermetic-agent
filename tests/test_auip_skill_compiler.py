"""tests/test_auip_skill_compiler.py — compile_skill_md 单元测试.

P5 简化: 只解析 frontmatter + §2.1 状态表 + §3.1 工具白名单,
其他 prose 整体作为 prompt_template 返回.
"""

from __future__ import annotations

from pathlib import Path

from hermetic_agent.auip.skill_compiler import compile_skill_md


def _write_skill_md(tmp_path: Path, body: str, frontmatter: str = "", name: str = "SKILL.md") -> Path:
    """写一个 SKILL.md, 可选 frontmatter."""
    p = tmp_path / name
    if frontmatter:
        p.write_text(f"---\n{frontmatter}\n---\n\n{body}", encoding="utf-8")
    else:
        p.write_text(body, encoding="utf-8")
    return p


def test_compile_skill_md_extracts_states(tmp_path: Path) -> None:
    """§2.1 状态表 → states 列表."""
    body = """
## 2. 状态机

### 2.1 状态一览

| # | State ID | 名称 | 类别 | 入口守卫 |
|---|---|---|---|---|
| 1 | S01 | INIT | 起点 | 收到客户提问 |
| 2 | S02 | OD_PENDING | 等待 | 未拿到 OD |
| 3 | S05 | FLIGHT_LISTED | 中间 | 拿到 departDate |
| 4 | F1 | AUTO_SUBMIT | 终止 | 自动提交订单 |
"""
    p = _write_skill_md(
        tmp_path=tmp_path,
        body=body,
        frontmatter='name: book-flight\nversion: "1.0.0"\ndescription: 订票',
    )
    out = compile_skill_md(p)
    assert out["name"] == "book-flight"
    assert out["version"] == "1.0.0"
    sids = [s["id"] for s in out["states"]]
    assert sids == ["S01", "S02", "S05", "F1"]
    assert out["initial_state"] == "S01"
    names = [s["name"] for s in out["states"]]
    assert "INIT" in names
    assert "OD_PENDING" in names
    assert "状态机" in out["prompt_template"]


def test_compile_skill_md_extracts_state_id_in_first_column(tmp_path: Path) -> None:
    """state id 在第一列时也能解析 (兼容简洁表格)."""
    body = """
### 2.1 状态一览

| State ID | Name |
|---|---|
| S01 | INIT |
| S02 | ASK |
"""
    p = _write_skill_md(tmp_path, body, frontmatter="name: foo")
    out = compile_skill_md(p)
    sids = [s["id"] for s in out["states"]]
    assert sids == ["S01", "S02"]
    assert out["states"][0]["name"] == "INIT"


def test_compile_skill_md_extracts_tool_whitelist(tmp_path: Path) -> None:
    """§3.1 工具白名单 → allowed_tools 列表."""
    body = """
## 2. 状态机 (省略)

## 3. MCP 工具

### 3.1 工具白名单

可用的工具:
- `query_flight_basic`
- `choose_flight`
- `choose_cabin`
- `fill_passenger`
- `validate_booking_info`
- `submit_order`

不在白名单的: 任何其他工具.
"""
    p = _write_skill_md(tmp_path, body, frontmatter="name: book-flight")
    out = compile_skill_md(p)
    tools = out["allowed_tools"]
    assert "query_flight_basic" in tools
    assert "choose_flight" in tools
    assert "choose_cabin" in tools
    assert "fill_passenger" in tools
    assert "validate_booking_info" in tools
    assert "submit_order" in tools
    assert len(tools) == len(set(tools))


def test_compile_skill_md_no_frontmatter_uses_filename(tmp_path: Path) -> None:
    """无 frontmatter 时用文件名做 name, 版本默认 1.0.0."""
    p = tmp_path / "my_skill.md"
    p.write_text("# Just text\nNo frontmatter here.\n", encoding="utf-8")
    out = compile_skill_md(p)
    assert out["name"] == "my_skill"
    assert out["version"] == "1.0.0"
    assert out["description"] == ""
    assert out["states"] == []
    assert out["allowed_tools"] == []
    assert "Just text" in out["prompt_template"]


def test_compile_skill_md_missing_file_returns_defaults(tmp_path: Path) -> None:
    """文件不存在时仍返回合法 dict (不抛异常)."""
    p = tmp_path / "definitely_missing_skill.md"
    out = compile_skill_md(p)
    assert out["name"] == "definitely_missing_skill"
    assert out["initial_state"] == "S01"
    assert out["states"] == []


def test_compile_skill_md_state_section_with_anchor(tmp_path: Path) -> None:
    """'State ID' 锚点也应触发状态表解析."""
    body = """
## States

| State ID | Name | Category |
|---|---|---|
| S01 | INIT | start |
| S02 | ASK | waiting |
"""
    p = _write_skill_md(tmp_path, body, frontmatter="name: foo")
    out = compile_skill_md(p)
    sids = [s["id"] for s in out["states"]]
    assert sids == ["S01", "S02"]


def test_compile_skill_md_stops_at_table_end(tmp_path: Path) -> None:
    """状态表解析在脱离表格区后停止 (不无限扫描)."""
    body = """
### 2.1 状态一览

| S01 | A |
| S02 | B |

中间 prose, 写一些内容. 包含 | 这种字符也不应被识别为表格.

## 4. 其他章节

| S99 | 这是 prose 中的表格, 不应被解析 |
"""
    p = _write_skill_md(tmp_path, body, frontmatter="name: bar")
    out = compile_skill_md(p)
    sids = [s["id"] for s in out["states"]]
    assert sids == ["S01", "S02"]
