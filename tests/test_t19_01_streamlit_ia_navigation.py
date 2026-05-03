from pathlib import Path

from streamlit_app.navigation_ux import navigation_summary_for_user, sync_navigation_state
from streamlit_app.unified_shell import (
    build_breadcrumb_labels,
    build_shell_for_user,
    filter_personalized_items,
    flatten_shell_sections,
    load_shell_config,
    search_shell_items,
    toggle_favorite_key,
    update_recent_keys,
)
from web_cabinet import rbac


def test_t19_01_operator_sees_grouped_navigation_sections_in_order() -> None:
    summary = navigation_summary_for_user(
        role=rbac.ROLE_OPERATOR,
        permissions=rbac.ROLE_PERMISSIONS.get(rbac.ROLE_OPERATOR, []),
    )
    assert summary["groups"] == ["Home", "Operations", "Analytics", "Reports", "Knowledge"]
    assert "Operations" in summary["section_descriptions"]
    assert summary["search_index_size"] >= 10


def test_t19_01_hidden_profiles_resolve_for_breadcrumbs_but_not_in_quick_launcher() -> None:
    cfg = load_shell_config(Path("configs/ui/ia_v3.yaml"))
    perms = set(rbac.ROLE_PERMISSIONS.get(rbac.ROLE_DIRECTOR, []))
    sections = build_shell_for_user(cfg=cfg, role=rbac.ROLE_DIRECTOR, permissions=perms)
    quick = [item.key for item in search_shell_items(sections, "profile", limit=10)]
    assert "group_profile" not in quick
    assert "animal_profile" not in quick

    shell_state = {}
    state = sync_navigation_state(
        shell_state,
        role=rbac.ROLE_DIRECTOR,
        permissions=perms,
        current_page="pages/15_Animal_Profile.py",
    )
    current = state["current_item"]
    assert current is not None
    assert current.key == "animal_profile"
    assert build_breadcrumb_labels(current) == ["Home", "Profiles", "Animal Profile"]


def test_t19_01_recent_pages_are_deduplicated_and_favorites_filter_accessible_items() -> None:
    cfg = load_shell_config(Path("configs/ui/ia_v3.yaml"))
    perms = set(rbac.ROLE_PERMISSIONS.get(rbac.ROLE_OPERATOR, []))
    sections = build_shell_for_user(cfg=cfg, role=rbac.ROLE_OPERATOR, permissions=perms, include_hidden=True)
    flat = flatten_shell_sections(sections)

    recent = []
    for key in ["home", "jobs_center", "report_ops", "jobs_center", "reports", "saved_views"]:
        recent = update_recent_keys(recent, key, limit=4)
    assert recent == ["saved_views", "reports", "jobs_center", "report_ops"]

    favorites = toggle_favorite_key([], "jobs_center")
    favorites = toggle_favorite_key(favorites, "saved_views")
    favorites = toggle_favorite_key(favorites, "jobs_center")
    assert favorites == ["saved_views"]

    visible = filter_personalized_items(flat, ["saved_views", "animal_profile"], include_hidden=False)
    assert [item.key for item in visible] == ["saved_views"]


def test_t19_01_docs_and_app_wire_navigation_ux() -> None:
    app = Path("streamlit_app/app.py").read_text(encoding="utf-8")
    common = Path("streamlit_app/common.py").read_text(encoding="utf-8")
    doc = Path("docs/streamlit_ia_navigation.md").read_text(encoding="utf-8")
    gate = Path("ci/pytest_gate.txt").read_text(encoding="utf-8")

    assert "render_shell_sidebar_tools" in app
    assert "render_page_navigation_header" in common
    assert "Quick launcher" in doc
    assert "Recent pages" in doc
    assert "Favorites" in doc
    assert "tests/test_t19_01_streamlit_ia_navigation.py" in gate
