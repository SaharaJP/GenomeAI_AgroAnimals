from __future__ import annotations

from pathlib import Path

import genomeai.report as assistant_mod

from core.reporting import (
    generate_assistant_report_text_fallback,
    generate_assistant_report_text_llm,
    render_assistant_report_docx,
    render_assistant_report_pdf,
)


def test_t15_08_core_assistant_exports_are_available() -> None:
    assert callable(generate_assistant_report_text_fallback)
    assert callable(generate_assistant_report_text_llm)
    assert callable(render_assistant_report_docx)
    assert callable(render_assistant_report_pdf)


def test_t15_08_legacy_assistant_narrative_and_renderers_are_core_wrappers(monkeypatch, tmp_path: Path) -> None:
    called: dict[str, object] = {}

    def _stub_fallback(fact_pack):
        called["fallback"] = fact_pack
        return {"executive_summary": "ok", "recommendations": "ok", "limitations": "ok"}

    def _stub_llm(fact_pack, *, model=None, temperature=0.2):
        called["llm"] = {"fact_pack": fact_pack, "model": model, "temperature": temperature}
        return ({"executive_summary": "llm", "recommendations": "llm", "limitations": "llm"}, True, None)

    def _stub_docx(**kwargs):
        called["docx"] = kwargs
        Path(kwargs["out_path"]).write_text("docx-stub", encoding="utf-8")

    def _stub_pdf(**kwargs):
        called["pdf"] = kwargs
        Path(kwargs["out_path"]).write_text("pdf-stub", encoding="utf-8")
        return True

    monkeypatch.setattr(assistant_mod, "_core_generate_assistant_report_text_fallback", _stub_fallback)
    monkeypatch.setattr(assistant_mod, "_core_generate_assistant_report_text_llm", _stub_llm)
    monkeypatch.setattr(assistant_mod, "_core_render_assistant_report_docx", _stub_docx)
    monkeypatch.setattr(assistant_mod, "_core_render_assistant_report_pdf", _stub_pdf)

    fact_pack = {"versions": {"data_version": "dv_stub"}}
    narrative = assistant_mod.generate_report_text_fallback(fact_pack)
    llm_narrative, llm_used, llm_err = assistant_mod.generate_report_text_llm(fact_pack, model="gpt-stub", temperature=0.1)
    assistant_mod._render_docx(
        fact_pack=fact_pack,
        narrative=narrative,
        out_path=tmp_path / "report.docx",
        report_version="report_stub",
        llm_used=False,
    )
    pdf_ok = assistant_mod._render_pdf(
        narrative=llm_narrative,
        fact_pack=fact_pack,
        out_path=tmp_path / "report.pdf",
        report_version="report_stub",
        llm_used=llm_used,
    )

    assert narrative["executive_summary"] == "ok"
    assert llm_used is True
    assert llm_err is None
    assert called["fallback"] == fact_pack
    assert called["llm"]["model"] == "gpt-stub"
    assert called["llm"]["temperature"] == 0.1
    assert called["docx"]["report_version"] == "report_stub"
    assert called["pdf"]["llm_used"] is True
    assert pdf_ok is True
    assert (tmp_path / "report.docx").exists()
    assert (tmp_path / "report.pdf").exists()
