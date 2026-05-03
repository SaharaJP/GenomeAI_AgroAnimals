from __future__ import annotations

from core.reporting.assistant_reporting import (
    generate_assistant_report_text_fallback,
    generate_assistant_report_text_llm,
    render_assistant_report_docx,
    render_assistant_report_pdf,
)
from core.reporting.entrypoints import (
    run_assistant_report,
    run_regular_report,
    run_template_report,
)
from core.reporting.fact_pack import (
    build_assistant_fact_pack,
    build_regular_fact_pack,
)
from core.reporting.regular_reporting import (
    generate_regular_report_text_fallback,
    generate_regular_report_text_llm,
    render_regular_report_markdown,
)
from core.reporting.report_builder import (
    persist_fact_pack_bundle,
    render_html_from_md,
    render_pdf_simple,
    write_markdown_report_bundle,
)
from core.reporting.template_reporting import (
    prepare_template_report_artifacts,
    sanitize_template,
)
from core.reporting.use_cases import (
    run_assistant_report_use_case,
    run_regular_report_use_case,
    run_template_report_use_case,
)

__all__ = [
    "run_assistant_report",
    "run_regular_report",
    "run_template_report",
    "generate_assistant_report_text_fallback",
    "generate_assistant_report_text_llm",
    "render_assistant_report_docx",
    "render_assistant_report_pdf",
    "build_assistant_fact_pack",
    "build_regular_fact_pack",
    "generate_regular_report_text_fallback",
    "generate_regular_report_text_llm",
    "render_regular_report_markdown",
    "prepare_template_report_artifacts",
    "sanitize_template",
    "persist_fact_pack_bundle",
    "render_html_from_md",
    "render_pdf_simple",
    "write_markdown_report_bundle",
    "run_assistant_report_use_case",
    "run_regular_report_use_case",
    "run_template_report_use_case",
]
