from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Mapping

from core.infra.deprecation_policy import DeprecationPolicy, DeprecationRule, load_deprecation_policy
from core.infra.warning_audit import ParsedWarningEntry, build_warning_origin_report, parse_pytest_warning_log


@dataclass(frozen=True)
class WarningGovernanceRule:
    name: str
    kind: str
    origin: str | None = None
    category_name: str | None = None
    category_regex: str | None = None
    message_regex: str = r".*"
    package: str | None = None
    filename_regex: str | None = None
    max_count: int = 1
    escalation: str = ""
    notes: str = ""

    def matches(self, entry: ParsedWarningEntry) -> bool:
        if self.origin is not None and entry.origin != self.origin:
            return False
        if self.category_name is not None and entry.category != self.category_name:
            return False
        if self.category_regex is not None and re.search(self.category_regex, entry.category) is None:
            return False
        if self.package is not None and entry.package != self.package:
            return False
        if self.filename_regex is not None and re.search(self.filename_regex, entry.filename) is None:
            return False
        return re.search(self.message_regex, entry.message) is not None


@dataclass(frozen=True)
class WarningEvidence:
    source: str
    entry: ParsedWarningEntry


@dataclass(frozen=True)
class WarningGovernancePolicy:
    version: int
    scope: str
    dependency_policy_path: str
    allowlist: tuple[WarningGovernanceRule, ...]
    denylist: tuple[WarningGovernanceRule, ...]


@dataclass(frozen=True)
class WarningGovernanceReport:
    total: int
    by_origin: dict[str, int]
    by_source: dict[str, int]
    by_dependency: dict[str, int]
    matched_counts: dict[str, int]
    unexpected: tuple[str, ...]
    over_budget: tuple[str, ...]
    denylisted: tuple[str, ...]
    entries: tuple[dict[str, object], ...]
    source_files: tuple[dict[str, object], ...]


def default_warning_governance_policy_path() -> Path:
    return Path(__file__).resolve().parents[3] / "configs" / "compat" / "warning_governance_v1.json"


def default_dependency_update_policy_path() -> Path:
    return Path(__file__).resolve().parents[3] / "configs" / "compat" / "dependency_update_policy_v1.json"


def load_warning_governance_policy(path: Path | str | None = None) -> WarningGovernancePolicy:
    policy_path = Path(path) if path is not None else default_warning_governance_policy_path()
    payload = json.loads(policy_path.read_text(encoding="utf-8"))
    policy = payload.get("policy") or {}

    def _load_rules(items: Iterable[dict[str, object]], *, kind: str) -> tuple[WarningGovernanceRule, ...]:
        return tuple(
            WarningGovernanceRule(
                name=str(item["name"]),
                kind=kind,
                origin=str(item["origin"]) if item.get("origin") is not None else None,
                category_name=str(item["category"]) if item.get("category") is not None else None,
                category_regex=str(item["category_regex"]) if item.get("category_regex") is not None else None,
                message_regex=str(item.get("message_regex", r".*")),
                package=str(item["package"]) if item.get("package") is not None else None,
                filename_regex=str(item["filename_regex"]) if item.get("filename_regex") is not None else None,
                max_count=int(item.get("max_count", 1)),
                escalation=str(item.get("escalation", "")),
                notes=str(item.get("notes", "")),
            )
            for item in items
        )

    dependency_policy_path = str(policy.get("dependency_policy_path") or default_dependency_update_policy_path())
    return WarningGovernancePolicy(
        version=int(payload["version"]),
        scope=str(policy.get("scope", "")),
        dependency_policy_path=dependency_policy_path,
        allowlist=_load_rules(payload.get("allowlist", []), kind="allow"),
        denylist=_load_rules(payload.get("denylist", []), kind="deny"),
    )


def load_dependency_update_policy(path: Path | str | None = None) -> dict[str, object]:
    policy_path = Path(path) if path is not None else default_dependency_update_policy_path()
    return json.loads(policy_path.read_text(encoding="utf-8"))


def parse_warning_sources(sources: Mapping[str, Path | str | None]) -> tuple[list[WarningEvidence], tuple[dict[str, object], ...]]:
    evidence: list[WarningEvidence] = []
    source_meta: list[dict[str, object]] = []
    for source_name, source_path in sources.items():
        if source_path is None:
            source_meta.append({"source": source_name, "path": None, "exists": False, "warnings": 0})
            continue
        path = Path(source_path)
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        entries = parse_pytest_warning_log(text)
        for entry in entries:
            evidence.append(WarningEvidence(source=source_name, entry=entry))
        source_meta.append(
            {
                "source": source_name,
                "path": str(path),
                "exists": path.exists(),
                "warnings": len(entries),
            }
        )
    return evidence, tuple(source_meta)


def _matches_deprecation_rule(rule: DeprecationRule, entry: ParsedWarningEntry) -> bool:
    if entry.category != rule.category_name:
        return False
    return re.search(rule.message_regex, entry.message) is not None


