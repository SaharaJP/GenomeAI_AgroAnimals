from __future__ import annotations

"""Mastitis risk ML pipeline (MVP+ / Target step T4-02).

IMPORTANT POLICY:
- We DO NOT diagnose disease. We only estimate *risk* on a horizon N days and suggest actions:
  check / inspect / sample / re-check.
- The web layer must not compute anything; it calls these offline-core functions / CLI.

Artifacts layout (aligned with existing MVP):
  artifacts/<data_version>/mastitis/models/<model_version>/
  artifacts/<data_version>/mastitis/scoring/<scoring_run>/
  artifacts/<data_version>/runs/<run_id>/ ... (for cow_day mart, built by marts_timeseries)

Versions to propagate: data_version, qc_run, model_version, scoring_run, report_version.
"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .sensor_anomaly_v1 import load_cow_day
from .versioning import generate_run_id, write_json, write_checksums
from .explainability_v1 import save_explainability_profile, load_explainability_profile, explain_row


DEFAULT_CFG_PATH = Path("configs/mastitis_risk.yaml")



def _resolve_canonical_dir(artifacts_root: Path, data_version: str) -> Path:
    """Support both layouts:
    - artifacts/<data_version>/canonical (legacy MVP)
    - artifacts/canonical/<data_version> (Target/web fixtures)
    """
    p1 = artifacts_root / data_version / "canonical"
    p2 = artifacts_root / "canonical" / data_version
    if p2.exists():
        return p2
    return p1

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_canonical_table(canonical_dir: Path, dataset: str) -> pd.DataFrame:
    pqt = canonical_dir / f"{dataset}.parquet"
    if pqt.exists():
        try:
            return pd.read_parquet(pqt)
        except Exception:
            pass
    csv = canonical_dir / f"{dataset}.csv"
    if not csv.exists():
        return pd.DataFrame()
    return pd.read_csv(csv)


def _to_dt(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce")


def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        v = float(x)
        if np.isfinite(v):
            return v
        return None
    except Exception:
        return None


def _load_cfg(path: Path = DEFAULT_CFG_PATH) -> Dict[str, Any]:
    # YAML is optional dependency elsewhere; we keep JSON-like fallback if yaml missing.
    try:
        import yaml  # type: ignore

        obj = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _mastitis_event_mask(health_events: pd.DataFrame, mastitis_codes: List[str]) -> pd.Series:
    if health_events.empty:
        return pd.Series([False] * 0, dtype=bool)
    code = health_events.get("condition_code")
    if code is None:
        return pd.Series([False] * len(health_events), dtype=bool)
    code_s = code.astype("string").str.upper()
    codes = [str(c).upper() for c in mastitis_codes if str(c).strip()]
    if not codes:
        return pd.Series([False] * len(health_events), dtype=bool)
    mask = pd.Series([False] * len(health_events), dtype=bool)
    for c in codes:
        # exact match OR substring match (fallback across vendors)
        mask = mask | (code_s == c) | code_s.str.contains(c, na=False)
    return mask


def _build_labels_from_health_events(
    cow_day: pd.DataFrame,
    health_events: pd.DataFrame,
    *,
    horizon_days: int,
    mastitis_codes: List[str],
) -> Tuple[pd.Series, Dict[str, Any]]:
    """Label y(date)=1 if mastitis event occurs in (date, date+horizon_days]."""
    meta: Dict[str, Any] = {"label_source": "health_events", "fallback_used": False}

    if cow_day.empty:
        return pd.Series(dtype="int64"), meta

    if health_events.empty:
        meta["fallback_used"] = True
        meta["label_source"] = "fallback_scc"
        return pd.Series([0] * len(cow_day), index=cow_day.index, dtype="int64"), meta

    he = health_events.copy()
    he["event_date_dt"] = _to_dt(he.get("event_date")).dt.floor("D")
    mask_m = _mastitis_event_mask(he, mastitis_codes)
    he = he.loc[mask_m].copy()
    if he.empty:
        meta["fallback_used"] = True
        meta["label_source"] = "fallback_scc"
        return pd.Series([0] * len(cow_day), index=cow_day.index, dtype="int64"), meta

    # Build a lookup: (farm_id, animal_id) -> sorted event dates
    he = he[[c for c in ["farm_id", "animal_id", "event_date_dt"] if c in he.columns]].dropna(subset=["animal_id", "event_date_dt"])
    if "farm_id" not in he.columns:
        he["farm_id"] = pd.NA
    he = he.sort_values(["farm_id", "animal_id", "event_date_dt"])
    grouped = he.groupby(["farm_id", "animal_id"], dropna=False)["event_date_dt"].apply(list).to_dict()

    dates = pd.to_datetime(cow_day["date"], errors="coerce").dt.floor("D")
    farm = cow_day.get("farm_id")
    if farm is None:
        farm = pd.Series([pd.NA] * len(cow_day), index=cow_day.index)
    animal = cow_day.get("animal_id").astype("string")

    y = pd.Series([0] * len(cow_day), index=cow_day.index, dtype="int64")
    for idx, (f, a, d) in enumerate(zip(farm, animal, dates)):
        if pd.isna(d) or pd.isna(a):
            continue
        key = (f, a)
        ev = grouped.get(key)
        if not ev:
            continue
        # Find if any event date is in (d, d+horizon]
        d0 = d.to_pydatetime().date()
        d1 = (d + pd.Timedelta(days=horizon_days)).to_pydatetime().date()
        # list of pandas Timestamps
        ok = False
        for t in ev:
            if t is pd.NaT:
                continue
            td = t.to_pydatetime().date()
            if td > d0 and td <= d1:
                ok = True
                break
        if ok:
            y.iloc[idx] = 1
    meta["n_positive"] = int(y.sum())
    meta["n_total"] = int(len(y))
    return y, meta


def _apply_fallback_label_from_scc(
    cow_day: pd.DataFrame,
    *,
    horizon_days: int,
    scc_high: float,
) -> Tuple[pd.Series, Dict[str, Any]]:
    """Fallback label proxy: future SCC spike above threshold."""
    meta: Dict[str, Any] = {"label_source": "fallback_scc", "fallback_used": True, "scc_high": scc_high}
    if cow_day.empty or "scc_cells_ml" not in cow_day.columns:
        return pd.Series([0] * len(cow_day), index=cow_day.index, dtype="int64"), meta
    df = cow_day.copy()
    df["date_dt"] = pd.to_datetime(df["date"], errors="coerce").dt.floor("D")
    df["scc"] = pd.to_numeric(df["scc_cells_ml"], errors="coerce")
    df = df.sort_values(["farm_id", "animal_id", "date_dt"], kind="mergesort")
    # For each row, check future max SCC in next horizon
    y = pd.Series([0] * len(df), index=df.index, dtype="int64")
    gcols = [c for c in ["farm_id", "animal_id"] if c in df.columns]
    for _, g in df.groupby(gcols, dropna=False):
        s = g["scc"].to_numpy()
        # build forward max within window (simple O(n*h), but ok for MVP scale)
        idxs = g.index.to_list()
        dates = g["date_dt"].to_list()
        for i in range(len(idxs)):
            d0 = dates[i]
            if pd.isna(d0):
                continue
            d1 = d0 + pd.Timedelta(days=horizon_days)
            m = None
            for j in range(i + 1, len(idxs)):
                if pd.isna(dates[j]):
                    continue
                if dates[j] > d1:
                    break
                v = s[j]
                if np.isfinite(v):
                    m = v if m is None else max(m, v)
            if m is not None and m >= scc_high:
                y.loc[idxs[i]] = 1
    meta["n_positive"] = int(y.sum())
    meta["n_total"] = int(len(y))
    return y, meta


def _rolling_features(df: pd.DataFrame, col: str, windows: List[int]) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    s = pd.to_numeric(df[col], errors="coerce")
    g = df.groupby(["farm_id", "animal_id"], dropna=False)[s.name]
    for w in windows:
        out[f"{col}_mean_{w}d"] = g.apply(lambda x: x.rolling(window=w, min_periods=1).mean()).reset_index(level=[0, 1], drop=True)
        out[f"{col}_std_{w}d"] = g.apply(lambda x: x.rolling(window=w, min_periods=2).std()).reset_index(level=[0, 1], drop=True)
        out[f"{col}_min_{w}d"] = g.apply(lambda x: x.rolling(window=w, min_periods=1).min()).reset_index(level=[0, 1], drop=True)
        out[f"{col}_max_{w}d"] = g.apply(lambda x: x.rolling(window=w, min_periods=1).max()).reset_index(level=[0, 1], drop=True)
    return out


def build_mastitis_dataset(
    *,
    artifacts_root: Path,
    data_version: str,
    horizon_days: int = 7,
    lookback_windows: Optional[List[int]] = None,
    cfg_path: Path = DEFAULT_CFG_PATH,
) -> Tuple[pd.DataFrame, pd.Series, Dict[str, Any]]:
    """Build cow_day-level dataset for mastitis risk.

    Row unit: (farm_id, animal_id, date) == cow_day.
    Features are computed using ONLY current and past data (rolling windows).
    Label uses future window (date, date+horizon_days] based on dm_health_events mastitis codes,
    with fallback proxy from SCC if no codes.
    """
    artifacts_root = Path(artifacts_root).resolve()
    base = artifacts_root / data_version
    canonical_dir = _resolve_canonical_dir(artifacts_root, data_version)

    cfg = _load_cfg(cfg_path)
    mastitis_codes = cfg.get("mastitis_codes") or ["MASTITIS", "MAST"]
    horizon_days = int(cfg.get("horizon_days", horizon_days))
    scc_high = float(cfg.get("fallback_scc_high", 500000))
    lookback_windows = lookback_windows or [3, 7, 14, 21]

    cow_day = load_cow_day(artifacts_root=artifacts_root, data_version=data_version)
    if cow_day.empty:
        return pd.DataFrame(), pd.Series(dtype="int64"), {"ok": False, "reason": "cow_day_missing"}

    df = cow_day.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.floor("D")
    # Normalize required columns
    if "farm_id" not in df.columns:
        df["farm_id"] = pd.NA
    df["animal_id"] = df.get("animal_id").astype("string")

    # Add parity (lactation_no) and DIM if present in cow_day
    lact = _read_canonical_table(canonical_dir, "dm_lactations")
    if not lact.empty and all(c in lact.columns for c in ["animal_id", "lactation_id"]):
        # Choose the latest row per lactation_id as static attrs (parity/lactation_no)
        use_cols = [c for c in ["animal_id", "lactation_id", "lactation_no", "parity"] if c in lact.columns]
        tmp = lact[use_cols].copy()
        tmp["lactation_no"] = pd.to_numeric(tmp.get("lactation_no", tmp.get("parity")), errors="coerce")
        tmp = tmp.drop_duplicates(subset=["animal_id", "lactation_id"], keep="last")
        df = df.merge(tmp[["animal_id", "lactation_id", "lactation_no"]], on=["animal_id", "lactation_id"], how="left")
    else:
        df["lactation_no"] = pd.NA

    # Basic numeric columns
    num_cols = [c for c in ["milk_kg", "milk_kg_ffill3", "fat_pct", "protein_pct", "scc_cells_ml", "activity_steps", "activity_steps_ffill3", "rumination_min", "rumination_min_ffill3", "body_temp_c", "body_temp_c_ffill3", "dim"] if c in df.columns]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # add ffill for SCC and milkings-derived columns if needed
    if "scc_cells_ml" in df.columns:
        df["scc_cells_ml_ffill3"] = df.groupby(["farm_id", "animal_id"], dropna=False)["scc_cells_ml"].apply(lambda s: s.ffill(limit=3)).reset_index(level=[0, 1], drop=True)
    else:
        df["scc_cells_ml_ffill3"] = pd.NA

    # Rolling features
    feat_parts: List[pd.DataFrame] = []
    # core signals
    for base_col in ["milk_kg_ffill3", "activity_steps_ffill3", "rumination_min_ffill3", "body_temp_c_ffill3", "scc_cells_ml_ffill3"]:
        if base_col in df.columns:
            feat_parts.append(_rolling_features(df, base_col, lookback_windows))

    X = pd.concat(feat_parts, axis=1) if feat_parts else pd.DataFrame(index=df.index)

    # Static features
    X["lactation_no"] = pd.to_numeric(df.get("lactation_no"), errors="coerce")
    X["dim"] = pd.to_numeric(df.get("dim"), errors="coerce")
    X["is_observed_milkings"] = df.get("is_observed_milkings", False).astype(int)
    X["is_observed_sensors"] = df.get("is_observed_sensors", False).astype(int)

    # Label
    health_events = _read_canonical_table(canonical_dir, "dm_health_events")
    y, y_meta = _build_labels_from_health_events(df, health_events, horizon_days=horizon_days, mastitis_codes=list(mastitis_codes))
    if bool(y_meta.get("fallback_used")):
        y, y_meta = _apply_fallback_label_from_scc(df, horizon_days=horizon_days, scc_high=scc_high)

    # Drop rows with no date or animal_id (non-traceable)
    ok = df["date"].notna() & df["animal_id"].notna()
    df = df.loc[ok].copy()
    X = X.loc[ok].copy()
    y = y.loc[ok].copy()

    # Add row_id trace
    X["_row_id"] = df["farm_id"].astype("string") + "|" + df["animal_id"].astype("string") + "|" + df["date"].dt.date.astype("string")
    meta: Dict[str, Any] = {
        "ok": True,
        "data_version": data_version,
        "horizon_days": horizon_days,
        "lookback_windows": lookback_windows,
        **y_meta,
        "n_rows": int(len(X)),
        "feature_count": int(X.shape[1] - 1),
        "date_min": str(df["date"].min().date()) if df["date"].notna().any() else None,
        "date_max": str(df["date"].max().date()) if df["date"].notna().any() else None,
    }
    return X, y, meta


def time_based_split(
    X: pd.DataFrame,
    y: pd.Series,
    *,
    dates: pd.Series,
    horizon_days: int,
    test_fraction: float = 0.2,
) -> Tuple[pd.Index, pd.Index, Dict[str, Any]]:
    """Time-based split with anti-leakage guard for future label window.

    We ensure:
      max(train_date) + horizon_days < min(test_date)
    """
    d = pd.to_datetime(dates, errors="coerce").dt.floor("D")
    ok = d.notna()
    if int(ok.sum()) < 30:
        raise ValueError("Not enough dated rows for time split (need >= 30)")
    idx = X.index[ok]
    d2 = d.loc[idx]
    order = d2.sort_values(kind="mergesort")
    n = len(order)
    cut = int(n * (1.0 - test_fraction))
    cut = min(max(cut, 1), n - 1)
    # initial split by fraction, then enforce anti-leakage gap by dropping early test dates
    for cut2 in range(cut, 1, -1):
        train_idx = order.index[:cut2]
        max_train = d2.loc[train_idx].max()
        gap_end = max_train + pd.Timedelta(days=horizon_days)
        test_full = list(order.index[cut2:])
        test_idx_list = [i for i in test_full if d2.loc[i] > gap_end]
        if len(test_idx_list) >= 1:
            test_idx = pd.Index(test_idx_list)
            break
    else:
        raise ValueError('Cannot construct time split with requested horizon_days; insufficient date range')

    min_test = d2.loc[test_idx].min() if len(test_idx) else pd.NaT
    meta = {
        "strategy": "time_fraction",
        "test_fraction": float(test_fraction),
        "n_total": int(n),
        "n_train": int(len(train_idx)),
        "n_test": int(len(test_idx)),
        "train_max_date": str(pd.to_datetime(max_train).date()) if pd.notna(max_train) else None,
        "test_min_date": str(pd.to_datetime(min_test).date()) if pd.notna(min_test) else None,
        "anti_leakage_horizon_days": int(horizon_days),
    }
    return train_idx, test_idx, meta


@dataclass
class MastitisTrainSummary:
    schema: str
    created_at_utc: str
    data_version: str
    qc_run: Optional[str]
    model_version: str
    horizon_days: int
    label: Dict[str, Any]
    split: Dict[str, Any]
    metrics: Dict[str, float]
    thresholds: Dict[str, Any]
    outputs: Dict[str, str]
    limitations: Dict[str, Any]


def _eval_at_k(y_true: np.ndarray, y_score: np.ndarray, k: int) -> Tuple[float, float]:
    # k as count (top-k)
    if k <= 0:
        return 0.0, 0.0
    k = min(k, len(y_score))
    idx = np.argsort(-y_score)[:k]
    tp = float((y_true[idx] == 1).sum())
    prec = tp / float(k) if k else 0.0
    rec = tp / float((y_true == 1).sum()) if float((y_true == 1).sum()) > 0 else 0.0
    return float(prec), float(rec)


def train_mastitis_risk_model(
    *,
    artifacts_root: Path,
    data_version: str,
    qc_run: Optional[str] = None,
    model_version: Optional[str] = None,
    horizon_days: int = 7,
    cfg_path: Path = DEFAULT_CFG_PATH,
) -> Dict[str, Any]:
    """Train mastitis risk classifier and save artifacts."""
    artifacts_root = Path(artifacts_root).resolve()
    mv = model_version or generate_run_id(prefix="mastitis_model")
    base = artifacts_root / data_version / "mastitis" / "models" / mv
    base.mkdir(parents=True, exist_ok=True)

    X, y, meta = build_mastitis_dataset(artifacts_root=artifacts_root, data_version=data_version, horizon_days=horizon_days, cfg_path=cfg_path)
    if not bool(meta.get("ok")):
        return {"ok": False, "reason": meta.get("reason"), "meta": meta}

    # Separate row_id and date
    row_id = X["_row_id"].astype("string")
    X_model = X.drop(columns=["_row_id"]).copy()

    cow_day = load_cow_day(artifacts_root=artifacts_root, data_version=data_version)
    cow_day = cow_day.copy()
    cow_day["date"] = pd.to_datetime(cow_day["date"], errors="coerce").dt.floor("D")
    # align dates to X index
    dates = pd.to_datetime(cow_day.loc[X.index, "date"], errors="coerce")

    train_idx, test_idx, split_meta = time_based_split(X_model, y, dates=dates, horizon_days=int(meta.get("horizon_days", horizon_days)))

    # sklearn pipeline
    from joblib import dump
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.metrics import average_precision_score
    from sklearn.pipeline import Pipeline

    numeric = [c for c in X_model.columns if c not in []]
    pre = ColumnTransformer(
        transformers=[
            (
                "num",
                Pipeline(steps=[("imputer", SimpleImputer(strategy="median"))]),
                numeric,
            ),
        ],
        remainder="drop",
    )
    clf = GradientBoostingClassifier(random_state=42)
    pipe = Pipeline(steps=[("pre", pre), ("model", clf)])

    X_train = X_model.loc[train_idx]
    y_train = y.loc[train_idx]
    X_test = X_model.loc[test_idx]
    y_test = y.loc[test_idx]

    # If label is too imbalanced / empty, fail fast with explanation
    if int(y_train.sum()) < 5 or int(y_test.sum()) < 2:
        limitations = {
            "reason": "not_enough_positive_examples",
            "y_train_pos": int(y_train.sum()),
            "y_test_pos": int(y_test.sum()),
            "tip": "Provide longer history or correct mastitis codes; fallback SCC may still be sparse.",
        }
        write_json(base / "limitations.json", limitations)
        return {"ok": False, "reason": "NOT_ENOUGH_POSITIVES", "limitations": limitations, "model_version": mv}

    pipe.fit(X_train, y_train)
    proba = pipe.predict_proba(X_test)[:, 1]

    pr_auc = float(average_precision_score(y_test, proba))

    # metrics at K (top % of cows/day)
    k_list = [50, 100]
    metrics = {"pr_auc": pr_auc, "n_train": int(len(X_train)), "n_test": int(len(X_test)), "pos_train": int(y_train.sum()), "pos_test": int(y_test.sum())}
    for k in k_list:
        p, r = _eval_at_k(y_test.to_numpy(), proba, k=k)
        metrics[f"precision_at_{k}"] = p
        metrics[f"recall_at_{k}"] = r

    # business threshold
    cfg = _load_cfg(cfg_path)
    thr = float(cfg.get("risk_threshold", 0.7))
    cost_fp = _safe_float(cfg.get("cost_false_alert")) or 1.0
    cost_fn = _safe_float(cfg.get("cost_missed_case")) or 10.0
    thresholds = {
        "risk_threshold": thr,
        "cost_false_alert": float(cost_fp),
        "cost_missed_case": float(cost_fn),
    }

    # save model + cards
    model_path = base / "model.joblib"
    dump(pipe, model_path)

    pred_df = pd.DataFrame({"row_id": row_id.loc[test_idx].values, "y_true": y_test.values, "y_proba": proba})
    pred_path = base / "test_predictions.csv"
    pred_df.to_csv(pred_path, index=False, encoding="utf-8")

    # global importance (best-effort): use model.feature_importances_ after pre
    importance_path = base / "feature_importance.csv"
    explain_profile_path = base / "explainability_profile.json"
    try:
        # Feature names = numeric list (since only numeric used)
        imp = pipe.named_steps["model"].feature_importances_
        imp_df = pd.DataFrame({"feature": numeric, "importance": imp}).sort_values("importance", ascending=False)
        imp_df.to_csv(importance_path, index=False, encoding="utf-8")
    except Exception:
        imp = np.zeros(len(numeric), dtype=float)
        pd.DataFrame(columns=["feature", "importance"]).to_csv(importance_path, index=False, encoding="utf-8")

    explain_cfg = cfg.get("explainability") if isinstance(cfg, dict) else {}
    feature_rules = (explain_cfg or {}).get("feature_rules") or {
        "scc_cells_ml": "higher_increases_risk",
        "scc_cells_ml_mean_3d": "higher_increases_risk",
        "scc_cells_ml_mean_7d": "higher_increases_risk",
        "milk_kg": "lower_increases_risk",
        "milk_kg_mean_3d": "lower_increases_risk",
        "milk_kg_mean_7d": "lower_increases_risk",
        "rumination_min": "lower_increases_risk",
        "rumination_min_mean_3d": "lower_increases_risk",
        "rumination_min_mean_7d": "lower_increases_risk",
        "body_temp_c": "higher_increases_risk",
        "body_temp_c_mean_3d": "higher_increases_risk",
        "body_temp_c_mean_7d": "higher_increases_risk",
    }
    baseline_median = {str(k): float(v) for k, v in X_train.median(numeric_only=True).to_dict().items() if np.isfinite(v)}
    baseline_scale_raw = X_train.std(numeric_only=True).replace(0, np.nan).fillna(1.0).to_dict()
    baseline_scale = {str(k): float(v) for k, v in baseline_scale_raw.items() if np.isfinite(v)}
    save_explainability_profile(
        model_dir=base,
        features=list(numeric),
        feature_importances=[float(x) for x in imp],
        baseline_median=baseline_median,
        baseline_scale=baseline_scale,
        feature_rules=feature_rules,
        top_k=int((explain_cfg or {}).get("top_k", 3)),
    )

    summary = MastitisTrainSummary(
        schema="genomeai.mastitis.train_summary.v1",
        created_at_utc=_utc_now_iso(),
        data_version=data_version,
        qc_run=qc_run,
        model_version=mv,
        horizon_days=int(meta.get("horizon_days", horizon_days)),
        label={k: meta.get(k) for k in ["label_source", "fallback_used", "n_positive", "n_total", "scc_high"] if k in meta},
        split=split_meta,
        metrics=metrics,
        thresholds=thresholds,
        outputs={
            "model_joblib": str(model_path),
            "test_predictions_csv": str(pred_path),
            "feature_importance_csv": str(importance_path),
            "explainability_profile_json": str(explain_profile_path),
        },
        limitations={
            "no_diagnosis": True,
            "note": "Model predicts risk only. Must be used for decision-support: check/inspect/sample.",
        },
    )
    write_json(base / "train_summary.json", asdict(summary))

    # Model card md
    md = [
        f"# Model Card: {mv}",
        "",
        f"- data_version: {data_version}",
        f"- qc_run: {qc_run}",
        f"- trained_at_utc: {summary.created_at_utc}",
        "",
        "## Task",
        f"Binary classification: mastitis risk within next {summary.horizon_days} days.",
        "",
        "## Label",
        f"Source: {summary.label.get('label_source')} (fallback_used={summary.label.get('fallback_used')})",
        "",
        "## Validation",
        f"Time-based split: {split_meta}",
        "",
        "## Metrics",
        "- PR-AUC: {:.4f}".format(pr_auc),
        "",
        "## Policy",
        "No diagnosis. Output is a risk score and suggested actions only.",
    ]
    (base / "model_card.md").write_text("\n".join(md), encoding="utf-8")

    # checksums for integrity
    write_checksums(run_root=base)

    return {"ok": True, "data_version": data_version, "qc_run": qc_run, "model_version": mv, "metrics": metrics, "model_dir": str(base)}


@dataclass
class MastitisScoringSummary:
    schema: str
    created_at_utc: str
    data_version: str
    model_version: str
    scoring_run: str
    asof_date: str
    horizon_days: int
    risk_threshold: float
    outputs: Dict[str, str]


def score_mastitis_risk(
    *,
    artifacts_root: Path,
    data_version: str,
    model_version: str,
    scoring_run: Optional[str] = None,
    asof_date: Optional[str] = None,
    cfg_path: Path = DEFAULT_CFG_PATH,
) -> Dict[str, Any]:
    """Score mastitis risk for cow_day as of a given date (default=max date)."""
    artifacts_root = Path(artifacts_root).resolve()
    sr = scoring_run or generate_run_id(prefix="mastitis_score")
    model_dir = artifacts_root / data_version / "mastitis" / "models" / model_version
    if not model_dir.exists():
        return {"ok": False, "reason": f"model_not_found:{model_dir}"}

    from joblib import load

    pipe = load(model_dir / "model.joblib")

    cow_day = load_cow_day(artifacts_root=artifacts_root, data_version=data_version)
    if cow_day.empty:
        return {"ok": False, "reason": "cow_day_missing"}
    cow_day = cow_day.copy()
    cow_day["date"] = pd.to_datetime(cow_day["date"], errors="coerce").dt.floor("D")

    # Determine as-of date
    if asof_date:
        asof = pd.to_datetime(asof_date, errors="coerce").floor("D")
    else:
        asof = cow_day["date"].max()
    if pd.isna(asof):
        return {"ok": False, "reason": "asof_date_invalid"}

    cfg = _load_cfg(cfg_path)
    horizon = int(cfg.get("horizon_days", 7))

    X, _y_dummy, meta = build_mastitis_dataset(artifacts_root=artifacts_root, data_version=data_version, horizon_days=horizon, cfg_path=cfg_path)
    if not bool(meta.get("ok")):
        return {"ok": False, "reason": meta.get("reason"), "meta": meta}

    # align to asof date only
    cd = cow_day.loc[X.index].copy()
    mask = (cd["date"] == asof)
    X_today = X.loc[mask].copy()
    if X_today.empty:
        return {"ok": False, "reason": "no_rows_for_asof", "asof_date": str(asof.date())}

    row_id = X_today.pop("_row_id").astype("string")
    proba = pipe.predict_proba(X_today)[:, 1]

    thr = float(cfg.get("risk_threshold", 0.7))

    out_dir = artifacts_root / data_version / "mastitis" / "scoring" / sr
    out_dir.mkdir(parents=True, exist_ok=True)

    out_df = pd.DataFrame(
        {
            "row_id": row_id.values,
            "farm_id": cd.loc[mask, "farm_id"].astype("string").values,
            "animal_id": cd.loc[mask, "animal_id"].astype("string").values,
            "date": cd.loc[mask, "date"].dt.date.astype("string").values,
            "risk_proba": proba,
            "risk_flag": (proba >= thr).astype(int),
        },
        index=X_today.index,
    ).sort_values("risk_proba", ascending=False)

    # Basic "reasons" (explainability, v1): derive from raw signals (not diagnosis)
    # We attach top 3 heuristic drivers for user friendliness and audit.
    # This is not a model explanation; it is a facts-based highlight.
    try:
        cd2 = cow_day.copy().sort_values(["farm_id", "animal_id", "date"], kind="mergesort")
        # last 7 days baseline
        cd2["milk_kg"] = pd.to_numeric(cd2.get("milk_kg"), errors="coerce")
        cd2["scc"] = pd.to_numeric(cd2.get("scc_cells_ml"), errors="coerce")
        cd2["rum"] = pd.to_numeric(cd2.get("rumination_min"), errors="coerce")
        cd2["temp"] = pd.to_numeric(cd2.get("body_temp_c"), errors="coerce")
        # map reasons per animal on asof date
        key_cols = ["farm_id", "animal_id", "date"]
        cd2_idx = cd2.set_index(key_cols, drop=False)
        reasons = []
        for _, r in out_df.iterrows():
            k = (r["farm_id"], r["animal_id"], pd.to_datetime(r["date"]).floor("D"))
            if k not in cd2_idx.index:
                reasons.append("insufficient_data")
                continue
            row = cd2_idx.loc[k]
            # row may be DataFrame if dup; take last
            if isinstance(row, pd.DataFrame):
                row = row.iloc[-1]
            facts = []
            if "scc" in row and np.isfinite(row["scc"]) and row["scc"] >= float(cfg.get("scc_attention", 300000)):
                facts.append("SCC_high")
            if "milk_kg" in row and np.isfinite(row["milk_kg"]) and row["milk_kg"] <= float(cfg.get("milk_low_kg", 15.0)):
                facts.append("milk_low")
            if "rum" in row and np.isfinite(row["rum"]) and row["rum"] <= float(cfg.get("rumination_low_min", 350)):
                facts.append("rumination_low")
            if "temp" in row and np.isfinite(row["temp"]) and row["temp"] >= float(cfg.get("temp_high_c", 39.5)):
                facts.append("temp_high")
            reasons.append(",".join(facts[:3]) if facts else "no_strong_fact_signals")
        out_df["why_facts"] = reasons
    except Exception:
        out_df["why_facts"] = "no_strong_fact_signals"

    explain_profile = load_explainability_profile(model_dir)
    explanation_rows = []
    try:
        score_features = X_today.copy()
        for idx in out_df.index.tolist():
            exp = explain_row(row=out_df.loc[idx], score_df=score_features, pipe=pipe, profile=explain_profile, cfg=cfg)
            out_df.loc[idx, "explain_top_factors_json"] = json.dumps(exp.get("top_factors") or [], ensure_ascii=False)
            out_df.loc[idx, "explain_top_factors_text"] = str(exp.get("top_factors_text") or "")
            out_df.loc[idx, "explain_counterfactuals_json"] = json.dumps(exp.get("counterfactuals") or [], ensure_ascii=False)
            out_df.loc[idx, "explain_counterfactuals_text"] = str(exp.get("counterfactuals_text") or "")
            explanation_rows.append({
                "row_id": str(out_df.loc[idx, "row_id"]),
                "farm_id": str(out_df.loc[idx, "farm_id"]),
                "animal_id": str(out_df.loc[idx, "animal_id"]),
                "date": str(out_df.loc[idx, "date"]),
                "risk_proba": float(out_df.loc[idx, "risk_proba"]),
                "top_factors_json": out_df.loc[idx, "explain_top_factors_json"],
                "top_factors_text": out_df.loc[idx, "explain_top_factors_text"],
                "counterfactuals_json": out_df.loc[idx, "explain_counterfactuals_json"],
                "counterfactuals_text": out_df.loc[idx, "explain_counterfactuals_text"],
            })
    except Exception:
        out_df["explain_top_factors_json"] = "[]"
        out_df["explain_top_factors_text"] = "insufficient_explainability_data"
        out_df["explain_counterfactuals_json"] = "[]"
        out_df["explain_counterfactuals_text"] = "no_simple_counterfactual"

    risk_csv = out_dir / "mastitis_risk_scores.csv"
    out_df.to_csv(risk_csv, index=False, encoding="utf-8")
    explanations_csv = out_dir / "mastitis_explanations.csv"
    pd.DataFrame(explanation_rows or []).to_csv(explanations_csv, index=False, encoding="utf-8")

    summary = MastitisScoringSummary(
        schema="genomeai.mastitis.scoring_summary.v1",
        created_at_utc=_utc_now_iso(),
        data_version=data_version,
        model_version=model_version,
        scoring_run=sr,
        asof_date=str(asof.date()),
        horizon_days=int(cfg.get("horizon_days", 7)),
        risk_threshold=thr,
        outputs={"risk_scores_csv": str(risk_csv), "explanations_csv": str(explanations_csv)},
    )
    write_json(out_dir / "scoring_summary.json", asdict(summary))
    write_checksums(run_root=out_dir)

    return {
        "ok": True,
        "data_version": data_version,
        "model_version": model_version,
        "scoring_run": sr,
        "asof_date": str(asof.date()),
        "scoring_dir": str(out_dir),
        "outputs": {"risk_scores_csv": str(risk_csv), "explanations_csv": str(explanations_csv)},
    }
