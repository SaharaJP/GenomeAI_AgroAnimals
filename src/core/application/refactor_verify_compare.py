from __future__ import annotations

import difflib
from dataclasses import asdict
from pathlib import Path
from typing import Any

from core.domain import FileDiff, ScenarioReport, VerifyReport


def compare_snapshot_dirs(expected_dir: Path, actual_dir: Path) -> ScenarioReport:
    expected_files = sorted(str(p.relative_to(expected_dir)).replace("\\", "/") for p in expected_dir.rglob("*") if p.is_file())
    actual_files = sorted(str(p.relative_to(actual_dir)).replace("\\", "/") for p in actual_dir.rglob("*") if p.is_file())
    differences: list[FileDiff] = []

    missing = sorted(set(expected_files) - set(actual_files))
    extra = sorted(set(actual_files) - set(expected_files))
    for rel in missing:
        differences.append(FileDiff(file=rel, kind="missing", detail="Файл отсутствует в текущем snapshot."))
    for rel in extra:
        differences.append(FileDiff(file=rel, kind="extra", detail="Файл появился в текущем snapshot, но отсутствует в golden."))

    common = sorted(set(expected_files) & set(actual_files))
    for rel in common:
        exp_text = (expected_dir / rel).read_text(encoding="utf-8")
        act_text = (actual_dir / rel).read_text(encoding="utf-8")
        if exp_text == act_text:
            continue
        diff_lines = list(
            difflib.unified_diff(
                exp_text.splitlines(),
                act_text.splitlines(),
                fromfile=f"golden/{rel}",
                tofile=f"actual/{rel}",
                lineterm="",
                n=2,
            )
        )
        snippet = "\n".join(diff_lines[:40])
        differences.append(FileDiff(file=rel, kind="content", detail=snippet))

    return ScenarioReport(
        scenario=expected_dir.parent.name,
        ok=not differences,
        compared_files=len(common),
        differences=differences,
        expected_snapshot=str(expected_dir.resolve()),
        actual_snapshot=str(actual_dir.resolve()),
    )


def render_markdown(report: VerifyReport) -> str:
    lines = [
        "# verify_refactor report",
        "",
        f"Сформировано: {report.created_at_utc}",
        f"Golden root: `{report.golden_root}`",
        "",
    ]
    for scenario in report.scenarios:
        status = "PASS" if scenario.ok else "FAIL"
        lines.append(f"## {scenario.scenario}: {status}")
        lines.append("")
        lines.append(f"Сравнено файлов: {scenario.compared_files}")
        if scenario.ok:
            lines.append("Расхождений нет.")
            lines.append("")
            continue
        lines.append(f"Найдено расхождений: {len(scenario.differences)}")
        lines.append("")
        for diff in scenario.differences:
            lines.append(f"### {diff.kind}: `{diff.file}`")
            lines.append("")
            lines.append("```diff")
            lines.append(diff.detail)
            lines.append("```")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def verify_report_payload(report: VerifyReport) -> dict[str, Any]:
    return {
        "schema": report.schema,
        "created_at_utc": report.created_at_utc,
        "golden_root": report.golden_root,
        "ok": report.ok,
        "scenarios": [
            {
                **{k: v for k, v in asdict(s).items() if k != "differences"},
                "differences": [asdict(d) for d in s.differences],
            }
            for s in report.scenarios
        ],
    }


__all__ = [
    "FileDiff",
    "ScenarioReport",
    "VerifyReport",
    "compare_snapshot_dirs",
    "render_markdown",
    "verify_report_payload",
]
