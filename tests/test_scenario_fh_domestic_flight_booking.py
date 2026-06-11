from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from openagent.api.controllers.chat_controller import _ask_user_to_card
from openagent.api.lifecycle import _skill_paths_with_fallbacks
from openagent.auip.cards import CARD_TYPES_SET
from openagent.scenarios.loader import load_scenario
from openagent.skills.registry import SkillRegistry
from openagent.streaming import StreamEvent

WORK_DIR = Path(__file__).resolve().parents[1] / "work"
SCENARIO_PATH = WORK_DIR / "scenarios" / "fh_domestic_flight_booking.scenario.yaml"
SCENARIO_DIR = WORK_DIR / "scenarios" / "fh_domestic_flight_booking"
SKILL_DIR = WORK_DIR / "shared" / "skills" / "fh-domestic-flight-booking"
NORMALIZE_SCRIPT = SKILL_DIR / "scripts" / "normalize_request.py"


def _load_fh_domestic():
    return load_scenario(
        SCENARIO_PATH,
        ctx={
            "WORK_ROOT": str(WORK_DIR),
            "WORK_SHARED": str(WORK_DIR / "shared"),
            "SCENARIO_DIR": str(SCENARIO_DIR),
            "PROJECT_DIR": str(
                WORK_DIR / "tenants" / "tenant-A" / "projects" / "project-1"
            ),
        },
    )


def test_fh_domestic_init_loads_with_auip_schema():
    cfg = _load_fh_domestic()

    assert cfg.name == "fh_domestic_flight_booking"
    assert cfg.a2ui.enabled is True
    assert cfg.execution.orchestration == "single"
    assert cfg.security.tool_level == "safe"
    assert cfg.a2ui.ask_user is not None
    assert Path(cfg.a2ui.ask_user.schema_ref).exists()
    assert "ask_user" in cfg.execution.tools
    assert "question" not in cfg.execution.tools
    assert "queryFlightBasic" in cfg.execution.tools
    assert "feihe-travel_queryFlightBasic" in cfg.execution.tools


def test_fh_domestic_skill_is_loaded_by_startup_fallbacks():
    paths = _skill_paths_with_fallbacks(type("SettingsStub", (), {"skill_paths": []})())
    reg = SkillRegistry()
    reg.load_from_paths(*paths)

    assert reg.get("fh-domestic-flight-booking") is not None


def test_fh_domestic_happy_path_card_whitelist_matches_auip():
    cfg = _load_fh_domestic()
    card_types = set(cfg.a2ui.card_schemas)

    assert card_types
    assert card_types.issubset(CARD_TYPES_SET)
    assert {"OD_INPUT", "FLIGHT_RESULT", "CABIN_LIST", "ORDER_CONFIRM"}.issubset(
        card_types
    )

    schema = json.loads(Path(cfg.a2ui.ask_user.schema_ref).read_text(encoding="utf-8"))
    schema_types = set(schema["properties"]["card_type"]["enum"])
    assert schema_types == card_types


def test_fh_domestic_happy_path_prompt_uses_chinese_and_minimal_questions():
    cfg = _load_fh_domestic()
    prompt = cfg.execution.system_prompt

    assert "所有回复" in prompt
    assert "必须使用中文" in prompt
    assert "先从用户原话中提取信息" in prompt
    assert "不要再用 ask_user 重复确认" in prompt
    assert "才调用\n    ask_user 询问用户" in prompt
    assert "缺少查询必填项：OD_INPUT" in prompt
    assert "只问缺失项" in prompt
    assert "不要用 Bash 拼 HTTP 请求" in prompt
    assert "不要用 task 子代理代查航班" in prompt
    assert "速度优先级最高" in prompt
    assert "不要先问舱位" in prompt
    assert "不要加载旧 flight-query skill" in prompt


def test_fh_domestic_does_not_reference_legacy_flight_query_skill():
    cfg = _load_fh_domestic()

    assert cfg.execution.skills == ["fh-domestic-flight-booking"]
    assert "flight-query" not in cfg.execution.skills
    assert "read_skill" not in cfg.execution.tools
    for tool in ("skill", "read", "glob", "grep"):
        assert tool not in cfg.execution.tools


def test_fh_domestic_workspace_has_no_legacy_claude_flight_query_skills():
    legacy_root = WORK_DIR / "tenant-A" / "project-1" / ".claude" / "skills"
    legacy_skill_files = [
        legacy_root / "flight-query" / "SKILL.md",
        legacy_root / "flight-query.iata_icao_codes" / "SKILL.md",
        legacy_root / "flight-query.query_flight_basic" / "SKILL.md",
    ]

    for path in legacy_skill_files:
        assert not path.exists(), f"legacy runtime skill should not exist: {path}"


def test_fh_domestic_normalize_allows_first_search_without_session_id():
    spec = importlib.util.spec_from_file_location(
        "fh_normalize_request", NORMALIZE_SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    plan = module.normalize(
        {
            "departureCity": "北京",
            "arrivalCity": "上海",
            "departureDate": "明天",
        },
        today=module.date.fromisoformat("2026-06-09"),
    )

    assert plan["departureDate"] == "2026-06-10"
    assert module.validate(plan) == []


def test_fh_domestic_error_rejects_legacy_card_aliases():
    cfg = _load_fh_domestic()
    allowed = set(cfg.a2ui.card_schemas)

    for legacy_type in ("CABIN_OPTIONS", "ORDER_PREVIEW"):
        event = StreamEvent.tool_use(
            tool_name="ask_user",
            input_data={"card_type": legacy_type, "title": "legacy"},
        )
        out = _ask_user_to_card(event, allowed_card_types=allowed)
        assert out.type == "error"
        assert out.data.get("code") == "CARD_TYPE_INVALID"
