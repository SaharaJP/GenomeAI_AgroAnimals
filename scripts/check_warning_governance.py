#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from core.infra.warning_governance import build_warning_governance_report  # noqa: E402


def _render_markdown(report: dict[str, object]) -> str:
    totals = report.get("totals") or {}
    lines = [
        "# Warning governance report",
        "",
        f"- status: `{report.get('status')}`",
        f"- total warnings: `{totals.get('total', 0)}`",
        f"- by origin: `{json.dumps(totals.get('by_origin', {}), ensure_ascii=False, sort_keys=True)}`",
        f"- by source: `{json.dumps(totals.get('by_source', {}), ensure_ascii=False, sort_keys=True)}`",
        f"- by dependency: `{json.dumps(totals.get('by_dependency', {}), ensure_ascii=False, sort_keys=True)}`",
        "",
        "## Source files",
        "",
    ]
    for item in report.get("source_files", []):
        lines.append(
            f"- {item.get('source')}: exists={item.get('exists')} warnings={item.get('warnings')} path=`{item.get('path')}`"
        )
    lines.extend(["", "## Violations", ""])
    for key in ("denylisted", "unexpected", "over_budget"):
        items = list(report.get(key, []))
        lines.append(f"### {key}")
        if not items:
            lines.append("- none")
        else:
            lines.extend(f"- {item}" for item in items)
        lines.append("")
    lines.extend(["## Matched counts", ""])
    matched_counts = report.get("matched_counts") or {}
    if matched_counts:
        for name, count in matched_counts.items():
            lines.append(f"- {name}: {count}")
    else:
        lines.append("- none")
    lines.extend(["", "## Dependency policy summary", ""])
    dep_policy = (report.get("dependency_policy") or {}).get("summary") or {}
    for key, value in dep_policy.items():
        lines.append(f"- {key}: `{json.dumps(value, ensure_ascii=False)}`")
    if report.get("failure_message"):
        lines.extend(["", "## Failure message", "", "```", str(report["failure_message"]), "```"])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check warning governance across pytest/smoke logs")
    parser.add_argument("--pytest-log", default=None)
    parser.add_argument("--web-smoke-log", default=None)
    parser.add_argument("--verify-log", default=None)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-md", required=True)
    args = parser.parse_args(argv)

    report = build_warning_governance_report(
        {
            "pytest": args.pytest_log,
            "web_smoke": args.web_smoke_log,
            "verify_refactor": args.verify_log,
        }
    )
    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_md.write_text(_render_markdown(report), encoding="utf-8")

    if report.get("status") != "ok":
        print(f"WARNING_GOVERNANCE_FAILED {output_json}", file=sys.stderr)
        failure_message = str(report.get("failure_message") or "warning governance failed")
        print(failure_message, file=sys.stderr)
        return 1

    print(f"WARNING_GOVERNANCE_OK {output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
