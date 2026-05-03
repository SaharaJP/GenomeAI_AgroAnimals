from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


_WARNING_CATEGORIES = {
    "DeprecationWarning": DeprecationWarning,
    "PendingDeprecationWarning": PendingDeprecationWarning,
}


@dataclass(frozen=True)
class DeprecationRule:
    name: str
    kind: str
    trigger_type: str
    trigger_target: str
    category_name: str
    message_regex: str
    max_count: int = 1

    @property
    def category(self) -> type[Warning]:
        try:
            return _WARNING_CATEGORIES[self.category_name]
        except KeyError as exc:  # pragma: no cover - config error path
            raise ValueError(f"Unsupported warning category in deprecation policy: {self.category_name}") from exc

    def matches(self, warning_message: object) -> bool:
        category = getattr(warning_message, "category", None)
        message = getattr(warning_message, "message", None)
        if category is None or message is None:
            return False
        try:
            is_category_match = issubclass(category, self.category)
        except TypeError:
            return False
        return is_category_match and re.search(self.message_regex, str(message)) is not None


@dataclass(frozen=True)
class DeprecationPolicy:
    version: int
    scope: str
    unexpected_deprecations_fail_ci: bool
    rules: tuple[DeprecationRule, ...]

    def rules_for(self, trigger_type: str) -> tuple[DeprecationRule, ...]:
        return tuple(rule for rule in self.rules if rule.trigger_type == trigger_type)

    def rule_by_name(self, name: str) -> DeprecationRule:
        for rule in self.rules:
            if rule.name == name:
                return rule
        raise KeyError(name)


@dataclass(frozen=True)
class WarningPolicyReport:
    matched_counts: dict[str, int]
    unexpected: tuple[str, ...]
    over_budget: tuple[str, ...]


def default_deprecation_policy_path() -> Path:
    return Path(__file__).resolve().parents[3] / "configs" / "compat" / "deprecation_warnings_v1.json"


def load_deprecation_policy(path: Path | str | None = None) -> DeprecationPolicy:
    policy_path = Path(path) if path is not None else default_deprecation_policy_path()
    payload = json.loads(policy_path.read_text(encoding="utf-8"))
    rules = []
    for item in payload.get("allowed", []):
        trigger = item.get("trigger") or {}
        rules.append(
            DeprecationRule(
                name=str(item["name"]),
                kind=str(item["kind"]),
                trigger_type=str(trigger["type"]),
                trigger_target=str(trigger["target"]),
                category_name=str(item["category"]),
                message_regex=str(item["message_regex"]),
                max_count=int(item.get("max_count", 1)),
            )
        )
    policy_meta = payload.get("policy") or {}
    return DeprecationPolicy(
        version=int(payload["version"]),
        scope=str(policy_meta.get("scope", "")),
        unexpected_deprecations_fail_ci=bool(policy_meta.get("unexpected_deprecations_fail_ci", True)),
        rules=tuple(rules),
    )


def analyze_warning_records(
    warning_records: Iterable[object],
    rules: Sequence[DeprecationRule],
) -> WarningPolicyReport:
    matched_counts = {rule.name: 0 for rule in rules}
    unexpected: list[str] = []
    for record in warning_records:
        category = getattr(record, "category", None)
        if category is None or not issubclass(category, (DeprecationWarning, PendingDeprecationWarning)):
            continue
        matched = next((rule for rule in rules if rule.matches(record)), None)
        if matched is None:
            unexpected.append(f"{category.__name__}: {record.message}")
            continue
        matched_counts[matched.name] += 1
    over_budget = [
        f"{rule.name}: {matched_counts[rule.name]} > {rule.max_count}"
        for rule in rules
        if matched_counts[rule.name] > rule.max_count
    ]
    return WarningPolicyReport(
        matched_counts=matched_counts,
        unexpected=tuple(unexpected),
        over_budget=tuple(over_budget),
    )


def assert_warning_policy(
    warning_records: Iterable[object],
    rules: Sequence[DeprecationRule],
) -> WarningPolicyReport:
    report = analyze_warning_records(warning_records, rules)
    problems: list[str] = []
    if report.unexpected:
        problems.append("Unexpected deprecation warnings:\n- " + "\n- ".join(report.unexpected))
    if report.over_budget:
        problems.append("Deprecation warning budget exceeded:\n- " + "\n- ".join(report.over_budget))
    if problems:
        raise AssertionError("\n\n".join(problems))
    return report


__all__ = [
    "DeprecationPolicy",
    "DeprecationRule",
    "WarningPolicyReport",
    "analyze_warning_records",
    "assert_warning_policy",
    "default_deprecation_policy_path",
    "load_deprecation_policy",
]
