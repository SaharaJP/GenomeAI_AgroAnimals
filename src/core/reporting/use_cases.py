from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, MutableMapping, Optional, Sequence

from core.reporting.report_builder import persist_fact_pack_bundle, write_markdown_report_bundle


JsonDict = Dict[str, Any]


def run_assistant_report_use_case(
    *,
    artifacts_root: Path,
    data_version: str,
    qc_run: str,
    model_version: str,
    scoring_run: str,
    mode: str = "fallback",
    report_version: Optional[str] = None,
    make_pdf: bool = True,
    llm_model: Optional[str] = None,
    build_fact_pack: Callable[..., MutableMapping[str, Any]],
    generate_report_text_fallback: Callable[[JsonDict], JsonDict],
    generate_report_text_llm: Callable[[JsonDict], tuple[JsonDict, bool, Optional[str]]],
    render_docx: Callable[..., Any],
    render_pdf: Callable[..., bool],
    utc_now_iso: Callable[[], str],
    read_json: Callable[[Path], JsonDict],
    write_json: Callable[[Path, Any], Any],
    generate_run_id: Callable[..., str],
    get_run_root: Callable[..., Path],
    copy_tree_into_run: Callable[..., Any],
    write_run_manifest: Callable[..., Any],
    write_checksums: Callable[..., Any],
) -> Dict[str, Any]:
    """Core orchestration for assistant report generation.

    Legacy modules provide concrete builders/renderers. This keeps runtime behavior
    stable while moving orchestration into core.
    """
    artifacts_root = Path(artifacts_root)
    base = artifacts_root / data_version
    report_ver = report_version or generate_run_id(prefix="report")
    out_dir = base / "reports" / report_ver
    exports_dir = out_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    fact_pack = build_fact_pack(
        artifacts_root=artifacts_root,
        data_version=data_version,
        qc_run=qc_run,
        model_version=model_version,
        scoring_run=scoring_run,
    )

    persisted = persist_fact_pack_bundle(out_dir=out_dir, fact_pack=fact_pack, report_version=report_ver)
    fact_pack_hash = persisted["fact_pack_hash"]

    llm_used = False
    llm_err: Optional[str] = None
    if mode.lower() == "llm":
        narrative, llm_used, llm_err = generate_report_text_llm(fact_pack)
        if not llm_used:
            narrative = generate_report_text_fallback(fact_pack)
    else:
        narrative = generate_report_text_fallback(fact_pack)

    docx_path = exports_dir / "report.docx"
    render_docx(
        fact_pack=fact_pack,
        narrative=narrative,
        out_path=docx_path,
        report_version=report_ver,
        llm_used=llm_used,
    )

    pdf_path = exports_dir / "report.pdf"
    pdf_ok = False
    if make_pdf:
        pdf_ok = render_pdf(
            narrative=narrative,
            fact_pack=fact_pack,
            out_path=pdf_path,
            report_version=report_ver,
            llm_used=llm_used,
        )

    summary = {
        "schema": "genomeai.report_summary.v1",
        "created_at_utc": utc_now_iso(),
        "data_version": data_version,
        "qc_run": qc_run,
        "model_version": model_version,
        "scoring_run": scoring_run,
        "report_version": report_ver,
        "mode_requested": mode.lower(),
        "llm_used": llm_used,
        "inputs": {
            "fact_pack": str((out_dir / "fact_pack.json").resolve()),
            "fact_pack_hash": fact_pack_hash,
            "llm_error": llm_err,
            "playbooks_used": [
                {
                    "target_kind": p.get("target_kind"),
                    "target_type": p.get("target_type"),
                    "farm_id": p.get("farm_id"),
                    "version_id": p.get("version_id"),
                    "source": p.get("source"),
                }
                for p in ((fact_pack.get("playbooks", {}) or {}).get("recommended") or [])
            ],
        },
        "outputs": {
            "report_docx": str(docx_path.resolve()),
            "report_pdf": str(pdf_path.resolve()) if pdf_ok and pdf_path.exists() else "NA",
        },
    }

    write_json(out_dir / "report_summary.json", summary)
    write_json(out_dir / "report_manifest.json", summary)

    meta_dir = base / "metadata"
    meta_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = meta_dir / "report_manifest.json"
    if manifest_path.exists():
        manifest = read_json(manifest_path)
    else:
        manifest = {"schema": "genomeai.report_manifest.v1", "data_version": data_version, "reports": {}, "latest": None}
    manifest["reports"][report_ver] = {
        "created_at_utc": summary["created_at_utc"],
        "mode_requested": summary["mode_requested"],
        "llm_used": summary["llm_used"],
        "report_summary": str((out_dir / "report_summary.json").resolve()),
        "report_docx": summary["outputs"]["report_docx"],
        "report_pdf": summary["outputs"]["report_pdf"],
        "fact_pack": summary["inputs"]["fact_pack"],
        "fact_pack_hash": summary["inputs"]["fact_pack_hash"],
        "versions": {
            "qc_run": qc_run,
            "model_version": model_version,
            "scoring_run": scoring_run,
        },
    }
    manifest["latest"] = report_ver
    write_json(manifest_path, manifest)

    run_root = get_run_root(artifacts_root=artifacts_root, data_version=data_version, run_id=report_ver)
    copy_tree_into_run(src_dir=out_dir, run_root=run_root, subdir="report")
    write_run_manifest(
        run_root=run_root,
        manifest={
            "schema": "genomeai.run_manifest.v1",
            "step": "report",
            "data_version": data_version,
            "run_id": report_ver,
            "created_at": summary["created_at_utc"],
            "status": "DONE",
            "outputs": {
                "legacy_dir": str(out_dir),
                "run_dir": str(run_root / "report"),
                "report_docx": str(exports_dir / "report.docx"),
                "report_pdf": str(exports_dir / "report.pdf") if (exports_dir / "report.pdf").exists() else None,
                "fact_pack_json": str(out_dir / "fact_pack.json"),
            },
            "lineage": {
                "qc_run": qc_run,
                "model_version": model_version,
                "scoring_run": scoring_run,
            },
            "params": {
                "mode": mode,
                "llm_used": llm_used,
            },
        },
    )
    write_checksums(run_root=run_root, include_subdirs=["report"])

    return {
        "ok": True,
        "data_version": data_version,
        "qc_run": qc_run,
        "model_version": model_version,
        "scoring_run": scoring_run,
        "report_version": report_ver,
        "llm_used": llm_used,
        "report_dir": str(out_dir.resolve()),
        "outputs": summary["outputs"],
        "fact_pack": str((out_dir / "fact_pack.json").resolve()),
        "fact_pack_hash": fact_pack_hash,
    }


