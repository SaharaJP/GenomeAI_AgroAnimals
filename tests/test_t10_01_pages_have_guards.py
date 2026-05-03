from __future__ import annotations

from pathlib import Path


PAGES_DIR = Path(__file__).resolve().parents[1] / "streamlit_app" / "pages"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore")


def test_all_pages_require_user() -> None:
    py_files = sorted([p for p in PAGES_DIR.glob("*.py") if not p.name.startswith("__")])
    assert py_files, "no streamlit pages found"
    bad = []
    for p in py_files:
        txt = _read(p)
        if "require_user" not in txt:
            bad.append(p.name)
    assert not bad, f"pages missing require_user(): {bad}"


def test_non_trivial_pages_have_rbac_guard() -> None:
    """Defense-in-depth: even if a user guesses a URL/page, the page must guard itself."""
    allow_no_guard = {
        "0_Home_v3.py",
        "0_Home_Viewer.py",
        "11_Glossary_v3.py",
    }

    py_files = sorted([p for p in PAGES_DIR.glob("*.py") if not p.name.startswith("__")])
    bad = []
    for p in py_files:
        if p.name in allow_no_guard:
            continue
        txt = _read(p)
        # acceptable patterns:
        # - require_permissions(...)
        # - require_roles(...)
        # - manual check "PERM_... not in user['permissions']"
        if (
            "require_permissions" not in txt
            and "require_roles" not in txt
            and "user[\"permissions\"]" not in txt
            and "user['permissions']" not in txt
        ):
            bad.append(p.name)

    assert not bad, f"pages missing RBAC guard (require_permissions/roles or manual): {bad}"
