
"""Validators for Target canonical model v2.

These validators are used to validate fixture datasets and later can be reused by ingestion/QC pipelines.
They intentionally do not mutate data ("no silent fixes").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Iterable
from pathlib import Path

import pandas as pd

def _df(dfs: dict, key: str) -> 'pd.DataFrame':
    """Safe df getter: avoids boolean evaluation of DataFrame."""
    v = dfs.get(key, None)
    return v if v is not None else pd.DataFrame()


@dataclass(frozen=True)
class Issue:
    severity: str  # ERROR/WARN
    dataset: str
    check: str
    message: str
    row_id: Optional[str] = None
    field: Optional[str] = None
    sample_value: Optional[str] = None

def _pk_series(df: pd.DataFrame, cols: List[str]) -> pd.Series:
    if len(cols) == 1:
        return df[cols[0]].astype(str)
    return df[cols].astype(str).agg("|".join, axis=1)

def validate_pk_unique(dfs: Dict[str, pd.DataFrame], pk_map: Dict[str, List[str]]) -> List[Issue]:
    issues: List[Issue] = []
    for name, pk_cols in pk_map.items():
        df = dfs.get(name)
        if df is None:
            continue
        missing = [c for c in pk_cols if c not in df.columns]
        if missing:
            issues.append(Issue("ERROR", name, "pk_missing_columns", f"Missing PK columns: {missing}"))
            continue
        keys = _pk_series(df, pk_cols)
        dup = keys[keys.duplicated(keep=False)]
        if len(dup) > 0:
            issues.append(Issue("ERROR", name, "pk_duplicates", f"Duplicate PK values found: {dup.iloc[0]}", sample_value=str(dup.iloc[0])))
    return issues

def validate_fk(
    dfs: Dict[str, pd.DataFrame],
    child: str,
    child_col: str,
    parent: str,
    parent_col: str,
    check_name: str,
) -> List[Issue]:
    issues: List[Issue] = []
    cdf = dfs.get(child)
    pdf = dfs.get(parent)
    if cdf is None or pdf is None:
        return issues
    if child_col not in cdf.columns or parent_col not in pdf.columns:
        issues.append(Issue("ERROR", child, check_name, f"Missing FK columns: {child}.{child_col} or {parent}.{parent_col}"))
        return issues
    parent_set = set(pdf[parent_col].dropna().astype(str).tolist())
    # only validate non-null values
    bad_mask = cdf[child_col].notna() & (~cdf[child_col].astype(str).isin(parent_set))
    if bad_mask.any():
        i = bad_mask[bad_mask].index[0]
        val = str(cdf.loc[i, child_col])
        issues.append(Issue("ERROR", child, check_name, f"FK value not found in parent: {val}", row_id=f"{child}:{i+1}", field=child_col, sample_value=val))
    return issues

def validate_target_v2_relations(dfs: Dict[str, pd.DataFrame]) -> List[Issue]:
    """Minimal referential integrity checks for Target v2 fixture datasets."""
    issues: List[Issue] = []

    pk_map = {
        "dm_farms": ["farm_id"],
        "dm_sites": ["site_id"],
        "dm_pens": ["pen_id"],
        "dm_bulls": ["bull_id"],
        "dm_animals": ["animal_id"],
        "dm_lactations": ["lactation_id"],
        "dm_milkings_daily": ["record_id"],
        "dm_testday": ["testday_id"],
        "dm_sensors_daily": ["record_id"],
        "dm_health_events": ["event_id"],
        "dm_treatments": ["treatment_id"],
        "dm_repro_events": ["repro_event_id"],
        "dm_pen_moves": ["move_id"],
        "dm_feed_rations": ["ration_id"],
        "dm_feed_deliveries": ["delivery_id"],
        "dm_prices": ["price_id"],
        "dm_economics_daily": ["record_id"],
        "dm_alerts": ["alert_id"],
        "dm_decisions": ["decision_id"],
        "dm_reports": ["report_id"],
        "dm_users": ["user_id"],
        "dm_roles": ["role_id"],
        "dm_user_roles": ["user_id", "role_id"],
    }
    issues.extend(validate_pk_unique(dfs, pk_map))

    # Core FKs
    issues.extend(validate_fk(dfs, "dm_sites", "farm_id", "dm_farms", "farm_id", "site_farm_fk"))
    issues.extend(validate_fk(dfs, "dm_pens", "site_id", "dm_sites", "site_id", "pen_site_fk"))
    issues.extend(validate_fk(dfs, "dm_animals", "farm_id", "dm_farms", "farm_id", "animal_farm_fk"))
    if "site_id" in (_df(dfs, "dm_animals")).columns:
        issues.extend(validate_fk(dfs, "dm_animals", "site_id", "dm_sites", "site_id", "animal_site_fk"))
    if "current_pen_id" in (_df(dfs, "dm_animals")).columns:
        issues.extend(validate_fk(dfs, "dm_animals", "current_pen_id", "dm_pens", "pen_id", "animal_pen_fk"))

    # Production FKs
    issues.extend(validate_fk(dfs, "dm_lactations", "animal_id", "dm_animals", "animal_id", "lactation_animal_fk"))
    if "lactation_id" in (_df(dfs, "dm_milkings_daily")).columns:
        issues.extend(validate_fk(dfs, "dm_milkings_daily", "lactation_id", "dm_lactations", "lactation_id", "milkings_lactation_fk"))
    issues.extend(validate_fk(dfs, "dm_milkings_daily", "animal_id", "dm_animals", "animal_id", "milkings_animal_fk"))
    issues.extend(validate_fk(dfs, "dm_testday", "animal_id", "dm_animals", "animal_id", "testday_animal_fk"))
    if "lactation_id" in (_df(dfs, "dm_testday")).columns:
        issues.extend(validate_fk(dfs, "dm_testday", "lactation_id", "dm_lactations", "lactation_id", "testday_lactation_fk"))

    # Sensors / health / treatments / repro
    issues.extend(validate_fk(dfs, "dm_sensors_daily", "animal_id", "dm_animals", "animal_id", "sensors_animal_fk"))
    issues.extend(validate_fk(dfs, "dm_health_events", "animal_id", "dm_animals", "animal_id", "health_animal_fk"))
    issues.extend(validate_fk(dfs, "dm_treatments", "animal_id", "dm_animals", "animal_id", "treat_animal_fk"))
    if "reason_event_id" in (_df(dfs, "dm_treatments")).columns:
        issues.extend(validate_fk(dfs, "dm_treatments", "reason_event_id", "dm_health_events", "event_id", "treat_event_fk"))
    issues.extend(validate_fk(dfs, "dm_repro_events", "animal_id", "dm_animals", "animal_id", "repro_animal_fk"))
    if "bull_id" in (_df(dfs, "dm_repro_events")).columns:
        issues.extend(validate_fk(dfs, "dm_repro_events", "bull_id", "dm_bulls", "bull_id", "repro_bull_fk"))

    # Moves / feed
    issues.extend(validate_fk(dfs, "dm_pen_moves", "animal_id", "dm_animals", "animal_id", "move_animal_fk"))
    issues.extend(validate_fk(dfs, "dm_pen_moves", "to_pen_id", "dm_pens", "pen_id", "move_to_pen_fk"))
    if "from_pen_id" in (_df(dfs, "dm_pen_moves")).columns:
        issues.extend(validate_fk(dfs, "dm_pen_moves", "from_pen_id", "dm_pens", "pen_id", "move_from_pen_fk"))
    issues.extend(validate_fk(dfs, "dm_feed_rations", "site_id", "dm_sites", "site_id", "ration_site_fk"))
    issues.extend(validate_fk(dfs, "dm_feed_deliveries", "ration_id", "dm_feed_rations", "ration_id", "delivery_ration_fk"))
    issues.extend(validate_fk(dfs, "dm_feed_deliveries", "pen_id", "dm_pens", "pen_id", "delivery_pen_fk"))

    # Reports / decisions / alerts
    issues.extend(validate_fk(dfs, "dm_alerts", "farm_id", "dm_farms", "farm_id", "alert_farm_fk"))
    issues.extend(validate_fk(dfs, "dm_decisions", "farm_id", "dm_farms", "farm_id", "decision_farm_fk"))
    issues.extend(validate_fk(dfs, "dm_reports", "farm_id", "dm_farms", "farm_id", "report_farm_fk"))
    if "source_alert_id" in (_df(dfs, "dm_decisions")).columns:
        issues.extend(validate_fk(dfs, "dm_decisions", "source_alert_id", "dm_alerts", "alert_id", "decision_alert_fk"))

    # RBAC FKs
    issues.extend(validate_fk(dfs, "dm_user_roles", "user_id", "dm_users", "user_id", "userrole_user_fk"))
    issues.extend(validate_fk(dfs, "dm_user_roles", "role_id", "dm_roles", "role_id", "userrole_role_fk"))
    return issues

def load_fixture_folder(folder: str) -> Dict[str, pd.DataFrame]:
    """Load CSV fixtures named dm_*.csv into a dict keyed by basename without extension."""
    path = Path(folder)
    dfs: Dict[str, pd.DataFrame] = {}
    for p in sorted(path.glob("dm_*.csv")):
        name = p.stem
        dfs[name] = pd.read_csv(p)
    return dfs