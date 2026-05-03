from pathlib import Path

from streamlit_app.ia_v3 import load_ia_config, build_nav_for_user


def test_ia_v3_loads_and_filters_by_permissions():
    cfg = load_ia_config(Path("configs/ui/ia_v3.yaml"))

    # minimal perms: only KPI view
    groups = build_nav_for_user(cfg=cfg, role="Viewer", permissions={"kpi.view"})
    flat = [it.key for g in groups for it in g.items]

    assert "home" in flat
    assert "director_summary" in flat
    # reports require export.download -> must not be visible
    assert "reports" not in flat
    assert "ai_assistant" not in flat


def test_ia_v3_export_items_visible_with_export_permission():
    cfg = load_ia_config(Path("configs/ui/ia_v3.yaml"))
    groups = build_nav_for_user(cfg=cfg, role="Viewer", permissions={"export.download"})
    flat = [it.key for g in groups for it in g.items]

    # home and glossary do not require perms
    assert "home" in flat
    assert "glossary" in flat
    # export‑gated pages are visible now
    assert "reports" in flat
    assert "ai_assistant" in flat
