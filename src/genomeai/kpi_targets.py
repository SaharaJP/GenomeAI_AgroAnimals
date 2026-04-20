from __future__ import annotations

"""KPI goals/targets config + plan-fact computation (T10-02).

This module is part of offline-core. The Web/Streamlit UI must not implement
business logic; it should call functions from here.

Config is YAML with defaults and optional overrides per (tenant_id/farm_id/site_id).
Overrides can be stored in Web Cabinet under:
  web_storage/config_overrides/<relative_path>
and passed as override_dir.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

from datetime import datetime

import pandas as pd
import yaml

from core.common.time import utc_isoformat_z


DEFAULT_REL_PATH = Path("configs/kpi/kpi_targets_v1.yaml")


class TargetsConfigError(ValueError):
    """Human-readable config parsing/validation errors."""


@dataclass(frozen=True)
class TargetSpec:
    kpi_id: str
    target: float
    direction: str  # higher_better | lower_better
    warn_pct: float
    alert_pct: float
    unit: Optional[str] = None
    source: str = ""  # for UI/debug


def _read_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        obj = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as e:
        raise TargetsConfigError(f"Не удалось прочитать YAML {path}: {e}")
    if obj is None:
        return {}
    if not isinstance(obj, dict):
        raise TargetsConfigError(
            f"Неверный формат {path}: ожидается dict, получено {type(obj).__name__}"
        )
    return obj


def _maybe_override_path(cfg_path: Path, override_dir: Optional[Path]) -> Path:
    """Return override path if exists, else cfg_path."""
    cfg_path = Path(cfg_path)
    if override_dir is None:
        return cfg_path
    override_dir = Path(override_dir)
    # We support only relative cfg_path for overrides.
    if cfg_path.is_absolute():
        return cfg_path
    cand = (override_dir / cfg_path).resolve()
    return cand if cand.exists() else cfg_path


def load_kpi_targets(
    *,
    cfg_path: Path = DEFAULT_REL_PATH,
    override_dir: Optional[Path] = None,
) -> dict:
    """Load KPI targets config with optional override dir.

    Returns the raw dict (validated & normalized). Use resolve_target_spec
    to get per-scope values.
    """

    path = _maybe_override_path(cfg_path, override_dir)
    obj = _read_yaml(path)
    if not obj:
        # fallback minimal defaults (no targets)
        return {"version": "0", "defaults": {"kpis": {}}, "targets": [], "_source": str(path)}

    obj.setdefault("version", "1")
    obj.setdefault("defaults", {})
    obj["defaults"].setdefault("kpis", {})
    obj.setdefault("targets", [])
    if not isinstance(obj["defaults"], dict):
        raise TargetsConfigError(f"{path}: defaults должен быть dict")
    if not isinstance(obj["defaults"].get("kpis"), dict):
        raise TargetsConfigError(f"{path}: defaults.kpis должен быть dict")
    if not isinstance(obj["targets"], list):
        raise TargetsConfigError(f"{path}: targets должен быть list")

    # Validate structure of targets entries
    for i, t in enumerate(obj["targets"]):
        if not isinstance(t, dict):
            raise TargetsConfigError(f"{path}: targets[{i}] должен быть dict")
        scope = t.get("scope")
        kpis = t.get("kpis")
        if scope is None or not isinstance(scope, dict):
            raise TargetsConfigError(f"{path}: targets[{i}].scope должен быть dict")
        if kpis is None or not isinstance(kpis, dict):
            raise TargetsConfigError(f"{path}: targets[{i}].kpis должен быть dict")
        # Ensure scope keys are strings
        for k, v in scope.items():
            if not isinstance(k, str):
                raise TargetsConfigError(f"{path}: targets[{i}].scope key должен быть str")
            if v is None:
                continue
            if not isinstance(v, (str, int)):
                raise TargetsConfigError(
                    f"{path}: targets[{i}].scope['{k}'] должен быть str/int, получено {type(v).__name__}"
                )

    obj["_source"] = str(path)
    return obj


def _parse_spec(kpi_id: str, spec: dict, *, source: str) -> TargetSpec:
    if not isinstance(spec, dict):
        raise TargetsConfigError(f"{source}: kpi '{kpi_id}' spec должен быть dict")
    if "target" not in spec:
        raise TargetsConfigError(f"{source}: kpi '{kpi_id}' отсутствует поле target")
    try:
        target = float(spec.get("target"))
    except Exception:
        raise TargetsConfigError(f"{source}: kpi '{kpi_id}' target должен быть числом")
    direction = str(spec.get("direction") or "higher_better").strip().lower()
    if direction not in {"higher_better", "lower_better"}:
        raise TargetsConfigError(
            f"{source}: kpi '{kpi_id}' direction должен быть higher_better|lower_better, получено '{direction}'"
        )
    try:
        warn_pct = float(spec.get("warn_pct", 0.05))
        alert_pct = float(spec.get("alert_pct", 0.10))
    except Exception:
        raise TargetsConfigError(f"{source}: kpi '{kpi_id}' warn_pct/alert_pct должны быть числами")
    if warn_pct < 0 or alert_pct < 0:
        raise TargetsConfigError(f"{source}: kpi '{kpi_id}' warn_pct/alert_pct должны быть >=0")
    if alert_pct < warn_pct:
        raise TargetsConfigError(f"{source}: kpi '{kpi_id}' alert_pct должен быть >= warn_pct")
    unit = spec.get("unit")
    if unit is not None:
        unit = str(unit)
    return TargetSpec(
        kpi_id=kpi_id,
        target=target,
        direction=direction,
        warn_pct=warn_pct,
        alert_pct=alert_pct,
        unit=unit,
        source=source,
    )


def _scope_score(scope: dict) -> int:
    # More keys => more specific
    return len([k for k, v in scope.items() if v is not None and str(v) != ""])


def resolve_target_spec(
    cfg: dict,
    *,
    kpi_id: str,
    scope: dict[str, Any],
) -> Optional[TargetSpec]:
    """Return best matching TargetSpec for scope or None if missing."""

    source = str(cfg.get("_source") or "kpi_targets")

    # Candidates from explicit rules
    best: Optional[Tuple[int, TargetSpec]] = None
    for rule in cfg.get("targets") or []:
        if not isinstance(rule, dict):
            continue
        rscope = rule.get("scope") or {}
        if not isinstance(rscope, dict):
            continue

        # Match: all specified keys must exist in scope and equal.
        ok = True
        for k, v in rscope.items():
            if v is None or str(v) == "":
                continue
            if k not in scope:
                ok = False
                break
            if str(scope.get(k)) != str(v):
                ok = False
                break
        if not ok:
            continue

        kpis = rule.get("kpis") or {}
        if not isinstance(kpis, dict) or kpi_id not in kpis:
            continue
        spec = _parse_spec(kpi_id, kpis[kpi_id], source=source)
        score = _scope_score(rscope)
        if best is None or score > best[0]:
            best = (score, spec)

    if best is not None:
        return best[1]

    # Defaults
    dkpis = ((cfg.get("defaults") or {}).get("kpis") or {})
    if isinstance(dkpis, dict) and kpi_id in dkpis:
        return _parse_spec(kpi_id, dkpis[kpi_id], source=source)
    return None


def _status(actual: float, spec: TargetSpec) -> Tuple[str, float, float]:
    """Return (status, delta, delta_pct)."""
    if spec.target == 0 or pd.isna(spec.target):
        return "NO_TARGET", float("nan"), float("nan")
    delta = float(actual - spec.target)
    delta_pct = float(delta / spec.target)
    if spec.direction == "higher_better":
        # Negative delta is bad
        if delta_pct <= -spec.alert_pct:
            return "ALERT", delta, delta_pct
        if delta_pct <= -spec.warn_pct:
            return "WARN", delta, delta_pct
        return "OK", delta, delta_pct
    # lower_better
    if delta_pct >= spec.alert_pct:
        return "ALERT", delta, delta_pct
    if delta_pct >= spec.warn_pct:
        return "WARN", delta, delta_pct
    return "OK", delta, delta_pct


def compute_plan_fact(
    kpi_long: pd.DataFrame,
    *,
    targets_cfg: dict,
    data_version: str,
    kpi_run_id: str,
) -> pd.DataFrame:
    """Compute plan-fact mart for director dashboard.

    Input kpi_long columns (expected):
      tenant_id, farm_id, kpi_id, value, unit
    Optional columns: site_id, pen_id
    """

    if kpi_long is None or kpi_long.empty:
        return pd.DataFrame(
            columns=[
                "tenant_id",
                "farm_id",
                "site_id",
                "kpi_id",
                "actual_value",
                "target_value",
                "unit",
                "direction",
                "warn_pct",
                "alert_pct",
                "status",
                "delta",
                "delta_pct",
                "data_version",
                "kpi_run_id",
                "targets_source",
            ]
        )

    df = kpi_long.copy()
    # Minimal normalization
    for c in ["tenant_id", "farm_id", "kpi_id", "value", "unit"]:
        if c not in df.columns:
            raise ValueError(f"kpi_long missing required column '{c}'. Columns={list(df.columns)[:20]}")

    if "site_id" not in df.columns:
        df["site_id"] = pd.NA

    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["kpi_id"] = df["kpi_id"].astype(str)

    rows = []
    targets_source = str(targets_cfg.get("_source") or "")
    for _, r in df.iterrows():
        scope = {
            "tenant_id": str(r.get("tenant_id")),
            "farm_id": str(r.get("farm_id")),
        }
        # site_id is optional
        if r.get("site_id") is not None and not pd.isna(r.get("site_id")):
            scope["site_id"] = str(r.get("site_id"))
        kid = str(r.get("kpi_id"))
        actual = float(r.get("value")) if not pd.isna(r.get("value")) else float("nan")
        unit = str(r.get("unit") or "")

        spec = resolve_target_spec(targets_cfg, kpi_id=kid, scope=scope)
        if spec is None or pd.isna(actual):
            status, delta, delta_pct = ("NO_TARGET" if spec is None else "NO_DATA", float("nan"), float("nan"))
            rows.append(
                {
                    "tenant_id": scope.get("tenant_id"),
                    "farm_id": scope.get("farm_id"),
                    "site_id": scope.get("site_id"),
                    "kpi_id": kid,
                    "actual_value": actual,
                    "target_value": float("nan") if spec is None else spec.target,
                    "unit": unit,
                    "direction": None if spec is None else spec.direction,
                    "warn_pct": None if spec is None else spec.warn_pct,
                    "alert_pct": None if spec is None else spec.alert_pct,
                    "status": status,
                    "delta": delta,
                    "delta_pct": delta_pct,
                    "data_version": data_version,
                    "kpi_run_id": kpi_run_id,
                    "targets_source": targets_source,
                }
            )
            continue

        status, delta, delta_pct = _status(actual, spec)
        rows.append(
            {
                "tenant_id": scope.get("tenant_id"),
                "farm_id": scope.get("farm_id"),
                "site_id": scope.get("site_id"),
                "kpi_id": kid,
                "actual_value": actual,
                "target_value": spec.target,
                "unit": spec.unit or unit,
                "direction": spec.direction,
                "warn_pct": spec.warn_pct,
                "alert_pct": spec.alert_pct,
                "status": status,
                "delta": delta,
                "delta_pct": delta_pct,
                "data_version": data_version,
                "kpi_run_id": kpi_run_id,
                "targets_source": targets_source,
            }
        )

    out = pd.DataFrame(rows)
    # Deterministic ordering
    order_cols = [c for c in ["tenant_id", "farm_id", "site_id", "status", "kpi_id"] if c in out.columns]
    if order_cols:
        out = out.sort_values(order_cols)
    return out


# ----------------------------
# Targets editor helpers (offline-core)
# ----------------------------


def list_target_specs(
    targets_cfg: dict,
    *,
    scope: dict[str, Any],
    kpi_ids: Iterable[str],
) -> pd.DataFrame:
    """Return a table of resolved target specs for a given scope.

    This helper is meant for Web/Streamlit editors: UI can display the table,
    allow user edits, and then call upsert_target_rule()+save_override_yaml().
    """

    rows = []
    for kid in list(kpi_ids):
        spec = resolve_target_spec(targets_cfg, kpi_id=str(kid), scope=scope)
        rows.append(
            {
                "kpi_id": str(kid),
                "target": None if spec is None else spec.target,
                "direction": None if spec is None else spec.direction,
                "warn_pct": None if spec is None else spec.warn_pct,
                "alert_pct": None if spec is None else spec.alert_pct,
                "unit": None if spec is None else spec.unit,
                "source": None if spec is None else spec.source,
            }
        )
    return pd.DataFrame(rows)


def _norm_scope(scope: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in (scope or {}).items():
        if v is None or (isinstance(v, float) and pd.isna(v)):
            continue
        out[str(k)] = str(v)
    return out


def upsert_target_rule(
    targets_cfg: dict,
    *,
    scope: dict[str, Any],
    kpi_updates: dict[str, dict[str, Any]],
    updated_by: str | None = None,
    comment: str | None = None,
) -> dict:
    """Upsert (insert or update) a targets rule for an exact scope.

    - scope is matched by exact equality of normalized key/value pairs.
    - kpi_updates is a dict: kpi_id -> {target, direction, warn_pct, alert_pct, unit}

    Returns a NEW dict (does not mutate input).
    """

    if not isinstance(targets_cfg, dict):
        raise TargetsConfigError("targets_cfg должен быть dict")

    scope_n = _norm_scope(scope)
    if not scope_n.get("tenant_id") or not scope_n.get("farm_id"):
        raise TargetsConfigError("scope должен содержать tenant_id и farm_id")

    # Validate/normalize KPI updates via _parse_spec
    source = str(targets_cfg.get("_source") or "kpi_targets")
    clean_updates: dict[str, dict[str, Any]] = {}
    for kid, spec in (kpi_updates or {}).items():
        if spec is None:
            continue
        _ = _parse_spec(str(kid), dict(spec), source=source)  # validation only
        clean_updates[str(kid)] = {
            "target": float(spec["target"]),
            "direction": str(spec.get("direction") or "higher_better"),
            "warn_pct": float(spec.get("warn_pct", 0.05)),
            "alert_pct": float(spec.get("alert_pct", 0.10)),
        }
        if spec.get("unit") is not None:
            clean_updates[str(kid)]["unit"] = str(spec.get("unit"))

    new_cfg = dict(targets_cfg)
    # Remove internal source; will be re-attached on load
    new_cfg.pop("_source", None)
    new_cfg.setdefault("version", "1")
    new_cfg.setdefault("defaults", {})
    new_cfg["defaults"].setdefault("kpis", {})
    new_cfg.setdefault("targets", [])
    if not isinstance(new_cfg["targets"], list):
        raise TargetsConfigError("targets должен быть list")

    # Find exact-scope rule
    idx = None
    for i, rule in enumerate(new_cfg["targets"]):
        if not isinstance(rule, dict):
            continue
        rscope = _norm_scope(rule.get("scope") or {})
        if rscope == scope_n:
            idx = i
            break

    if idx is None:
        new_rule = {"scope": scope_n, "kpis": dict(clean_updates)}
        new_cfg["targets"].append(new_rule)
    else:
        rule = dict(new_cfg["targets"][idx])
        rule.setdefault("scope", scope_n)
        rule_kpis = dict(rule.get("kpis") or {})
        rule_kpis.update(clean_updates)
        rule["kpis"] = rule_kpis
        new_cfg["targets"][idx] = rule

    meta = dict(new_cfg.get("meta") or {})
    meta["updated_at"] = utc_isoformat_z()
    if updated_by:
        meta["updated_by"] = str(updated_by)
    if comment:
        meta["comment"] = str(comment)
    new_cfg["meta"] = meta
    return new_cfg


def save_override_yaml(
    targets_cfg: dict,
    *,
    override_dir: Path,
    cfg_path: Path = DEFAULT_REL_PATH,
) -> Path:
    """Save override config into override_dir/cfg_path.

    The override mechanism expects cfg_path to be relative.
    """

    cfg_path = Path(cfg_path)
    override_dir = Path(override_dir)
    if cfg_path.is_absolute():
        raise TargetsConfigError("cfg_path должен быть относительным для override")

    out_path = (override_dir / cfg_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Ensure basic keys exist
    obj = dict(targets_cfg)
    obj.pop("_source", None)
    obj.setdefault("version", "1")
    obj.setdefault("defaults", {})
    obj["defaults"].setdefault("kpis", {})
    obj.setdefault("targets", [])

    try:
        text = yaml.safe_dump(obj, sort_keys=False, allow_unicode=True)
        out_path.write_text(text, encoding="utf-8")
    except Exception as e:
        raise TargetsConfigError(f"Не удалось сохранить override YAML {out_path}: {e}")
    return out_path


def reset_override(
    *,
    override_dir: Path,
    cfg_path: Path = DEFAULT_REL_PATH,
) -> bool:
    """Remove override file if exists. Returns True if removed."""

    cfg_path = Path(cfg_path)
    if cfg_path.is_absolute():
        return False
    p = (Path(override_dir) / cfg_path).resolve()
    if p.exists() and p.is_file():
        p.unlink()
        return True
    return False
