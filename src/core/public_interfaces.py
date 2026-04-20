from __future__ import annotations

import argparse
import importlib
import inspect
import json
from pathlib import Path
from typing import Any


PUBLIC_FUNCTION_PATHS: tuple[str, ...] = (
    "genomeai.cli.build_parser",
    "genomeai.cli.main",
    "core.security.load_permission_matrix",
    "core.security.ensure_permissions",
    "core.security.resolve_role_permissions",
    "core.audit.load_audit_retention_config",
    "core.audit.write_audit",
    "core.audit.list_audit",
    "web_cabinet.jobs_v2.load_job_runner_config",
    "core.config.validate_startup_config_bundle",
)

PUBLIC_DEPRECATIONS: tuple[dict[str, str], ...] = (
    {
        "kind": "cli_alias",
        "name": "verify-refactor",
        "replacement": "verify_refactor",
        "status": "deprecated",
    },
    {
        "kind": "import",
        "name": "genomeai.application",
        "replacement": "core.application",
        "status": "deprecated",
    },
    {
        "kind": "import",
        "name": "web_cabinet.audit",
        "replacement": "core.audit",
        "status": "deprecated",
    },
    {
        "kind": "import",
        "name": "web_cabinet.rbac",
        "replacement": "core.security",
        "status": "deprecated",
    },
)


def _collect_parser_commands(parser: argparse.ArgumentParser, prefix: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = []
    for action in parser._actions:
        if not isinstance(action, argparse._SubParsersAction):
            continue
        for name, child in action.choices.items():
            command_path = prefix + (name,)
            options: list[str] = []
            for child_action in child._actions:
                if isinstance(child_action, argparse._SubParsersAction):
                    continue
                flags = list(child_action.option_strings or [])
                if not flags and child_action.dest != "help":
                    flags = [str(child_action.dest)]
                options.extend(flags)
            commands.append(
                {
                    "command": " ".join(command_path),
                    "options": sorted(dict.fromkeys(options)),
                }
            )
            commands.extend(_collect_parser_commands(child, command_path))
    return commands


def collect_cli_contract() -> dict[str, Any]:
    from genomeai.cli import build_parser

    parser = build_parser()
    rows = _collect_parser_commands(parser)
    uniq: dict[str, dict[str, Any]] = {}
    for row in rows:
        uniq[row["command"]] = row
    return {
        "commands": [uniq[key] for key in sorted(uniq)],
    }


def collect_api_contract() -> dict[str, Any]:
    from web_cabinet.app import app

    rows: dict[tuple[str, tuple[str, ...]], dict[str, Any]] = {}
    for route in app.routes:
        path = getattr(route, "path", None)
        if not path:
            continue
        methods = tuple(sorted(m for m in (getattr(route, "methods", set()) or set()) if m != "HEAD"))
        rows[(str(path), methods)] = {"path": str(path), "methods": list(methods)}
    return {"routes": [rows[key] for key in sorted(rows, key=lambda item: (item[0], item[1]))]}



def _resolve_dotted_path(path: str) -> Any:
    module_name, attr_name = path.rsplit(".", 1)
    module = importlib.import_module(module_name)
    return getattr(module, attr_name)


def collect_python_function_contract(paths: tuple[str, ...] = PUBLIC_FUNCTION_PATHS) -> dict[str, Any]:
    functions = []
    for dotted_path in paths:
        obj = _resolve_dotted_path(dotted_path)
        functions.append(
            {
                "path": dotted_path,
                "signature": str(inspect.signature(obj)),
            }
        )
    return {"functions": functions}


def collect_public_interfaces_contract(project_root: str | Path = ".") -> dict[str, Any]:
    return {
        "version": 1,
        "cli": collect_cli_contract(),
        "api": collect_api_contract(),
        "python": collect_python_function_contract(),
        "deprecations": list(PUBLIC_DEPRECATIONS),
    }


def load_public_interfaces_snapshot(path: str | Path = "docs/public_interfaces.json") -> dict[str, Any]:
    snapshot_path = Path(path)
    return json.loads(snapshot_path.read_text(encoding="utf-8"))


__all__ = [
    "PUBLIC_DEPRECATIONS",
    "PUBLIC_FUNCTION_PATHS",
    "collect_api_contract",
    "collect_cli_contract",
    "collect_public_interfaces_contract",
    "collect_python_function_contract",
    "load_public_interfaces_snapshot",
]
