from __future__ import annotations

from core.domain import VerifyRefactorCommand


def parse_scenarios_arg(raw: str | None) -> list[str]:
    if raw is None:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in str(raw).split(","):
        scenario = item.strip()
        if not scenario or scenario in seen:
            continue
        seen.add(scenario)
        out.append(scenario)
    return out


def selected_scenarios(command: VerifyRefactorCommand) -> list[str] | None:
    selected = list(command.scenario_names)
    return selected or None


__all__ = [
    "VerifyRefactorCommand",
    "parse_scenarios_arg",
    "selected_scenarios",
]
