from pathlib import Path

from streamlit_app.unified_shell import (
    build_shell_for_user,
    collect_status_badges,
    flatten_shell_sections,
    get_home_item,
    load_shell_config,
)
from web_cabinet import rbac


def test_t18_01_home_page_resolves_per_role_in_unified_shell():
    cfg = load_shell_config(Path("configs/ui/ia_v3.yaml"))
    for role in [
        rbac.ROLE_DIRECTOR,
        rbac.ROLE_ZOOTECH,
        rbac.ROLE_VET,
        rbac.ROLE_OPERATOR,
        rbac.ROLE_ADMIN,
        rbac.ROLE_VIEWER,
    ]:
        perms = set(rbac.ROLE_PERMISSIONS.get(role, []))
        sections = build_shell_for_user(cfg=cfg, role=role, permissions=perms)
        home = get_home_item(sections)
        assert home is not None
        assert home.page.endswith(f"0_Home_{role}.py")


def test_t18_01_hidden_internal_pages_are_excluded_from_primary_shell():
    cfg = load_shell_config(Path("configs/ui/ia_v3.yaml"))
    perms = set(rbac.ROLE_PERMISSIONS.get(rbac.ROLE_DIRECTOR, []))
    sections = build_shell_for_user(cfg=cfg, role=rbac.ROLE_DIRECTOR, permissions=perms)
    flat = flatten_shell_sections(sections)
    assert "group_profile" not in flat
    assert "animal_profile" not in flat
    assert "report_view" not in flat


def test_t18_01_operations_shell_hidden_for_viewer_and_visible_for_operator():
    cfg = load_shell_config(Path("configs/ui/ia_v3.yaml"))

    viewer_sections = build_shell_for_user(
        cfg=cfg,
        role=rbac.ROLE_VIEWER,
        permissions=set(rbac.ROLE_PERMISSIONS.get(rbac.ROLE_VIEWER, [])),
    )
    assert "operations_shell" not in flatten_shell_sections(viewer_sections)

    operator_sections = build_shell_for_user(
        cfg=cfg,
        role=rbac.ROLE_OPERATOR,
        permissions=set(rbac.ROLE_PERMISSIONS.get(rbac.ROLE_OPERATOR, [])),
    )
    assert "operations_shell" in flatten_shell_sections(operator_sections)


def test_t18_01_collect_status_badges_prefers_signal_keys():
    badges = collect_status_badges(
        {
            "role": "Director",
            "active_farm": "farm_demo",
            "active_site": "site_a",
            "regular_reports.data_version": "dv_001",
            "qc_run": "qc_123",
            "model_version": "mdl_01",
            "report_version": "rep_01",
            "request_id": "st_abc",
            "user_id": 42,
        }
    )
    assert ("role", "Director") in badges
    assert ("farm", "farm_demo") in badges
    assert ("site", "site_a") in badges
    assert ("data_version", "dv_001") in badges
    assert ("qc_run", "qc_123") in badges
    assert ("model_version", "mdl_01") in badges
    assert ("report_version", "rep_01") in badges
    assert ("request_id", "st_abc") in badges
    assert ("user_id", "42") in badges
