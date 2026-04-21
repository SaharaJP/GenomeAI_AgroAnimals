from __future__ import annotations

from pathlib import Path

import core.reporting as reporting
import genomeai.regular_reports as regular_mod
import genomeai.report as assistant_mod
import genomeai.template_reports as template_mod


ROOT = Path(__file__).resolve().parents[1]


def test_t15_08_core_reporting_high_level_entrypoints_are_available() -> None:
    assert callable(reporting.run_assistant_report)
    assert callable(reporting.run_regular_report)
    assert callable(reporting.run_template_report)


def test_t15_08_legacy_assistant_run_wrapper_delegates_to_core_entrypoint(monkeypatch) -> None:
    called: dict[str, object] = {}

    def _stub(**kwargs):
        called.update(kwargs)
        return {"ok": True, "report_version": "report_stub"}

    monkeypatch.setattr(assistant_mod, "_core_run_assistant_report", _stub)
    result = assistant_mod.run_report(
        artifacts_root=Path("artifacts"),
        data_version="dv_stub",
        qc_run="qc_stub",
        model_version="model_stub",
        scoring_run="score_stub",
        mode="fallback",
        report_version="report_stub",
        make_pdf=False,
        llm_model=None,
    )

    assert result["ok"] is True
    assert called["data_version"] == "dv_stub"
    assert called["make_pdf"] is False


def test_t15_08_legacy_regular_and_template_wrappers_delegate_to_core_entrypoints(monkeypatch) -> None:
    regular_called: dict[str, object] = {}
    template_called: dict[str, object] = {}

    def _stub_regular(**kwargs):
        regular_called.update(kwargs)
        return {"ok": True, "report_version": "regular_stub"}

    def _stub_template(**kwargs):
        template_called.update(kwargs)
        return {"ok": True, "report_version": "template_stub"}

    monkeypatch.setattr(regular_mod, "_core_run_regular_report", _stub_regular)
    monkeypatch.setattr(template_mod, "_core_run_template_report", _stub_template)

    regular_result = regular_mod.run_regular_report(
        artifacts_root=Path("artifacts"),
        data_version="dv_stub",
        asof_date="2025-01-31",
        period="weekly",
        mode="fallback",
        llm_model=None,
        report_version="regular_stub",
    )
    template_result = template_mod.run_template_report(
        artifacts_root=Path("artifacts"),
        data_version="dv_stub",
        asof_date="2025-01-31",
        template={"template_id": "tpl_1", "name": "Stub", "sections": [], "metrics": [], "options": {}},
        inputs={"alerts": [], "tasks": [], "decisions": []},
        mode="fallback",
        llm_model=None,
        report_version="template_stub",
        max_rows=5,
        options_override={"focus_type": "group", "focus_id": "pen-1"},
    )

    assert regular_result["report_version"] == "regular_stub"
    assert regular_called["period"] == "weekly"
    assert template_result["report_version"] == "template_stub"
    assert template_called["options_override"] == {"focus_type": "group", "focus_id": "pen-1"}


def test_t15_08_cli_and_ui_modules_import_core_reporting_entrypoints() -> None:
    cli_text = (ROOT / "src" / "genomeai" / "cli.py").read_text(encoding="utf-8")
    smoke_text = (ROOT / "src" / "genomeai" / "smoke.py").read_text(encoding="utf-8")
    reproduce_text = (ROOT / "src" / "genomeai" / "run_reproduce.py").read_text(encoding="utf-8")
    regular_page_text = (ROOT / "streamlit_app" / "pages" / "10_Regular_Reports.py").read_text(encoding="utf-8")
    template_page_text = (ROOT / "streamlit_app" / "pages" / "18_Report_Templates.py").read_text(encoding="utf-8")

    assert "from core.reporting import run_assistant_report as run_report" in cli_text
    assert "from core.reporting import run_regular_report" in cli_text
    assert "from core.reporting import run_assistant_report as run_report" in smoke_text
    assert "from core.reporting import run_assistant_report as run_report" in reproduce_text
    assert "from core.reporting import run_regular_report" in regular_page_text
    assert "from core.reporting import run_template_report" in template_page_text
