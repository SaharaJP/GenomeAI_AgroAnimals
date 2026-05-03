from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping
import os

import yaml

_DEFAULT_CFG = Path("configs/product/commercial_packaging_v1.yaml")


@dataclass(frozen=True)
class CommercialPackagingContext:
    edition_key: str
    edition_label: str
    profile_key: str
    enabled_modules: tuple[str, ...]
    enabled_features: tuple[str, ...]
    optional_modules: tuple[str, ...]
    enterprise_capabilities: tuple[str, ...]
    source: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _norm_list(values: Iterable[Any] | None) -> list[str]:
    return [str(v).strip() for v in (values or []) if str(v).strip()]


def load_commercial_packaging_config(path: str | Path = _DEFAULT_CFG) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Commercial packaging config not found: {p}")
    cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    _validate_packaging_config(cfg)
    return cfg


def _validate_packaging_config(cfg: Mapping[str, Any]) -> None:
    if not isinstance(cfg, Mapping):
        raise ValueError("Commercial packaging config must be a mapping")
    if int(cfg.get("version", 0)) != 1:
        raise ValueError("Commercial packaging config version must be 1")
    for key in ("feature_catalog", "module_catalog", "editions", "runtime_profiles"):
        section = cfg.get(key)
        if not isinstance(section, Mapping) or not section:
            raise ValueError(f"Commercial packaging config: '{key}' must be a non-empty mapping")
    for module_key, meta in (cfg.get("module_catalog") or {}).items():
        if not isinstance(meta, Mapping):
            raise ValueError(f"module_catalog.{module_key} must be a mapping")
        if not _norm_list(meta.get("includes_features")):
            raise ValueError(f"module_catalog.{module_key}.includes_features must be non-empty")
    for edition_key, meta in (cfg.get("editions") or {}).items():
        if not isinstance(meta, Mapping):
            raise ValueError(f"editions.{edition_key} must be a mapping")
        if not str(meta.get("label") or "").strip():
            raise ValueError(f"editions.{edition_key}.label is required")


def _resolve_edition_meta(cfg: Mapping[str, Any], edition_key: str) -> dict[str, Any]:
    editions = dict(cfg.get("editions") or {})
    if edition_key not in editions:
        raise KeyError(f"Unknown edition: {edition_key}")
    stack: list[tuple[str, Mapping[str, Any]]] = []
    current = edition_key
    seen: set[str] = set()
    while current:
        if current in seen:
            raise ValueError(f"Edition inheritance cycle detected: {current}")
        seen.add(current)
        meta = dict(editions.get(current) or {})
        stack.append((current, meta))
        parent = str(meta.get("parent") or "").strip()
        current = parent
    merged: dict[str, Any] = {
        "label": "",
        "summary": "",
        "base_features": [],
        "optional_modules": [],
        "enterprise_capabilities": [],
        "implementation_scope": {"includes": [], "excludes": []},
    }
    for _, meta in reversed(stack):
        if meta.get("label"):
            merged["label"] = str(meta.get("label") or "")
        if meta.get("summary"):
            merged["summary"] = str(meta.get("summary") or "")
        for list_key in ("base_features", "optional_modules", "enterprise_capabilities"):
            merged[list_key] = list(dict.fromkeys([*merged.get(list_key, []), *_norm_list(meta.get(list_key))]))
        impl = dict(meta.get("implementation_scope") or {})
        merged_impl = dict(merged.get("implementation_scope") or {})
        for list_key in ("includes", "excludes"):
            merged_impl[list_key] = list(dict.fromkeys([*_norm_list(merged_impl.get(list_key)), *_norm_list(impl.get(list_key))]))
        merged["implementation_scope"] = merged_impl
    return merged


def resolve_packaging_context(
    *,
    cfg: Mapping[str, Any],
    edition_key: str,
    enabled_modules: Iterable[str] | None = None,
    source: str = "config",
    profile_key: str = "custom",
) -> CommercialPackagingContext:
    edition_meta = _resolve_edition_meta(cfg, edition_key)
    modules_cfg = dict(cfg.get("module_catalog") or {})
    modules = [m for m in _norm_list(enabled_modules) if m in modules_cfg]
    feature_set: list[str] = list(_norm_list(edition_meta.get("base_features")))
    for module_key in modules:
        feature_set.extend(_norm_list((modules_cfg.get(module_key) or {}).get("includes_features")))
    feature_set = list(dict.fromkeys(feature_set))
    return CommercialPackagingContext(
        edition_key=edition_key,
        edition_label=str(edition_meta.get("label") or edition_key),
        profile_key=str(profile_key),
        enabled_modules=tuple(modules),
        enabled_features=tuple(feature_set),
        optional_modules=tuple(_norm_list(edition_meta.get("optional_modules"))),
        enterprise_capabilities=tuple(_norm_list(edition_meta.get("enterprise_capabilities"))),
        source=str(source),
    )


