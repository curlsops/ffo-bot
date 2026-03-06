import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]


def test_no_on_conflict_with_partial_unique():
    pattern = re.compile(
        r"ON\s+CONFLICT\s*\([^)]+\)\s+WHERE\s*\(",
        re.IGNORECASE | re.DOTALL,
    )
    bad = [
        str(p.relative_to(_ROOT))
        for p in _ROOT.rglob("*.py")
        if "venv" not in str(p)
        and "migrations" not in str(p)
        and "tests/" not in str(p)
        and pattern.search(p.read_text())
    ]
    assert not bad, f"ON CONFLICT ... WHERE in {bad}. Use SELECT-then-INSERT/UPDATE."


def test_partial_unique_tables_use_select_then_insert():
    tables = ["user_permissions", "reaction_roles", "phrase_reactions", "command_permissions"]
    for path in (_ROOT / "bot").rglob("*.py"):
        text = path.read_text()
        for table in tables:
            if f"INSERT INTO {table}" in text and "ON CONFLICT" in text:
                pytest.fail(
                    f"{path.relative_to(_ROOT)}: {table} has partial unique - "
                    "use SELECT-then-INSERT, not ON CONFLICT"
                )
