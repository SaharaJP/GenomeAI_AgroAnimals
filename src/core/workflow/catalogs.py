from __future__ import annotations

from typing import Any, Optional

from core.workflow.policies import load_workflow_yaml, workflow_project_root


def workflow_stage_catalog() -> dict[str, Any]:
    """Canonical stage catalog for both UI layers.

    Keeps config loading in core and preserves legacy defaults when configs are
    absent or malformed.
    """

    cfg = load_workflow_yaml(workflow_project_root() / "configs" / "workflow_v2" / "stages.yaml")
    raw_items = list(cfg.get("stages") or [])
    stages: list[dict[str, Any]] = []
    keys: list[str] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        key = str(raw.get("key") or "").strip().lower()
        if not key:
            continue
        item = dict(raw)
        item["key"] = key
        stages.append(item)
        if key not in keys:
            keys.append(key)
    if not stages:
        stages = [
            {"key": "triage", "title": "Triage"},
            {"key": "plan", "title": "Plan"},
            {"key": "execute", "title": "Execute"},
            {"key": "review", "title": "Review"},
        ]
        keys = [str(item["key"]) for item in stages]

    default_stage_open = str(cfg.get("default_stage_open") or (keys[0] if keys else "triage")).strip().lower()
    if default_stage_open not in keys:
        default_stage_open = keys[0] if keys else "triage"

    done_stage = str(cfg.get("done_stage") or "done").strip().lower() or "done"
    cancelled_stage = str(cfg.get("cancelled_stage") or "cancelled").strip().lower() or "cancelled"

    return {
        "default_stage_open": default_stage_open,
        "stages": stages,
        "stage_keys": tuple(keys),
        "done_stage": done_stage,
        "cancelled_stage": cancelled_stage,
    }


def workflow_stage_keys() -> tuple[str, ...]:
    return tuple(workflow_stage_catalog().get("stage_keys") or ())


def workflow_default_stage() -> str:
    return str(workflow_stage_catalog().get("default_stage_open") or "triage")


def workflow_stage_options(*, include_blank: bool = False, include_closed: bool = False) -> tuple[str, ...]:
    values = list(workflow_stage_keys())
    if include_closed:
        catalog = workflow_stage_catalog()
        for extra in (catalog.get("done_stage"), catalog.get("cancelled_stage")):
            v = str(extra or "").strip().lower()
            if v and v not in values:
                values.append(v)
    if include_blank:
        return tuple([""] + values)
    return tuple(values)


def workflow_team_catalog() -> dict[str, Any]:
    cfg = load_workflow_yaml(workflow_project_root() / "configs" / "workflow_v2" / "teams.yaml")
    raw_items = list(cfg.get("teams") or [])
    teams: list[dict[str, Any]] = []
    keys: list[str] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        key = str(raw.get("key") or "").strip()
        if not key:
            continue
        item = dict(raw)
        item["key"] = key
        teams.append(item)
        if key not in keys:
            keys.append(key)
    return {
        "teams": teams,
        "team_keys": tuple(keys),
    }


def workflow_team_keys(*, include_blank: bool = False) -> tuple[str, ...]:
    keys = list(workflow_team_catalog().get("team_keys") or ())
    if include_blank:
        return tuple([""] + keys)
    return tuple(keys)


def workflow_ui_catalogs_use_case(*, current_stage: Optional[str] = None) -> dict[str, Any]:
    """Single core payload for workflow filters/options across both UIs."""

    stage_catalog = workflow_stage_catalog()
    team_catalog = workflow_team_catalog()
    current = str(current_stage or "").strip().lower()
    if current and current not in set(workflow_stage_options(include_closed=True)):
        current = ""
    return {
        "stages": stage_catalog,
        "teams": team_catalog,
        "stage_options": workflow_stage_options(include_blank=True),
        "team_options": workflow_team_keys(include_blank=True),
        "current_stage": current or None,
    }


__all__ = [
    "workflow_default_stage",
    "workflow_stage_catalog",
    "workflow_stage_keys",
    "workflow_stage_options",
    "workflow_team_catalog",
    "workflow_team_keys",
    "workflow_ui_catalogs_use_case",
]
