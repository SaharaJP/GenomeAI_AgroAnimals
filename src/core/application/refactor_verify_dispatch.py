from __future__ import annotations

from core.application.refactor_verify_command import selected_scenarios
from core.application.refactor_verify_errors import _UPDATE_ACTION, _VERIFY_ACTION
from core.application.refactor_verify_result import (
    make_golden_updated_result,
    make_verify_execution_result,
)
from core.domain import VerifyRefactorCommand, VerifyRefactorDispatch
from core.infra.refactor_verify_service import (
    perform_update_golden,
    perform_verify_refactor,
)


def build_verify_refactor_dispatch(command: VerifyRefactorCommand) -> VerifyRefactorDispatch:
    scenario_names = selected_scenarios(command)
    if command.update_golden:
        return VerifyRefactorDispatch(
            action_name=_UPDATE_ACTION,
            operation=lambda: perform_update_golden(
                project_root=command.project_root,
                golden_root=command.golden_root,
                scenario_names=scenario_names,
            ),
            success_builder=make_golden_updated_result,
            golden_root=command.golden_root,
            report_root=None,
        )

    return VerifyRefactorDispatch(
        action_name=_VERIFY_ACTION,
        operation=lambda: perform_verify_refactor(
            project_root=command.project_root,
            golden_root=command.golden_root,
            scenario_names=scenario_names,
            report_root=command.report_root,
        ),
        success_builder=make_verify_execution_result,
        golden_root=command.golden_root,
        report_root=command.report_root,
    )


__all__ = ["VerifyRefactorDispatch", "build_verify_refactor_dispatch"]
