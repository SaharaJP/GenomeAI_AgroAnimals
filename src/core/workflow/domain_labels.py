from __future__ import annotations

from functools import lru_cache
from typing import Any

from core.workflow.policies import WORKFLOW_DOMAINS, load_workflow_yaml, workflow_project_root


def _config_path() -> Any:
    return workflow_project_root() / "configs" / "workflow_v2" / "domain_labels.yaml"


@lru_cache(maxsize=16)
def _load() -> dict[str, Any]:
    return load_workflow_yaml(_config_path())


def default_locale() -> str:
    return str(_load().get("default_locale") or "ru")


def supported_locales() -> list[str]:
    labels = _load().get("labels") or {}
    return sorted(labels.keys()) if isinstance(labels, dict) else []


def load_domain_labels(locale: str | None = None) -> dict[str, str]:
    """Return canonical domain → human label map for a locale, fallback to id."""
    cfg = _load()
    locale = (locale or default_locale()).strip().lower()
    labels = ((cfg.get("labels") or {}).get(locale) or {}) if isinstance(cfg, dict) else {}
    out: dict[str, str] = {}
    for dom in sorted(WORKFLOW_DOMAINS):
        value = labels.get(dom) if isinstance(labels, dict) else None
        out[dom] = str(value) if value else dom
    return out


__all__ = ["default_locale", "load_domain_labels", "supported_locales"]
