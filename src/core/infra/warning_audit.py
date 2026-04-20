from __future__ import annotations

import json
import re
import sysconfig
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class ParsedWarningEntry:
    filename: str
    lineno: int
    category: str
    message: str
    origin: str
    package: str | None = None


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_dependency_inventory_path() -> Path:
    return repo_root() / "configs" / "compat" / "dependency_warning_inventory_v1.json"


def classify_warning_filename(filename: str | Path) -> tuple[str, str | None]:
    text = str(filename)
    path = Path(text)

    try:
        resolved = path.resolve(strict=False)
    except OSError:
        resolved = path

    root = repo_root()
    try:
        resolved.relative_to(root)
        return "project", None
    except ValueError:
        pass

    project_markers = ("src", "tests", "web_cabinet", "web_app", "mobile_android", "configs", "docs")
    resolved_parts = list(resolved.parts)
    for marker in project_markers:
        if marker not in resolved_parts:
            continue
        candidate = root / Path(*resolved_parts[resolved_parts.index(marker):])
        if candidate.exists():
            return "project", None

    text_lower = str(resolved).replace('\\', '/').lower()
    for marker in ("/site-packages/", "/dist-packages/"):
        if marker in text_lower:
            after = text_lower.split(marker, 1)[1]
            package = after.split('/', 1)[0].split('-', 1)[0]
            return "dependency", package or None

    stdlib_path = sysconfig.get_paths().get("stdlib")
    if stdlib_path:
        try:
            resolved.relative_to(Path(stdlib_path))
            return "stdlib", None
        except ValueError:
            pass

    return "unknown", None


_WARNING_LINE_RE = re.compile(
    r"^\s*(?P<filename>.+?):(?P<lineno>\d+):\s+(?P<category>[A-Za-z_][A-Za-z0-9_]*Warning):\s+(?P<message>.+?)\s*$"
)


def parse_pytest_warning_log(log_text: str) -> list[ParsedWarningEntry]:
    entries: list[ParsedWarningEntry] = []
    for line in log_text.splitlines():
        match = _WARNING_LINE_RE.match(line)
        if not match:
            continue
        origin, package = classify_warning_filename(match.group("filename"))
        entries.append(
            ParsedWarningEntry(
                filename=match.group("filename"),
                lineno=int(match.group("lineno")),
                category=match.group("category"),
                message=match.group("message"),
                origin=origin,
                package=package,
            )
        )
    return entries


def build_warning_origin_report(entries: Iterable[ParsedWarningEntry]) -> dict[str, object]:
    items = list(entries)
    by_origin: dict[str, int] = {}
    by_dependency: dict[str, int] = {}
    for item in items:
        by_origin[item.origin] = by_origin.get(item.origin, 0) + 1
        if item.origin == "dependency":
            key = item.package or "unknown"
            by_dependency[key] = by_dependency.get(key, 0) + 1
    return {
        "total": len(items),
        "by_origin": dict(sorted(by_origin.items())),
        "by_dependency": dict(sorted(by_dependency.items())),
        "entries": [asdict(item) for item in items],
    }


def load_dependency_warning_inventory(path: Path | str | None = None) -> dict[str, object]:
    inventory_path = Path(path) if path is not None else default_dependency_inventory_path()
    return json.loads(inventory_path.read_text(encoding="utf-8"))


__all__ = [
    "ParsedWarningEntry",
    "build_warning_origin_report",
    "classify_warning_filename",
    "default_dependency_inventory_path",
    "load_dependency_warning_inventory",
    "parse_pytest_warning_log",
    "repo_root",
]
