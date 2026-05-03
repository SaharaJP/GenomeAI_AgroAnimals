from pathlib import Path

from streamlit_app.home_widgets import build_role_home_payload, load_home_pages_config
from streamlit_app.unified_shell import build_shell_for_user, load_shell_config
from web_cabinet import rbac


def _shell_for_role(role: str):
    cfg = load_shell_config(Path("configs/ui/ia_v3.yaml"))
    perms = set(rbac.ROLE_PERMISSIONS.get(role, []))
    return build_shell_for_user(cfg=cfg, role=role, permissions=perms, include_hidden=False)


def _snapshot() -> dict:
    return {
        "data_version": "dv_demo",
        "kpis": {
            "milk_total_kg_7d": {"kpi_id": "milk_total_kg_7d", "title": "Milk total kg 7d", "value": 125000, "unit": "kg", "source": "kpi_run=demo"},
            "milk_avg_kg_per_cow_1d": {"kpi_id": "milk_avg_kg_per_cow_1d", "title": "Milk avg kg per cow 1d", "value": 31.4, "unit": "kg", "source": "kpi_run=demo"},
            "alerts_open_count": {"kpi_id": "alerts_open_count", "title": "Alerts open count", "value": 9, "unit": "", "source": "kpi_run=demo"},
            "margin_rub_7d": {"kpi_id": "margin_rub_7d", "title": "Margin rub 7d", "value": 530000, "unit": "RUB", "source": "kpi_run=demo"},
            "decisions_accept_rate_90d": {"kpi_id": "decisions_accept_rate_90d", "title": "Decisions accept rate 90d", "value": 0.71, "unit": "", "source": "kpi_run=demo"},
            "fat_pct_avg_7d": {"kpi_id": "fat_pct_avg_7d", "title": "Fat pct avg 7d", "value": 3.8, "unit": "%", "source": "kpi_run=demo"},
            "protein_pct_avg_7d": {"kpi_id": "protein_pct_avg_7d", "title": "Protein pct avg 7d", "value": 3.2, "unit": "%", "source": "kpi_run=demo"},
            "scc_avg_7d": {"kpi_id": "scc_avg_7d", "title": "SCC avg 7d", "value": 220000, "unit": "", "source": "kpi_run=demo"},
            "mastitis_events_30d": {"kpi_id": "mastitis_events_30d", "title": "Mastitis events 30d", "value": 4, "unit": "", "source": "kpi_run=demo"},
            "severe_health_events_30d": {"kpi_id": "severe_health_events_30d", "title": "Severe health events 30d", "value": 1, "unit": "", "source": "kpi_run=demo"},
        },
        "operational": {
            "alerts": {"new": 3, "acknowledged": 2, "resolved": 7},
            "tasks": {"open": 5, "done": 11},
        },
        "report": {"has_any": True, "report_version": "rv_demo"},
        "role_focus": {"top_candidates": 6, "high_risk_count": 3},
    }


def test_t19_02_home_payload_per_role_has_single_insight_kpis_and_actions() -> None:
    cfg = load_home_pages_config(Path("configs/ui/home_pages_v1.yaml"))
    snapshot = _snapshot()

    for role in [
        rbac.ROLE_ADMIN,
        rbac.ROLE_DIRECTOR,
        rbac.ROLE_OPERATOR,
        rbac.ROLE_VET,
        rbac.ROLE_VIEWER,
        rbac.ROLE_ZOOTECH,
    ]:
        payload = build_role_home_payload(
            role=role,
            shell_sections=_shell_for_role(role),
            snapshot=snapshot,
            cfg=cfg,
        )
        assert payload.insight_title
        assert payload.insight_text
        assert 3 <= len(payload.metrics) <= 6
        assert 3 <= len(payload.actions) <= 5
        assert payload.focus_title
        assert payload.focus_hint


def test_t19_02_docs_and_gate_reference_home_redesign() -> None:
    doc = Path("docs/streamlit_home_pages.md").read_text(encoding="utf-8")
    gate = Path("ci/pytest_gate.txt").read_text(encoding="utf-8")
    home = Path("streamlit_app/home_v3.py").read_text(encoding="utf-8")

    assert "что мне делать сейчас" in doc.lower()
    assert "3–6 KPI" in doc or "3-6 KPI" in doc
    assert "tests/test_t19_02_home_pages.py" in gate
    assert "build_role_home_payload" in home
