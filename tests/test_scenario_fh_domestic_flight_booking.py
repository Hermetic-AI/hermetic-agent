from __future__ import annotations

import json
from pathlib import Path

from openagent.api.controllers.chat_controller import _ask_user_to_card
from openagent.auip.cards import CARD_TYPES_SET
from openagent.scenarios.loader import load_scenario
from openagent.streaming import StreamEvent

WORK_DIR = Path(__file__).resolve().parents[1] / "work"
SCENARIO_PATH = WORK_DIR / "scenarios" / "fh_domestic_flight_booking.scenario.yaml"
SCENARIO_DIR = WORK_DIR / "scenarios" / "fh_domestic_flight_booking"


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
    assert cfg.a2ui.ask_user is not None
    assert Path(cfg.a2ui.ask_user.schema_ref).exists()
    assert "ask_user" in cfg.execution.tools


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

