import pytest

from hermetic_agent.store.object.skill_files import validate_skill_path


def test_accepts_normal_relative_path():
    p = validate_skill_path("scripts/run.sh")
    assert p == "scripts/run.sh"


@pytest.mark.parametrize("bad", [
    "../etc/passwd", "/etc/passwd", "..\\windows",
    "a\x00b", "a;b", "a$b", "", "  ",
])
def test_rejects_traversal_and_invalid(bad):
    with pytest.raises(ValueError):
        validate_skill_path(bad)
