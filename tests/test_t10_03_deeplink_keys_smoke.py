from __future__ import annotations

from pathlib import Path

PAGES_DIR = Path(__file__).resolve().parents[1] / "streamlit_app" / "pages"


def _read(name: str) -> str:
    return (PAGES_DIR / name).read_text(encoding="utf-8", errors="ignore")


def test_alert_center_accepts_deeplink_selected_alert() -> None:
    txt = _read("5_Alert_Center_v2.py")
    assert "alert_center.selected_alert_id" in txt


def test_worklist_accepts_deeplink_selected_task() -> None:
    txt = _read("7_Worklist_v1.py")
    assert "worklist.selected_task_id" in txt


def test_decision_log_accepts_deeplink_selected_decision() -> None:
    txt = _read("6_Decision_Log_v2.py")
    assert "decision_log.selected_decision_id" in txt


def test_report_view_accepts_deeplink_keys() -> None:
    txt = _read("16_Report_View.py")
    assert "report_view.data_version" in txt
    assert "report_view.report_version" in txt