def run_regular_report_use_case(
    *,
    artifacts_root: Path,
    data_version: str,
    asof_date: str,
    period: str = "daily",
    mode: str = "fallback",
    llm_model: Optional[str] = None,
    report_version: Optional[str] = None,
    build_fact_pack: Callable[..., MutableMapping[str, Any]],
    generate_report_text_fallback: Callable[[JsonDict, str], JsonDict],
    generate_report_text_llm: Callable[[JsonDict, str], tuple[JsonDict, bool, Optional[str]]],
    render_md: Callable[..., Any],
    utc_now_iso: Callable[[], str],
    generate_run_id: Callable[..., str],
    write_json: Callable[[Path, Any], Any],
) -> Dict[str, Any]:
    """Core orchestration for regular markdown report generation."""
    artifacts_root = Path(artifacts_root).resolve()
    dv = str(data_version)
    report_ver = report_version or generate_run_id(prefix="regular_report")
    out_dir = artifacts_root / dv / "reports_regular" / report_ver
    exports_dir = out_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    fact_pack = build_fact_pack(
        artifacts_root=artifacts_root,
        data_version=dv,
        asof_date=asof_date,
        period=period,
        max_rows=20,
    )
    fact_pack.setdefault("versions", {})
    fact_pack["versions"]["report_version"] = report_ver
    persisted = persist_fact_pack_bundle(out_dir=out_dir, fact_pack=fact_pack, report_version=report_ver)
    fact_pack_hash = persisted["fact_pack_hash"]

    llm_used = False
    llm_err: Optional[str] = None
    markdown_by_audience: Dict[str, str] = {}
    for audience in ["director", "ops"]:
        if mode.lower() == "llm":
            narrative, llm_used2, llm_err2 = generate_report_text_llm(fact_pack, audience)
            if not llm_used2:
                narrative = generate_report_text_fallback(fact_pack, audience)
                llm_used2 = False
            llm_used = llm_used or llm_used2
            llm_err = llm_err or llm_err2
        else:
            narrative = generate_report_text_fallback(fact_pack, audience)

        narrative = {
            key: (value.replace("{REPORT_VERSION}", report_ver) if isinstance(value, str) else value)
            for key, value in narrative.items()
        }

        md_path = exports_dir / f"report_{audience}.md"
        render_md(
            narrative=narrative,
            fact_pack=fact_pack,
            out_path=md_path,
            report_version=report_ver,
            audience=audience,
            llm_used=llm_used,
        )
        markdown_by_audience[audience] = md_path.read_text(encoding="utf-8")

    outputs = write_markdown_report_bundle(
        exports_dir=exports_dir,
        markdown_by_audience=markdown_by_audience,
        pdf_titles={aud: f"Regular report ({aud}) {report_ver}" for aud in markdown_by_audience},
    )
    summary = {
        "schema": "genomeai.regular_report_summary.v1",
        "created_at_utc": utc_now_iso(),
        "data_version": dv,
        "model_version": str(fact_pack.get("versions", {}).get("model_version", "NA")),
        "report_version": report_ver,
        "period": str(period),
        "asof_date": str(asof_date),
        "mode_requested": mode.lower(),
        "llm_used": bool(llm_used),
        "inputs": {
            "fact_pack": str((out_dir / "fact_pack.json").resolve()),
            "fact_pack_hash": fact_pack_hash,
            "llm_error": llm_err,
        },
        "outputs": outputs,
    }
    write_json(out_dir / "report_summary.json", summary)

    return {
        "ok": True,
        "data_version": dv,
        "report_version": report_ver,
        "report_dir": str(out_dir),
        "outputs": outputs,
    }


