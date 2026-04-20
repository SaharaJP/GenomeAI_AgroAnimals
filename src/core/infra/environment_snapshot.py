from __future__ import annotations

import importlib.metadata as metadata
import json
import platform
import re
import sys
import tomllib
from pathlib import Path


_REQ_NAME_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_test_environment_policy_path() -> Path:
    return repo_root() / "configs" / "compat" / "test_environment_policy_v1.json"


def load_test_environment_policy(path: Path | str | None = None) -> dict[str, object]:
    policy_path = Path(path) if path is not None else default_test_environment_policy_path()
    return json.loads(policy_path.read_text(encoding="utf-8"))


def load_pyproject_data(path: Path | str | None = None) -> dict[str, object]:
    pyproject_path = Path(path) if path is not None else repo_root() / "pyproject.toml"
    return tomllib.loads(pyproject_path.read_text(encoding="utf-8"))


def requirement_name(requirement: str) -> str:
    text = requirement.strip()
    if text.startswith("#"):
        raise ValueError(f"Comment is not a requirement: {requirement!r}")
    if ";" in text:
        text = text.split(";", 1)[0].strip()
    if "[" in text:
        text = text.split("[", 1)[0].strip()
    match = _REQ_NAME_RE.match(text)
    if match is None:
        raise ValueError(f"Cannot parse requirement name from: {requirement!r}")
    return match.group(1)


def declared_dependency_specs(pyproject: dict[str, object] | None = None) -> dict[str, dict[str, object]]:
    data = pyproject or load_pyproject_data()
    project = data.get("project", {}) if isinstance(data, dict) else {}
    dependencies = project.get("dependencies", []) if isinstance(project, dict) else []
    optional_dependencies = project.get("optional-dependencies", {}) if isinstance(project, dict) else {}

    declared: dict[str, dict[str, object]] = {}
    for requirement in dependencies:
        name = requirement_name(str(requirement)).lower()
        declared[name] = {
            "requirement": str(requirement),
            "group": "runtime",
        }

    if isinstance(optional_dependencies, dict):
        for group_name, items in optional_dependencies.items():
            for requirement in items:
                name = requirement_name(str(requirement)).lower()
                declared[name] = {
                    "requirement": str(requirement),
                    "group": f"optional:{group_name}",
                }
    return declared



def installed_version(distribution_name: str) -> str | None:
    try:
        return metadata.version(distribution_name)
    except metadata.PackageNotFoundError:
        return None


def build_test_environment_snapshot(policy_path: Path | str | None = None) -> dict[str, object]:
    policy = load_test_environment_policy(policy_path)
    pyproject = load_pyproject_data()
    declared = declared_dependency_specs(pyproject)

    packages_payload: list[dict[str, object]] = []
    for item in policy.get("packages", []):
        if not isinstance(item, dict):
            continue
        package_name = str(item["name"])
        lookup_name = str(item.get("distribution", package_name))
        declared_meta = declared.get(package_name.lower(), {})
        packages_payload.append(
            {
                "name": package_name,
                "distribution": lookup_name,
                "installed_version": installed_version(lookup_name),
                "declared_requirement": declared_meta.get("requirement"),
                "declared_group": declared_meta.get("group"),
                "role": item.get("role"),
                "upgrade_strategy": item.get("upgrade_strategy"),
                "notes": item.get("notes", ""),
            }
        )

    return {
        "version": 1,
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": sys.executable,
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "requires_python": pyproject.get("project", {}).get("requires-python"),
        "policy_version": policy.get("version"),
        "packages": packages_payload,
    }


__all__ = [
    "build_test_environment_snapshot",
    "declared_dependency_specs",
    "default_test_environment_policy_path",
    "installed_version",
    "load_pyproject_data",
    "load_test_environment_policy",
    "repo_root",
    "requirement_name",
]