def analyze_warning_governance(
    evidence: Iterable[WarningEvidence],
    policy: WarningGovernancePolicy,
    *,
    deprecation_policy: DeprecationPolicy | None = None,
    source_files: tuple[dict[str, object], ...] = (),
) -> WarningGovernanceReport:
    dep_policy = deprecation_policy or load_deprecation_policy()
    items = list(evidence)
    matched_counts: dict[str, int] = {}
    by_source: dict[str, int] = {}
    by_dependency: dict[str, int] = {}
    processed_entries: list[dict[str, object]] = []
    unexpected: list[str] = []
    denylisted: list[str] = []

    all_entries = [item.entry for item in items]
    origin_summary = build_warning_origin_report(all_entries)

    explicit_rules = {rule.name: rule for rule in policy.allowlist}
    deprecation_rules = {f"deprecation:{rule.name}": rule for rule in dep_policy.rules}
    for rule_name in list(explicit_rules) + list(deprecation_rules):
        matched_counts[rule_name] = 0

    for item in items:
        entry = item.entry
        by_source[item.source] = by_source.get(item.source, 0) + 1
        if entry.origin == "dependency":
            key = entry.package or "unknown"
            by_dependency[key] = by_dependency.get(key, 0) + 1

        deny_rule = next((rule for rule in policy.denylist if rule.matches(entry)), None)
        if deny_rule is not None:
            denylisted.append(
                f"{item.source}: {entry.category} at {entry.filename}:{entry.lineno} matched denylist {deny_rule.name}: {entry.message}"
            )
            processed_entries.append(
                {
                    "source": item.source,
                    **asdict(entry),
                    "status": "denylisted",
                    "rule": deny_rule.name,
                    "escalation": deny_rule.escalation,
                }
            )
            continue

        matched_name: str | None = None
        matched_escalation = ""
        if entry.origin == "project" and entry.category in {"DeprecationWarning", "PendingDeprecationWarning"}:
            matched_dep_rule = next((rule for rule in dep_policy.rules if _matches_deprecation_rule(rule, entry)), None)
            if matched_dep_rule is not None:
                matched_name = f"deprecation:{matched_dep_rule.name}"
                matched_escalation = "backward-compatible shim/deprecation; keep documented and stable"

        if matched_name is None:
            explicit_match = next((rule for rule in policy.allowlist if rule.matches(entry)), None)
            if explicit_match is not None:
                matched_name = explicit_match.name
                matched_escalation = explicit_match.escalation

        if matched_name is None:
            unexpected.append(
                f"{item.source}: {entry.origin}/{entry.category} at {entry.filename}:{entry.lineno}: {entry.message}"
            )
            processed_entries.append(
                {
                    "source": item.source,
                    **asdict(entry),
                    "status": "unexpected",
                    "rule": None,
                    "escalation": "fix in project code or document in policy before accepting",
                }
            )
            continue

        matched_counts[matched_name] = matched_counts.get(matched_name, 0) + 1
        processed_entries.append(
            {
                "source": item.source,
                **asdict(entry),
                "status": "allowed",
                "rule": matched_name,
                "escalation": matched_escalation,
            }
        )

    over_budget: list[str] = []
    for rule_name, count in matched_counts.items():
        if rule_name in deprecation_rules:
            max_count = deprecation_rules[rule_name].max_count
            escalation = "reduce duplicate shim warnings or adjust documented budget in separate change"
        else:
            rule = explicit_rules[rule_name]
            max_count = rule.max_count
            escalation = rule.escalation
        if count > max_count:
            over_budget.append(f"{rule_name}: {count} > {max_count}; escalation={escalation}")

    return WarningGovernanceReport(
        total=len(items),
        by_origin=dict(origin_summary.get("by_origin") or {}),
        by_source=dict(sorted(by_source.items())),
        by_dependency=dict(sorted(by_dependency.items())),
        matched_counts=dict(sorted(matched_counts.items())),
        unexpected=tuple(unexpected),
        over_budget=tuple(over_budget),
        denylisted=tuple(denylisted),
        entries=tuple(processed_entries),
        source_files=source_files,
    )


def assert_warning_governance(report: WarningGovernanceReport) -> WarningGovernanceReport:
    problems: list[str] = []
    if report.denylisted:
        problems.append("Denylisted warnings:\n- " + "\n- ".join(report.denylisted))
    if report.unexpected:
        problems.append("Unexpected warnings:\n- " + "\n- ".join(report.unexpected))
    if report.over_budget:
        problems.append("Warning budgets exceeded:\n- " + "\n- ".join(report.over_budget))
    if problems:
        raise AssertionError("\n\n".join(problems))
    return report


def build_warning_governance_report(
    sources: Mapping[str, Path | str | None],
    *,
    policy: WarningGovernancePolicy | None = None,
    deprecation_policy: DeprecationPolicy | None = None,
) -> dict[str, object]:
    governance_policy = policy or load_warning_governance_policy()
    evidence, source_files = parse_warning_sources(sources)
    report = analyze_warning_governance(
        evidence,
        governance_policy,
        deprecation_policy=deprecation_policy,
        source_files=source_files,
    )
    status = "ok"
    try:
        assert_warning_governance(report)
    except AssertionError as exc:
        status = "failed"
        failure_message = str(exc)
    else:
        failure_message = ""
    dependency_policy = load_dependency_update_policy(governance_policy.dependency_policy_path)
    return {
        "version": governance_policy.version,
        "status": status,
        "scope": governance_policy.scope,
        "dependency_policy_version": dependency_policy.get("version"),
        "totals": {
            "total": report.total,
            "by_origin": report.by_origin,
            "by_source": report.by_source,
            "by_dependency": report.by_dependency,
        },
        "matched_counts": report.matched_counts,
        "unexpected": list(report.unexpected),
        "over_budget": list(report.over_budget),
        "denylisted": list(report.denylisted),
        "failure_message": failure_message,
        "source_files": list(report.source_files),
        "entries": list(report.entries),
        "dependency_policy": {
            "path": governance_policy.dependency_policy_path,
            "summary": dependency_policy.get("upgrade_policy", {}),
        },
    }


__all__ = [
    "WarningEvidence",
    "WarningGovernancePolicy",
    "WarningGovernanceReport",
    "WarningGovernanceRule",
    "analyze_warning_governance",
    "assert_warning_governance",
    "build_warning_governance_report",
    "default_dependency_update_policy_path",
    "default_warning_governance_policy_path",
    "load_dependency_update_policy",
    "load_warning_governance_policy",
    "parse_warning_sources",
]