def run_template_report_use_case(
    *,
    artifacts_root: Path,
    data_version: str,
    asof_date: str,
    mode: str,
    report_version: Optional[str],
    generate_run_id: Callable[..., str],
    utc_now_iso: Callable[[], str],
    write_json: Callable[[Path, Any], Any],
    prepare_fact_pack_and_markdown: Callable[..., tuple[MutableMapping[str, Any], Dict[str, str], Dict[str, Any]]],
) -> Dict[str, Any]:
    """Core finalization flow for template-based reports."""
    artifacts_root = Path(artifacts_root).resolve()
    dv = str(data_version)
    report_ver = report_version or generate_run_id(prefix="regular_report")
    out_dir = artifacts_root / dv / "reports_regular" / report_ver
    exports_dir = out_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    fact_pack, markdown_by_audience, summary_inputs = prepare_fact_pack_and_markdown(
        artifacts_root=artifacts_root,
        data_version=dv,
        asof_date=str(asof_date),
        report_version=report_ver,
        out_dir=out_dir,
        exports_dir=exports_dir,
    )

    persist_fact_pack_bundle(out_dir=out_dir, fact_pack=fact_pack, report_version=report_ver)
    outputs = write_markdown_report_bundle(
        exports_dir=exports_dir,
        markdown_by_audience=markdown_by_audience,
        pdf_titles={aud: f"Template report {report_ver}" for aud in markdown_by_audience},
    )
    summary = {
        "schema": "genomeai.template_report_summary.v1",
        "created_at_utc": utc_now_iso(),
        "data_version": dv,
        "report_version": report_ver,
        "template_id": str(((fact_pack.get("template") or {}).get("template_id")) or ""),
        "asof_date": str(asof_date),
        "mode_requested": str(mode),
        "llm_used": False,
        "inputs": summary_inputs,
        "outputs": outputs,
    }
    write_json(out_dir / "report_summary.json", summary)

    return {
        "ok": True,
        "data_version": dv,
        "report_version": report_ver,
        "report_dir": str(out_dir),
        "outputs": outputs,
    }


__all__ = [
    "run_assistant_report_use_case",
    "run_regular_report_use_case",
    "run_template_report_use_case",
]
