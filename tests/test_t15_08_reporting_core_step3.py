from __future__ import annotations

from pathlib import Path

import genomeai.regular_reports as regular_mod
import genomeai.template_reports as template_mod

from core.reporting import (
    generate_regular_report_text_fallback,
    generate_regular_report_text_llm,
    prepare_template_report_artifacts,
    render_regular_report_markdown,
)


def test_t15_08_core_regular_exports_are_available() -> None:
    assert callable(generate_regular_report_text_fallback)
    assert callable(generate_regular_report_text_llm)
    assert callable(render_regular_report_markdown)
    assert callable(prepare_template_report_artifacts)


def test_t15_08_legacy_regular_narrative_and_renderer_are_core_wrappers(monkeypatch, tmp_path: Path) -> None:
    called: dict[str, object] = {}

    def _stub_fallback(fact_pack, *, audience):
        called["fallback"] = {"fact_pack": fact_pack, "audience": audience}
        return {"executive_summary": "ok", "recommendations": "ok", "limitations": "ok"}

    def _stub_render(**kwargs):
        called["render"] = kwargs
        Path(kwargs["out_path"]).write_text("# stub\n", encoding="utf-8")

    monkeypatch.setattr(regular_mod, "_core_generate_regular_report_text_fallback", _stub_fallback)
    monkeypatch.setattr(regular_mod, "_core_render_regular_report_markdown", _stub_render)

    narrative = regular_mod.generate_regular_report_text_fallback({"versions": {}}, audience="director")
    regular_mod._render_md(
        narrative=narrative,
        fact_pack={"versions": {}},
        out_path=tmp_path / "report.md",
        report_version="report_stub",
        audience="ops",
        llm_used=False,
    )

    assert called["fallback"]["audience"] == "director"
    assert called["render"]["report_version"] == "report_stub"
    assert (tmp_path / "report.md").exists()


def test_t15_08_legacy_template_prepare_is_core_wrapper(monkeypatch, tmp_path: Path) -> None:
    called: dict[str, object] = {}

    def _stub_prepare(**kwargs):
        called.update(kwargs)
        return ({"versions": {"report_version": kwargs["report_version"]}}, {"director": "# ok\n", "ops": "# ok\n"}, {"template": {}})

    monkeypatch.setattr(template_mod, "prepare_template_report_artifacts", _stub_prepare)
    fact_pack, markdown_by_audience, summary_inputs = template_mod._prepare_template_report_artifacts_for_core(
        artifacts_root=tmp_path / "artifacts",
        data_version="dv_t15_08",
        asof_date="2026-03-15",
        report_version="regular_report_stub",
        out_dir=tmp_path / "out",
        exports_dir=tmp_path / "out" / "exports",
        template={"template_id": "tpl_stub"},
        inputs={"alerts": [], "tasks": [], "decisions": []},
        mode="fallback",
        max_rows=20,
        options_override={"focus_type": "alert", "focus_id": "A1"},
    )

    assert called["data_version"] == "dv_t15_08"
    assert called["report_version"] == "regular_report_stub"
    assert fact_pack["versions"]["report_version"] == "regular_report_stub"
    assert set(markdown_by_audience) == {"director", "ops"}
    assert "template" in summary_inputs
