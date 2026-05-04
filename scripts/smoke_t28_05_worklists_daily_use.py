"""T28-05 Worklists daily use — smoke test for worklist workflow round-trip."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from core.workflow.worklists import (
    WORKLIST_TYPES,
    DEFAULT_WORKLIST_TITLES,
    create_worklist_use_case,
    accept_worklist_use_case,
    close_worklist_use_case,
)


def _check_worklist_types() -> None:
    assert WORKLIST_TYPES, "WORKLIST_TYPES must be non-empty"
    for wt in WORKLIST_TYPES:
        assert isinstance(wt, str) and wt, f"Invalid worklist type: {wt!r}"


def _check_default_titles() -> None:
    assert DEFAULT_WORKLIST_TITLES, "DEFAULT_WORKLIST_TITLES must be non-empty"
    for wt, title in DEFAULT_WORKLIST_TITLES.items():
        assert isinstance(title, str) and title, f"Missing title for worklist type {wt!r}"


def _check_use_case_callables() -> None:
    for fn in (create_worklist_use_case, accept_worklist_use_case, close_worklist_use_case):
        assert callable(fn), f"{fn.__name__} must be callable"


def main() -> int:
    _check_worklist_types()
    _check_default_titles()
    _check_use_case_callables()
    print(f"OK: {len(WORKLIST_TYPES)} worklist types, {len(DEFAULT_WORKLIST_TITLES)} titles — daily use smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
