from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from dataclasses import dataclass

@dataclass(frozen=True)
class ShellItem:
    key: str
    label: str
    page: str | None = None
    permission: str | None = None


def flatten_shell_sections(sections):
    items = []
    for section in sections or []:
        for item in (section.get("items") or []):
            items.append(ShellItem(key=str(item.get("key") or ""), label=str(item.get("label") or item.get("key") or ""), page=str(item.get("page") or item.get("route") or ""), permission=str(item.get("permission") or "") or None))
    return items

_DEFAULT_CFG = Path("configs/ui/onboarding_by_role_v1.yaml")


@dataclass(frozen=True)
class OnboardingChecklistStep:
    title: str
    page: str
    page_label: str
    why: str
    checklist: tuple[str, ...]
    do_items: tuple[str, ...]
    dont_items: tuple[str, ...]
    diagnostics: tuple[str, ...]


@dataclass(frozen=True)
class RoleOnboardingKit:
    role: str
    summary: str
    restrictions_note: str
    start_of_day: tuple[OnboardingChecklistStep, ...]
    key_pages: tuple[dict[str, str], ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_onboarding_config(path: str | Path = _DEFAULT_CFG) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Onboarding config not found: {p}")
    cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    _validate_onboarding_config(cfg)
    return cfg


def _validate_onboarding_config(cfg: Mapping[str, Any]) -> None:
    if not isinstance(cfg, Mapping):
        raise ValueError("Onboarding config must be a mapping")
    roles = cfg.get("roles")
    if not isinstance(roles, Mapping) or not roles:
        raise ValueError("Onboarding config must contain non-empty 'roles'")
    for role, meta in roles.items():
        if not isinstance(meta, Mapping):
            raise ValueError(f"roles.{role} must be a mapping")
        if not str(meta.get("summary") or "").strip():
            raise ValueError(f"roles.{role}.summary is required")
        if not isinstance(meta.get("start_of_day") or [], list):
            raise ValueError(f"roles.{role}.start_of_day must be a list")
        if not isinstance(meta.get("key_pages") or [], list):
            raise ValueError(f"roles.{role}.key_pages must be a list")


def _resolve_step_page(step: Mapping[str, Any], flat: Mapping[str, ShellItem]) -> tuple[str, str]:
    direct_page = str(step.get("page") or "").strip()
    if direct_page:
        label = str(step.get("page_label") or Path(direct_page).stem.replace("_", " ")).strip()
        return direct_page, label
    page_key = str(step.get("page_key") or "").strip()
    item = flat.get(page_key)
    if item is None:
        return "", ""
    return str(item.page), str(item.label)


def _resolve_key_page(key: str, flat: Mapping[str, ShellItem]) -> dict[str, str] | None:
    item = flat.get(str(key).strip())
    if item is None:
        return None
    return {
        "key": item.key,
        "label": item.label,
        "page": item.page,
        "group": item.group,
        "description": item.description or "",
    }


def build_role_onboarding_kit(*, role: str, shell_sections: Sequence[Any], cfg: Mapping[str, Any] | None = None) -> RoleOnboardingKit:
    config = dict(cfg or load_onboarding_config())
    roles_cfg = dict(config.get("roles") or {})
    role_cfg = dict(roles_cfg.get(role) or roles_cfg.get("Viewer") or {})
    flat = flatten_shell_sections(list(shell_sections))

    steps: list[OnboardingChecklistStep] = []
    for raw in list(role_cfg.get("start_of_day") or []):
        if not isinstance(raw, Mapping):
            continue
        page, page_label = _resolve_step_page(raw, flat)
        if not page:
            continue
        why_bits = [str(bit).strip() for bit in [raw.get("why"), *(raw.get("diagnostics") or [])] if str(bit).strip()]
        why = str(raw.get("why") or "").strip() or (why_bits[0] if why_bits else "Open the linked governed page.")
        steps.append(
            OnboardingChecklistStep(
                title=str(raw.get("title") or "Шаг").strip(),
                page=page,
                page_label=page_label,
                why=why,
                checklist=tuple(str(x).strip() for x in (raw.get("checklist") or []) if str(x).strip()),
                do_items=tuple(str(x).strip() for x in (raw.get("do") or []) if str(x).strip()),
                dont_items=tuple(str(x).strip() for x in (raw.get("dont") or []) if str(x).strip()),
                diagnostics=tuple(str(x).strip() for x in (raw.get("diagnostics") or []) if str(x).strip()),
            )
        )

    key_pages = tuple(
        page for key in (role_cfg.get("key_pages") or []) if (page := _resolve_key_page(str(key), flat)) is not None
    )

    return RoleOnboardingKit(
        role=str(role),
        summary=str(role_cfg.get("summary") or "").strip(),
        restrictions_note=str(role_cfg.get("restrictions_note") or "").strip(),
        start_of_day=tuple(steps),
        key_pages=key_pages,
    )


def build_role_onboarding_markdown(kit: RoleOnboardingKit) -> str:
    lines = [f"# Onboarding kit — {kit.role}", "", kit.summary, "", f"Ограничения роли: {kit.restrictions_note}", ""]
    lines.append("## Start-of-day workflow")
    for idx, step in enumerate(kit.start_of_day, start=1):
        lines.append(f"{idx}. **{step.title}** — `{step.page}`")
        lines.append(f"   - Почему: {step.why}")
        if step.checklist:
            lines.append("   - Checklist:")
            for item in step.checklist:
                lines.append(f"     - {item}")
        if step.do_items:
            lines.append("   - Do:")
            for item in step.do_items:
                lines.append(f"     - {item}")
        if step.dont_items:
            lines.append("   - Don't:")
            for item in step.dont_items:
                lines.append(f"     - {item}")
        if step.diagnostics:
            lines.append("   - Diagnostics:")
            for item in step.diagnostics:
                lines.append(f"     - {item}")
    if kit.key_pages:
        lines.extend(["", "## Key pages"])
        for page in kit.key_pages:
            lines.append(f"- **{page['label']}** — `{page['page']}`")
            if page.get("description"):
                lines.append(f"  - {page['description']}")
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "OnboardingChecklistStep",
    "RoleOnboardingKit",
    "build_role_onboarding_kit",
    "build_role_onboarding_markdown",
    "load_onboarding_config",
]
