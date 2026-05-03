from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from core.application.refactor_verify_result import make_operation_failed_result


_VERIFY_ACTION = "verify_refactor"
_UPDATE_ACTION = "update_golden"


def _error_reason(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, FileNotFoundError):
        return "missing_path", str(exc)
    if isinstance(exc, ValueError):
        return "validation_error", str(exc)
    if isinstance(exc, RuntimeError):
        return "runtime_error", str(exc)
    return "unexpected_error", f"{type(exc).__name__}: {exc}"


def execute_refactor_verify_action(
    *,
    action_name: str,
    operation: Callable[[], dict[str, Any]],
    success_builder: Callable[[dict[str, Any]], dict[str, Any]],
    golden_root: Path,
    report_root: Path | None = None,
) -> dict[str, Any]:
    try:
        payload = operation()
    except Exception as exc:
        error_code, reason = _error_reason(exc)
        return make_operation_failed_result(
            action_name=action_name,
            error_type=type(exc).__name__,
            error_code=error_code,
            reason=reason,
            golden_manifest=str((golden_root / "manifest.json").resolve()),
            report_root=str(report_root.resolve()) if report_root is not None else None,
        )
    return success_builder(payload)


__all__ = [
    "execute_refactor_verify_action",
    "_VERIFY_ACTION",
    "_UPDATE_ACTION",
]
