from __future__ import annotations

from pathlib import Path

import genomeai.regular_reports as regular_mod
import genomeai.report as assistant_mod
import genomeai.template_reports as template_mod


def test_t15_08_assistant_run_report_is_core_wrapper(monkeypatch, tmp_path: Path) -> None:
    called: dict[str, object] = {}

    def _stub(**kwargs):
        called.update(kwargs)
        return {"ok": True, "report_version": "report_stub", "outputs": {}}

    monkeypatch.setattr(assistant_mod, "run_assistant_report_use_case", _stub)
    res = assistant_mod.run_report(
        artifacts_root=tmp_path / "artifacts",
        data_version="dv_stub",
        qc_run="qc_stub",
        model_version="model_stub",
        scoring_run="score_stub",
        mode="fallback",
        make_pdf=False,
    )

    assert res["ok"] is True
    assert called["data_version"] == "dv_stub"
    assert called["qc_run"] == "qc_stub"
    assert called["model_version"] == "model_stub"
    assert called["scoring_run"] == "score_stub"
    assert called["build_fact_pack"] is assistant_mod.build_fact_pack


def test_t15_08_regular_run_report_is_core_wrapper(monkeypatch, tmp_path: Path) -> None:
    called: dict[str, object] = {}

    def _stub(**kwargs):
        called.update(kwargs)
        return {"ok": True, "report_version": "regular_stub", "outputs": {}}

    monkeypatch.setattr(regular_mod, "run_regular_report_use_case", _stub)
    res = regular_mod.run_regular_report(
        artifacts_root=tmp_path / "artifacts",
        data_version="dv_regular",
        asof_date="2026-03-15",
        period="weekly",
        mode="fallback",
    )

    assert res["ok"] is True
    assert called["data_version"] == "dv_regular"
    assert called["period"] == "weekly"
    assert called["build_fact_pack"] is regular_mod.build_fact_pack_regular
    assert called["render_md"] is regular_mod._render_md


def test_t15_08_template_run_report_is_core_wrapper(monkeypatch, tmp_path: Path) -> None:
    called: dict[str, object] = {}

    def _stub(**kwargs):
        called.update(kwargs)
        return {"ok": True, "report_version": "template_stub", "outputs": {}}

    monkeypatch.setattr(template_mod, "run_template_report_use_case", _stub)
    res = template_mod.run_template_report(
        artifacts_root=tmp_path / "artifacts",
        data_version="dv_template",
        asof_date="2026-03-15",
        template={"template_id": "tpl_stub", "name": "Stub", "sections": [], "metrics": []},
        inputs={"alerts": [], "tasks": [], "decisions": []},
        mode="fallback",
    )

    assert res["ok"] is True
    assert called["data_version"] == "dv_template"
    assert called["mode"] == "fallback"
    prepare = called["prepare_fact_pack_and_markdown"]
    assert callable(prepare)
