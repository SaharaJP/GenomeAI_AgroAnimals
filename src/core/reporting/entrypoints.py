from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from core.reporting.assistant_reporting import (
    generate_assistant_report_text_fallback,
    generate_assistant_report_text_llm,
    render_assistant_report_docx,
    render_assistant_report_pdf,
)
from core.reporting.fact_pack import build_assistant_fact_pack, build_regular_fact_pack
from core.reporting.regular_reporting import (
    generate_regular_report_text_fallback,
    generate_regular_report_text_llm,
    render_regular_report_markdown,
)
from core.reporting.template_reporting import prepare_template_report_artifacts
from core.reporting.use_cases import (
    run_assistant_report_use_case,
    run_regular_report_use_case,
    run_template_report_use_case,
)
from genomeai.versioning import (
    copy_tree_into_run,
    generate_run_id,
    get_run_root,
    write_checksums,
    write_json,
    write_run_manifest,
)


JsonDict = Dict[str, Any]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path) -> JsonDict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_assistant_report(
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
) -> JsonDict:
    """Canonical high-level assistant report entrypoint for UI/CLI adapters."""
    return run_assistant_report_use_case(
        artifacts_root=artifacts_root,
        data_version=data_version,
        qc_run=qc_run,
        model_version=model_version,
        scoring_run=scoring_run,
        mode=mode,
        report_version=report_version,
        make_pdf=make_pdf,
        llm_model=llm_model,
        build_fact_pack=build_assistant_fact_pack,
        generate_report_text_fallback=generate_assistant_report_text_fallback,
        generate_report_text_llm=(
            lambda fact_pack: generate_assistant_report_text_llm(
                fact_pack,
                model=llm_model,
            )
        ),
        render_docx=render_assistant_report_docx,
        render_pdf=render_assistant_report_pdf,
        utc_now_iso=_utc_now_iso,
        read_json=_read_json,
        write_json=write_json,
        generate_run_id=generate_run_id,
        get_run_root=get_run_root,
        copy_tree_into_run=copy_tree_into_run,
        write_run_manifest=write_run_manifest,
        write_checksums=write_checksums,
    )


def run_regular_report(
    *,
    artifacts_root: Path,
    data_version: str,
    asof_date: str,
    period: str = "daily",
    mode: str = "fallback",
    llm_model: Optional[str] = None,
    report_version: Optional[str] = None,
) -> JsonDict:
    """Canonical high-level regular report entrypoint for UI/CLI adapters."""
    return run_regular_report_use_case(
        artifacts_root=artifacts_root,
        data_version=data_version,
        asof_date=asof_date,
        period=period,
        mode=mode,
        llm_model=llm_model,
        report_version=report_version,
        build_fact_pack=build_regular_fact_pack,
        generate_report_text_fallback=(
            lambda fact_pack, audience: generate_regular_report_text_fallback(
                fact_pack,
                audience=audience,
            )
        ),
        generate_report_text_llm=(
            lambda fact_pack, audience: generate_regular_report_text_llm(
                fact_pack,
                audience=audience,
                model=llm_model,
            )
        ),
        render_md=render_regular_report_markdown,
        utc_now_iso=_utc_now_iso,
        generate_run_id=generate_run_id,
        write_json=write_json,
    )


def run_template_report(
    *,
    artifacts_root: Path,
    data_version: str,
    asof_date: str,
    template: dict[str, Any],
    inputs: Optional[dict[str, Any]] = None,
    mode: str = "fallback",
    llm_model: Optional[str] = None,
    report_version: Optional[str] = None,
    max_rows: int = 20,
    options_override: Optional[dict[str, Any]] = None,
) -> JsonDict:
    """Canonical high-level template report entrypoint for UI/CLI adapters."""
    _ = llm_model
    return run_template_report_use_case(
        artifacts_root=artifacts_root,
        data_version=data_version,
        asof_date=asof_date,
        mode=mode,
        report_version=report_version,
        generate_run_id=generate_run_id,
        utc_now_iso=_utc_now_iso,
        write_json=write_json,
        prepare_fact_pack_and_markdown=(
            lambda **kwargs: prepare_template_report_artifacts(
                **kwargs,
                template=template,
                inputs=inputs,
                mode=mode,
                max_rows=max_rows,
                options_override=options_override,
            )
        ),
    )
