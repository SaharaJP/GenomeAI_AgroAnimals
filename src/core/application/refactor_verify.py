from __future__ import annotations

from core.application.refactor_verify_command import (
    VerifyRefactorCommand,
    parse_scenarios_arg,
)
from core.application.refactor_verify_dispatch import build_verify_refactor_dispatch
from core.application.refactor_verify_errors import execute_refactor_verify_action
from core.application.refactor_verify_result import (
    make_update_blocked_result,
    render_verify_refactor_cli_lines,
)


def execute_verify_refactor(command: VerifyRefactorCommand) -> dict[str, object]:
    if command.update_golden and not command.confirm_update_golden:
        return make_update_blocked_result(
            reason="manual confirmation required; pass --i-understand-update-golden"
        )

    dispatch = build_verify_refactor_dispatch(command)
    return execute_refactor_verify_action(
        action_name=dispatch.action_name,
        operation=dispatch.operation,
        success_builder=dispatch.success_builder,
        golden_root=dispatch.golden_root,
        report_root=dispatch.report_root,
    )


__all__ = [
    "VerifyRefactorCommand",
    "execute_verify_refactor",
    "parse_scenarios_arg",
    "render_verify_refactor_cli_lines",
]
