from __future__ import annotations

from typing import Any


def make_update_blocked_result(*, reason: str) -> dict[str, Any]:
    return {
        "ok": False,
        "exit_code": 2,
        "status": "VERIFY_REFACTOR_UPDATE_BLOCKED",
        "reason": reason,
    }


def make_golden_updated_result(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "exit_code": 0,
        "status": "VERIFY_REFACTOR_GOLDEN_UPDATED",
        **payload,
    }


def make_verify_execution_result(payload: dict[str, Any]) -> dict[str, Any]:
    ok = bool(payload.get("ok"))
    return {
        "ok": ok,
        "exit_code": 0 if ok else 2,
        "status": "VERIFY_REFACTOR_OK" if ok else "VERIFY_REFACTOR_FAILED",
        **payload,
    }


def make_operation_failed_result(
    *,
    action_name: str,
    error_type: str,
    error_code: str,
    reason: str,
    golden_manifest: str,
    report_root: str | None = None,
) -> dict[str, Any]:
    return {
        "ok": False,
        "exit_code": 2,
        "status": "VERIFY_REFACTOR_FAILED",
        "action": action_name,
        "error_type": error_type,
        "error_code": error_code,
        "reason": reason,
        "golden_manifest": golden_manifest,
        "report_root": report_root or "NA",
        "report_json": "NA",
        "report_md": "NA",
        "scenarios": [],
    }


def render_verify_refactor_cli_lines(result: dict[str, Any]) -> list[str]:
    lines = [str(result["status"])]
    if result["status"] == "VERIFY_REFACTOR_UPDATE_BLOCKED":
        lines.append(f"reason={result['reason']}")
        return lines

    if result["status"] == "VERIFY_REFACTOR_GOLDEN_UPDATED":
        lines.append(f"golden_root={result['golden_root']}")
        lines.append(f"manifest_path={result['manifest_path']}")
        lines.append(f"updated_scenarios={','.join(result['updated_scenarios'])}")
        return lines

    if result.get("action"):
        lines.append(f"action={result['action']}")
    if result.get("error_type"):
        lines.append(f"error_type={result['error_type']}")
    if result.get("error_code"):
        lines.append(f"error_code={result['error_code']}")
    if result.get("reason"):
        lines.append(f"reason={result['reason']}")
    lines.append(f"golden_manifest={result['golden_manifest']}")
    if result.get("status") == "VERIFY_REFACTOR_FAILED" and result.get("report_root") and result.get("report_root") != "NA":
        lines.append(f"report_root={result['report_root']}")
    lines.append(f"report_json={result['report_json']}")
    lines.append(f"report_md={result['report_md']}")
    for row in result.get("scenarios", []):
        lines.append(
            "scenario={scenario} ok={ok} compared_files={compared_files} differences={differences}".format(
                scenario=row["scenario"],
                ok=row["ok"],
                compared_files=row["compared_files"],
                differences=row["differences"],
            )
        )
    return lines


__all__ = [
    "make_golden_updated_result",
    "make_operation_failed_result",
    "make_update_blocked_result",
    "make_verify_execution_result",
    "render_verify_refactor_cli_lines",
]