def load_runtime_packaging_context(*, project_root: str | Path = ".", env: Mapping[str, str] | None = None, config_path: str | Path | None = None) -> CommercialPackagingContext:
    root = Path(project_root).resolve()
    cfg_path = Path(config_path).resolve() if config_path is not None else (root / _DEFAULT_CFG).resolve()
    cfg = load_commercial_packaging_config(cfg_path)
    runtime_profiles = dict(cfg.get("runtime_profiles") or {})
    env_map = dict(os.environ)
    env_map.update(dict(env or {}))
    explicit_profile = str(env_map.get("GENOMEAI_COMMERCIAL_PROFILE") or "").strip()
    deploy_profile = str(env_map.get("GENOMEAI_DEPLOY_PROFILE") or "").strip()
    mapped_profile = str((cfg.get("deploy_profile_map") or {}).get(deploy_profile) or "").strip()
    profile_key = explicit_profile or mapped_profile or "enterprise_default"
    runtime_meta = dict(runtime_profiles.get(profile_key) or runtime_profiles.get("enterprise_default") or {})
    edition_key = str(env_map.get("GENOMEAI_EDITION") or runtime_meta.get("edition") or "enterprise").strip()
    modules = _norm_list(runtime_meta.get("enabled_modules"))
    override_modules = env_map.get("GENOMEAI_ENABLED_MODULES")
    if override_modules is not None:
        modules = _norm_list(str(override_modules).split(","))
        source = "env"
    else:
        source = "profile"
    return resolve_packaging_context(cfg=cfg, edition_key=edition_key, enabled_modules=modules, source=source, profile_key=profile_key)


def is_feature_enabled(packaging: CommercialPackagingContext | Mapping[str, Any] | None, feature_key: str) -> bool:
    if packaging is None:
        return True
    enabled = set(packaging.enabled_features if isinstance(packaging, CommercialPackagingContext) else _norm_list((packaging or {}).get("enabled_features")))
    return str(feature_key).strip() in enabled


def is_module_enabled(packaging: CommercialPackagingContext | Mapping[str, Any] | None, module_key: str) -> bool:
    if packaging is None:
        return True
    enabled = set(packaging.enabled_modules if isinstance(packaging, CommercialPackagingContext) else _norm_list((packaging or {}).get("enabled_modules")))
    return str(module_key).strip() in enabled


def build_packaging_summary(*, project_root: str | Path = ".", env: Mapping[str, str] | None = None, config_path: str | Path | None = None) -> dict[str, Any]:
    root = Path(project_root).resolve()
    cfg_path = Path(config_path).resolve() if config_path is not None else (root / _DEFAULT_CFG).resolve()
    cfg = load_commercial_packaging_config(cfg_path)
    runtime = load_runtime_packaging_context(project_root=root, env=env, config_path=cfg_path)
    edition_meta = _resolve_edition_meta(cfg, runtime.edition_key)
    modules_cfg = dict(cfg.get("module_catalog") or {})
    module_rows = []
    for key, meta in modules_cfg.items():
        module_rows.append({
            "module_key": key,
            "label": str(meta.get("label") or key),
            "enabled": key in set(runtime.enabled_modules),
            "features": _norm_list(meta.get("includes_features")),
            "nav_keys": _norm_list(meta.get("nav_keys")),
            "required_configs": _norm_list(meta.get("required_configs")),
        })
    edition_rows = []
    for key in (cfg.get("editions") or {}).keys():
        meta = _resolve_edition_meta(cfg, key)
        edition_rows.append({
            "edition_key": key,
            "label": str(meta.get("label") or key),
            "summary": str(meta.get("summary") or ""),
            "base_features": _norm_list(meta.get("base_features")),
            "optional_modules": _norm_list(meta.get("optional_modules")),
            "enterprise_capabilities": _norm_list(meta.get("enterprise_capabilities")),
            "implementation_scope": meta.get("implementation_scope") or {},
        })
    return {
        "runtime": runtime.as_dict(),
        "edition": {
            "edition_key": runtime.edition_key,
            "label": runtime.edition_label,
            "summary": str(edition_meta.get("summary") or ""),
            "implementation_scope": edition_meta.get("implementation_scope") or {},
        },
        "module_rows": module_rows,
        "edition_rows": edition_rows,
        "license_unit": str(((cfg.get("basis") or {}).get("license_unit") or "site")),
        "implementation_scope_unit": str(((cfg.get("basis") or {}).get("implementation_scope_unit") or "site_wave")),
    }


def render_packaging_markdown(summary: Mapping[str, Any]) -> str:
    runtime = dict(summary.get("runtime") or {})
    edition = dict(summary.get("edition") or {})
    lines = [
        f"# Commercial packaging — {edition.get('label') or runtime.get('edition_key')}",
        "",
        f"- edition_key: `{runtime.get('edition_key')}`",
        f"- profile_key: `{runtime.get('profile_key')}`",
        f"- source: `{runtime.get('source')}`",
        f"- license_unit: `{summary.get('license_unit')}`",
        f"- implementation_scope_unit: `{summary.get('implementation_scope_unit')}`",
        "",
        str(edition.get('summary') or ''),
        "",
        "## Enabled modules",
    ]
    for module in summary.get("module_rows") or []:
        if module.get("enabled"):
            lines.append(f"- **{module.get('label')}** (`{module.get('module_key')}`) → features: {', '.join(module.get('features') or [])}")
    lines.extend(["", "## Implementation scope"])
    impl = dict(edition.get("implementation_scope") or {})
    for item in _norm_list(impl.get("includes")):
        lines.append(f"- includes: {item}")
    for item in _norm_list(impl.get("excludes")):
        lines.append(f"- excludes: {item}")
    return "\n".join(lines) + "\n"


__all__ = [
    "CommercialPackagingContext",
    "build_packaging_summary",
    "is_feature_enabled",
    "is_module_enabled",
    "load_commercial_packaging_config",
    "load_runtime_packaging_context",
    "render_packaging_markdown",
    "resolve_packaging_context",
]
