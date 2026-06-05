"""Custom pydantic-settings sources for path-aware complex fields.

Some settings fields (currently ``mcp_tools_config`` and ``default_agents_json``)
are typed as ``list[dict]``. By default pydantic-settings will JSON-decode any
string value, which breaks when the user wants to point the env var at a JSON
file path (a common pattern in containerised deployments).

The ``PathAwareEnvSource`` and ``PathAwareDotEnvSource`` classes override
``prepare_field_value`` so that, for the selected fields only, a non-JSON
string is treated as a file path: if the file exists, its contents are
substituted before pydantic-settings attempts JSON decoding. Other fields and
unparseable values fall back to the standard behaviour.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic_settings import DotEnvSettingsSource, EnvSettingsSource


# Fields that accept either an inline JSON string or a path to a JSON file.
PATH_AWARE_FIELDS: frozenset[str] = frozenset(
    {"mcp_tools_config", "default_agents_json"}
)


def _maybe_load_path(value: Any, field_name: str) -> Any:
    """Return JSON file contents if ``value`` is a path to an existing file."""
    if field_name not in PATH_AWARE_FIELDS or not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped or stripped[0] in "[{":
        return value
    candidate = Path(stripped)
    if candidate.is_file():
        return candidate.read_text(encoding="utf-8")
    return value


class PathAwareEnvSource(EnvSettingsSource):
    """EnvSettingsSource that resolves file paths for selected complex fields."""

    def prepare_field_value(
        self,
        field_name: str,
        field: Any,
        value: Any,
        value_is_complex: bool,
    ) -> Any:
        value = _maybe_load_path(value, field_name)
        return super().prepare_field_value(
            field_name, field, value, value_is_complex
        )


class PathAwareDotEnvSource(DotEnvSettingsSource):
    """DotEnvSettingsSource that resolves file paths for selected complex fields."""

    def prepare_field_value(
        self,
        field_name: str,
        field: Any,
        value: Any,
        value_is_complex: bool,
    ) -> Any:
        value = _maybe_load_path(value, field_name)
        return super().prepare_field_value(
            field_name, field, value, value_is_complex
        )
