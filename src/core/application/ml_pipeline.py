from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from math import sqrt
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import yaml

from core.application.ml_registry import (
    MlConfigRef,
    load_ml_pipeline_config,
    register_model_manifest,
    register_scoring_manifest,
    write_best_effort_ml_audit,
)
from genomeai.explainability_v1 import (
    aggregate_native_feature_importances,
    explain_regression_row,
    infer_prediction_rules_from_sensitivity,
    load_explainability_profile,
    safe_abs_correlation,
    save_explainability_profile,
)
from genomeai.versioning import (
    compute_data_version,
    copy_tree_into_run,
    generate_run_id,
    get_run_root,
    write_checksums,
    write_json,
    write_run_manifest,
)


@dataclass
class TrainSummary:
    schema: str
    created_at_utc: str
    data_version: str
    qc_run: str
    qc_status: str
    model_version: str
    config_version: str
    seed: int
    target: str
    features: Dict[str, Any]
    split: Dict[str, Any]
    metrics: Dict[str, float]
    outputs: Dict[str, str]
    limitations: Dict[str, Any]


@dataclass
class ScoringSummary:
    schema: str
    created_at_utc: str
    data_version: str
    model_version: str
    scoring_run: str
    config_version: str
    seed: int
    inputs: Dict[str, Any]
    outputs: Dict[str, str]
    row_counts: Dict[str, int]
    status: str


@dataclass(frozen=True)
class TimeSplitBounds:
    train_max_key: str
    test_min_key: str
    train_max_year: int | None
    test_min_year: int | None


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
        raise FileNotFoundError(f"Canonical dataset not found: {csv}")
    return pd.read_csv(csv)


def _parse_date_series(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce")


def _season_from_month(m: int) -> str:
    if m in (12, 1, 2):
        return "winter"
    if m in (3, 4, 5):
        return "spring"
    if m in (6, 7, 8):
        return "summer"
    return "autumn"


def _load_productivity_explainability_cfg() -> Dict[str, Any]:
    cfg_path = Path("configs/ml_explainability.yaml")
    if not cfg_path.exists():
        return {}
    try:
        return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _load_qc_status(artifacts_root: Path, data_version: str, qc_run: str) -> Dict[str, Any]:
    qc_summary = artifacts_root / data_version / "qc" / qc_run / "qc_summary.json"
    if not qc_summary.exists():
        raise FileNotFoundError(f"qc_summary.json not found: {qc_summary}")
    return json.loads(qc_summary.read_text(encoding="utf-8"))


def _productivity_cfg(cfg_ref: MlConfigRef) -> dict[str, Any]:
    payload = cfg_ref.payload if isinstance(cfg_ref.payload, dict) else {}
    section = payload.get("productivity_model") if isinstance(payload.get("productivity_model"), dict) else {}
    return dict(section or {})


def _feature_lists(cfg_ref: MlConfigRef, *, age_at_calving_available: bool) -> tuple[list[str], list[str]]:
    cfg = _productivity_cfg(cfg_ref)
    features = cfg.get("features") if isinstance(cfg.get("features"), dict) else {}
    numeric = list(features.get("numeric_base") or ["parity", "calving_year", "calving_quarter"])
    categorical = list(features.get("categorical_base") or ["calving_season"])
    optional_numeric = list(features.get("optional_numeric_if_available") or ["age_at_calving"])
    if age_at_calving_available:
        for name in optional_numeric:
            if name not in numeric:
                numeric.append(name)
    return numeric, categorical


def _target_name(cfg_ref: MlConfigRef) -> str:
    cfg = _productivity_cfg(cfg_ref)
    return str(cfg.get("target") or "milk_305d_kg")


def _seed_value(cfg_ref: MlConfigRef) -> int:
    cfg = _productivity_cfg(cfg_ref)
    try:
        return int(cfg.get("seed", 42))
    except Exception:
        return 42


def _min_group_size(cfg_ref: MlConfigRef, explicit: int | None = None) -> int:
    if explicit is not None:
        return int(explicit)
    cfg = _productivity_cfg(cfg_ref)
    scoring = cfg.get("scoring") if isinstance(cfg.get("scoring"), dict) else {}
    try:
        return int(scoring.get("min_group_size", 10))
    except Exception:
        return 10


def build_productivity_feature_frame(
    *,
    artifacts_root: Path,
    data_version: str,
    cfg_ref: MlConfigRef,
) -> Tuple[pd.DataFrame, pd.Series, Dict[str, Any]]:
    base = artifacts_root / data_version
    canonical_dir = base / "canonical"

    target_col = _target_name(cfg_ref)
    lact = _read_canonical_table(canonical_dir, "dm_lactations")
    animals: Optional[pd.DataFrame] = None
    animals_path_csv = canonical_dir / "dm_animals.csv"
    animals_path_pqt = canonical_dir / "dm_animals.parquet"
    if animals_path_csv.exists() or animals_path_pqt.exists():
        animals = _read_canonical_table(canonical_dir, "dm_animals")

    lact["calving_date_dt"] = _parse_date_series(lact.get("calving_date"))
    if animals is not None and "birth_date" in animals.columns:
        animals["birth_date_dt"] = _parse_date_series(animals.get("birth_date"))
    elif animals is not None:
        animals["birth_date_dt"] = pd.NaT

    y = pd.to_numeric(lact.get(target_col), errors="coerce")
    lactation_no = pd.to_numeric(lact.get("lactation_no"), errors="coerce")
    calving_dt = lact["calving_date_dt"]

    X = pd.DataFrame(index=lact.index)
    X["parity"] = lactation_no
    X["calving_year"] = calving_dt.dt.year
    X["calving_quarter"] = calving_dt.dt.quarter
    X["calving_season"] = calving_dt.dt.month.map(lambda m: _season_from_month(int(m)) if pd.notna(m) else pd.NA)

    limitations: Dict[str, Any] = {
        "age_at_calving_available": False,
        "age_at_calving_reason": None,
    }

    if animals is not None and "animal_id" in lact.columns and "animal_id" in animals.columns and "birth_date_dt" in animals.columns:
        tmp = lact[["animal_id", "calving_date_dt"]].merge(
            animals[["animal_id", "birth_date_dt"]],
            on="animal_id",
            how="left",
        )
        age_days = (tmp["calving_date_dt"] - tmp["birth_date_dt"]).dt.days
        age_years = age_days / 365.25
        if age_years.notna().sum() > 0:
            X["age_at_calving"] = age_years
            limitations["age_at_calving_available"] = True
        else:
            X["age_at_calving"] = pd.NA
            limitations["age_at_calving_available"] = False
            limitations["age_at_calving_reason"] = "birth_date missing or unparsable for all joined rows"
    else:
        X["age_at_calving"] = pd.NA
        limitations["age_at_calving_available"] = False
        limitations["age_at_calving_reason"] = "dm_animals.birth_date not available in canonical layer"

    ok = y.notna()
    X = X.loc[ok].copy()
    y = y.loc[ok].copy()

    ok2 = X["calving_year"].notna() & X["calving_quarter"].notna()
    X = X.loc[ok2]
    y = y.loc[ok2]

    if "animal_id" in lact.columns and "lactation_no" in lact.columns:
        idx_all = lact.loc[ok].loc[ok2].index
        row_id = lact.loc[idx_all, "animal_id"].astype("string") + "|" + lact.loc[idx_all, "lactation_no"].astype("string")
        X["_row_id"] = row_id.values
    else:
        X["_row_id"] = X.index.astype("int64").astype("string")

    return X, y, limitations


def build_time_split_bounds(X: pd.DataFrame, train_idx: pd.Index, test_idx: pd.Index) -> TimeSplitBounds:
    ordered = X[["calving_year", "calving_quarter"]].copy()
    ordered["calving_year"] = pd.to_numeric(ordered["calving_year"], errors="coerce")
    ordered["calving_quarter"] = pd.to_numeric(ordered["calving_quarter"], errors="coerce")

    def _key(df: pd.DataFrame, agg: str) -> str:
        if df.empty:
            return "NA"
        years = df["calving_year"].fillna(-1).astype(int)
        quarters = df["calving_quarter"].fillna(-1).astype(int)
        seq = years.astype(str).str.zfill(4) + "Q" + quarters.astype(str)
        return str(seq.max() if agg == "max" else seq.min())

    train_frame = ordered.loc[train_idx]
    test_frame = ordered.loc[test_idx]
    train_year = None if train_frame.empty else int(pd.to_numeric(train_frame["calving_year"], errors="coerce").max())
    test_year = None if test_frame.empty else int(pd.to_numeric(test_frame["calving_year"], errors="coerce").min())
    return TimeSplitBounds(
        train_max_key=_key(train_frame, "max"),
        test_min_key=_key(test_frame, "min"),
        train_max_year=train_year,
        test_min_year=test_year,
    )


def split_feature_frame_time_aware(X: pd.DataFrame, y: pd.Series, cfg_ref: MlConfigRef) -> Tuple[pd.Index, pd.Index, Dict[str, Any]]:
    calving_year = pd.to_numeric(X["calving_year"], errors="coerce")
    years = sorted([int(v) for v in calving_year.dropna().unique().tolist()])
    split_cfg = _productivity_cfg(cfg_ref).get("split") if isinstance(_productivity_cfg(cfg_ref).get("split"), dict) else {}
    year_holdout_cfg = split_cfg.get("year_holdout") if isinstance(split_cfg.get("year_holdout"), dict) else {}
    min_train_rows = int(year_holdout_cfg.get("min_train_rows", 20))
    min_test_rows = int(year_holdout_cfg.get("min_test_rows", 10))
    train_fraction = float(split_cfg.get("fallback_train_fraction", 0.8)) if split_cfg else 0.8

    if len(X) < 2:
        raise ValueError("Not enough labeled rows for time split (need at least 2)")

    if len(years) >= 2:
        test_year = max(years)
        train_mask = calving_year < test_year
        test_mask = calving_year == test_year
        if int(train_mask.sum()) >= min_train_rows and int(test_mask.sum()) >= min_test_rows:
            train_idx = X.index[train_mask]
            test_idx = X.index[test_mask]
            bounds = build_time_split_bounds(X, train_idx, test_idx)
            return train_idx, test_idx, {
                "strategy": "year_holdout",
                "train_years": years[:-1],
                "test_year": test_year,
                "bounds": asdict(bounds),
            }

    df_ord = X[["calving_year", "calving_quarter"]].copy()
    df_ord["calving_year"] = pd.to_numeric(df_ord["calving_year"], errors="coerce")
    df_ord["calving_quarter"] = pd.to_numeric(df_ord["calving_quarter"], errors="coerce")
    df_ord = df_ord.sort_values(["calving_year", "calving_quarter"], ascending=[True, True])
    n = len(df_ord)
    cut = int(n * train_fraction)
    cut = min(max(cut, 1), n - 1)
    train_idx = df_ord.index[:cut]
    test_idx = df_ord.index[cut:]
    bounds = build_time_split_bounds(X, train_idx, test_idx)
    return train_idx, test_idx, {
        "strategy": "time_percentile",
        "train_fraction": train_fraction,
        "n_total": int(n),
        "bounds": asdict(bounds),
    }




def strip_split_bounds(split_meta: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(split_meta or {})
    out.pop("bounds", None)
    return out

def train_productivity_model(
    *,
    artifacts_root: Path,
    data_version: str,
    qc_run: str,
    model_version: Optional[str] = None,
    config_path: str | Path | None = None,
) -> Dict[str, Any]:
    artifacts_root = artifacts_root.resolve()
    cfg_ref = load_ml_pipeline_config(config_path)
    seed = _seed_value(cfg_ref)
    qc = _load_qc_status(artifacts_root, data_version, qc_run)
    qc_status = str(qc.get("qc_status", "UNKNOWN"))
    if qc_status == "ERROR":
        return {
            "ok": False,
            "reason": "QC_STATUS_ERROR",
            "qc_status": qc_status,
        }

    mv = model_version or generate_run_id(prefix="model")
    base = artifacts_root / data_version
    model_dir = base / "models" / mv
    model_dir.mkdir(parents=True, exist_ok=True)

    X, y, limitations = build_productivity_feature_frame(
        artifacts_root=artifacts_root,
        data_version=data_version,
        cfg_ref=cfg_ref,
    )
    train_idx, test_idx, split_meta = split_feature_frame_time_aware(X, y, cfg_ref)

    row_id = X["_row_id"].astype("string")
    X_model = X.drop(columns=["_row_id"])

    from joblib import dump
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.metrics import mean_absolute_error, mean_squared_error
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder

    numeric, categorical = _feature_lists(cfg_ref, age_at_calving_available=bool(limitations.get("age_at_calving_available")))

    pre = ColumnTransformer(
        transformers=[
            (
                "num",
                Pipeline(steps=[("imputer", SimpleImputer(strategy="median"))]),
                numeric,
            ),
            (
                "cat",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("ohe", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                categorical,
            ),
        ],
        remainder="drop",
    )

    model = GradientBoostingRegressor(random_state=seed)
    pipe = Pipeline(steps=[("pre", pre), ("model", model)])

    X_train = X_model.loc[train_idx]
    y_train = y.loc[train_idx]
    X_test = X_model.loc[test_idx]
    y_test = y.loc[test_idx]

    pipe.fit(X_train, y_train)
    pred = pipe.predict(X_test)

    mae = float(mean_absolute_error(y_test, pred))
    rmse = float(sqrt(mean_squared_error(y_test, pred)))

    model_path = model_dir / "model.joblib"
    dump(pipe, model_path)

    metrics = {
        "mae": mae,
        "rmse": rmse,
        "n_train": int(len(X_train)),
        "n_test": int(len(X_test)),
    }

    explain_cfg = _load_productivity_explainability_cfg()
    explain_section = explain_cfg.get("productivity_explainability") if isinstance(explain_cfg, dict) else {}
    explain_profile_path = model_dir / "explainability_profile.json"
    importance_by_feature = aggregate_native_feature_importances(pipe, numeric + categorical)
    if not any(float(v or 0.0) > 0 for v in importance_by_feature.values()):
        y_train_numeric = pd.to_numeric(y_train, errors="coerce")
        for f in numeric:
            try:
                corr = safe_abs_correlation(pd.to_numeric(X_train[f], errors="coerce"), y_train_numeric)
            except Exception:
                corr = 0.0
            importance_by_feature[f] = corr
    if not any(float(v or 0.0) > 0 for v in importance_by_feature.values()):
        fallback_order = list(numeric) + list(categorical)
        for idx, f in enumerate(fallback_order, start=1):
            importance_by_feature[f] = float(max(1, len(fallback_order) - idx + 1))
    baseline_median = {str(k): float(v) for k, v in X_train[numeric].median(numeric_only=True).to_dict().items() if pd.notna(v)}
    baseline_scale_raw = X_train[numeric].std(numeric_only=True).replace(0, pd.NA).fillna(1.0).to_dict()
    baseline_scale = {str(k): float(v) for k, v in baseline_scale_raw.items() if pd.notna(v)}
    feature_rules = infer_prediction_rules_from_sensitivity(
        pipe=pipe,
        numeric_features=numeric,
        baseline_median=baseline_median,
        baseline_scale=baseline_scale,
        abs_step_default=float((explain_section.get("counterfactual") or {}).get("abs_step_default", 1.0)),
    )
    for cat in categorical:
        feature_rules.setdefault(cat, "neutral")
    save_explainability_profile(
        model_dir=model_dir,
        features=list(numeric) + list(categorical),
        feature_importances=[float(importance_by_feature.get(f, 0.0)) for f in list(numeric) + list(categorical)],
        baseline_median=baseline_median,
        baseline_scale=baseline_scale,
        feature_rules=feature_rules,
        top_k=int(explain_section.get("top_k", 3)),
        task_kind="regression",
    )

    pred_df = pd.DataFrame(
        {
            "row_id": row_id.loc[test_idx].values,
            "y_true": y_test.values,
            "y_pred": pred,
        }
    )
    pred_path = model_dir / "test_predictions.csv"
    pred_df.to_csv(pred_path, index=False, encoding="utf-8")

    created_at = _utc_now_iso()
    card = {
        "schema": "genomeai.model_card.v1",
        "created_at_utc": created_at,
        "run_id": mv,
        "data_version": data_version,
        "qc_run": qc_run,
        "qc_status": qc_status,
        "model_version": mv,
        "config_version": cfg_ref.config_version,
        "config_sha256": cfg_ref.sha256,
        "seed": seed,
        "task": str(_productivity_cfg(cfg_ref).get("task") or "baseline_regression"),
        "target": _target_name(cfg_ref),
        "features": {
            "numeric": numeric,
            "categorical": categorical,
        },
        "split": strip_split_bounds(split_meta),
        "metrics": metrics,
        "limitations": limitations,
    }
    write_json(model_dir / "model_card.json", card)

    md_lines = [
        f"# Model Card: {mv}",
        "",
        f"- **data_version:** {data_version}",
        f"- **qc_run:** {qc_run} (status: {qc_status})",
        f"- **trained_at_utc:** {created_at}",
        f"- **config_version:** {cfg_ref.config_version}",
        f"- **seed:** {seed}",
        "",
        "## Task",
        "Baseline regression: predict 305-day milk yield (kg) from simple calving/lactation features.",
        "",
        "## Features",
        f"- Numeric: {', '.join(numeric)}",
        f"- Categorical: {', '.join(categorical)}",
        "",
        "## Validation (no leakage)",
        f"Split strategy: `{split_meta.get('strategy')}`. See `docs/ml_validation.md`.",
        f"Split bounds: train_max={split_meta.get('bounds', {}).get('train_max_key')}, test_min={split_meta.get('bounds', {}).get('test_min_key')}",
        "",
        "## Metrics",
        f"- MAE: {mae:.3f}",
        f"- RMSE: {rmse:.3f}",
        f"- n_train: {len(X_train)}",
        f"- n_test: {len(X_test)}",
        "",
        "## Limitations",
        f"- age_at_calving used: {bool(limitations.get('age_at_calving_available'))}",
    ]
    if limitations.get("age_at_calving_reason"):
        md_lines.append(f"- age_at_calving note: {limitations['age_at_calving_reason']}")
    (model_dir / "model_card.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    summary = TrainSummary(
        schema="genomeai.train_summary.v1",
        created_at_utc=created_at,
        data_version=data_version,
        qc_run=qc_run,
        qc_status=qc_status,
        model_version=mv,
        config_version=cfg_ref.config_version,
        seed=seed,
        target=_target_name(cfg_ref),
        features={"numeric": numeric, "categorical": categorical},
        split=strip_split_bounds(split_meta),
        metrics={"mae": mae, "rmse": rmse},
        outputs={
            "model_path": str(model_path.resolve()),
            "model_card_md": str((model_dir / "model_card.md").resolve()),
            "model_card_json": str((model_dir / "model_card.json").resolve()),
            "test_predictions_csv": str(pred_path.resolve()),
            "explainability_profile_json": str(explain_profile_path.resolve()),
        },
        limitations=limitations,
    )

    write_json(model_dir / "train_summary.json", asdict(summary))
    meta_dir = base / "metadata"
    meta_dir.mkdir(parents=True, exist_ok=True)
    write_json(meta_dir / f"train_{mv}.json", asdict(summary))

    manifest_path = register_model_manifest(
        artifacts_root=artifacts_root,
        data_version=data_version,
        model_version=mv,
        entry={
            "created_at_utc": summary.created_at_utc,
            "qc_run": qc_run,
            "qc_status": qc_status,
            "config_version": cfg_ref.config_version,
            "seed": seed,
            "features": {"numeric": numeric, "categorical": categorical},
            "metrics": metrics,
            "train_summary": str((model_dir / "train_summary.json").resolve()),
            "model_card": str((model_dir / "model_card.json").resolve()),
            "model_path": str(model_path.resolve()),
        },
    )

    run_root = get_run_root(artifacts_root=artifacts_root, data_version=data_version, run_id=mv)
    copy_tree_into_run(src_dir=model_dir, run_root=run_root, subdir="model")
    manifest2 = {
        "schema": "genomeai.run_manifest.v1",
        "step": "train",
        "data_version": data_version,
        "run_id": mv,
        "created_at": summary.created_at_utc,
        "status": "DONE",
        "outputs": {
            "legacy_dir": str(model_dir),
            "run_dir": str(run_root / "model"),
            "model_path": str(model_path),
            "train_summary": str(model_dir / "train_summary.json"),
            "model_manifest": str(manifest_path),
        },
        "lineage": {
            "qc_run": qc_run,
            "qc_status": qc_status,
            "canonical_dir": str(base / "canonical"),
            "config_version": cfg_ref.config_version,
        },
        "metrics": metrics,
        "split": strip_split_bounds(split_meta),
    }
    write_run_manifest(run_root=run_root, manifest=manifest2)
    write_checksums(run_root=run_root, include_subdirs=["model"])
    write_best_effort_ml_audit(
        action="pipeline.train",
        object_type="model",
        object_id=mv,
        data_version=data_version,
        run_id=mv,
        after={
            "qc_run": qc_run,
            "config_version": cfg_ref.config_version,
            "seed": seed,
            "metrics": metrics,
        },
    )

    return {
        "ok": True,
        "data_version": data_version,
        "qc_run": qc_run,
        "qc_status": qc_status,
        "model_version": mv,
        "config_version": cfg_ref.config_version,
        "seed": seed,
        "model_dir": str(model_dir.resolve()),
        "run_dir": str(run_root.resolve()),
        "metrics": metrics,
        "split": strip_split_bounds(split_meta),
        "outputs": summary.outputs,
    }


def _find_model_dir(artifacts_root: Path, model_version: str) -> Path:
    artifacts_root = artifacts_root.resolve()
    candidates = list(artifacts_root.glob(f"*/models/{model_version}"))
    if not candidates:
        candidates = list(artifacts_root.glob(f"**/models/{model_version}"))
    if not candidates:
        raise FileNotFoundError(f"model_version not found under {artifacts_root}: {model_version}")
    candidates = sorted(candidates, key=lambda p: len(str(p)))
    return candidates[0]


def _load_model(artifacts_root: Path, model_version: str) -> Tuple[Any, Dict[str, Any], Path]:
    model_dir = _find_model_dir(artifacts_root, model_version)
    model_path = model_dir / "model.joblib"
    card_path = model_dir / "model_card.json"
    if not model_path.exists():
        raise FileNotFoundError(str(model_path))
    if not card_path.exists():
        raise FileNotFoundError(str(card_path))

    from joblib import load

    model = load(model_path)
    card = json.loads(card_path.read_text(encoding="utf-8"))
    return model, card, model_dir


def _latest_per_animal(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["_calving_dt"] = _parse_date_series(out.get("calving_date", pd.Series([pd.NA] * len(out))))
    out["_lact_no"] = pd.to_numeric(out.get("lactation_no", pd.Series([pd.NA] * len(out))), errors="coerce")
    out["_has_date"] = out["_calving_dt"].notna()
    out = out.sort_values(["animal_id", "_has_date", "_calving_dt", "_lact_no"], ascending=[True, False, False, False])
    out = out.drop_duplicates(subset=["animal_id"], keep="first")
    return out.drop(columns=["_calving_dt", "_lact_no", "_has_date"], errors="ignore")


def _safe_zscore(x: pd.Series) -> pd.Series:
    mu = x.mean(skipna=True)
    sd = x.std(skipna=True)
    if sd is None or pd.isna(sd) or float(sd) == 0.0:
        return pd.Series([0.0] * len(x), index=x.index)
    return (x - mu) / sd


def _build_action_and_reasons(row: pd.Series) -> Tuple[str, str]:
    reasons: List[str] = []
    if bool(row.get("flag_missing_keys", False)):
        reasons.append("missing_group_key")
    if bool(row.get("flag_small_group", False)):
        reasons.append("small_group")
    if bool(row.get("flag_missing_features", False)):
        reasons.append("missing_features")
    if bool(row.get("flag_outlier", False)):
        reasons.append("outlier")

    conf = str(row.get("confidence", "LOW"))
    pred = row.get("y_pred")
    resid = row.get("residual")
    parity = row.get("parity")
    action = "OBSERVE"

    if conf == "LOW":
        reasons.append("low_confidence")
        return action, ";".join(sorted(set(reasons)))

    if pd.notna(resid):
        try:
            r = float(resid)
        except Exception:
            r = 0.0
        p = float(parity) if pd.notna(parity) else 1.0
        if r >= 500:
            action = "PRIORITY"
            reasons.append("high_positive_residual")
        elif r <= -800 and p >= 2:
            action = "CULL_CANDIDATE"
            reasons.append("low_negative_residual")
    else:
        if pd.notna(pred):
            reasons.append("no_actual_y")
            pr = row.get("rank_pct_in_farm")
            if pd.notna(pr):
                try:
                    prf = float(pr)
                except Exception:
                    prf = 0.5
                if prf <= 0.2:
                    action = "PRIORITY"
                    reasons.append("top_pred_in_farm")
                elif prf >= 0.8:
                    action = "OBSERVE"
                    reasons.append("low_pred_in_farm")
    return action, ";".join(sorted(set(reasons)))


def run_scoring(
    *,
    artifacts_root: Path,
    data_version: str,
    model_version: str,
    scoring_run: Optional[str] = None,
    min_group_size: int | None = None,
    config_path: str | Path | None = None,
) -> Dict[str, Any]:
    artifacts_root = artifacts_root.resolve()
    cfg_ref = load_ml_pipeline_config(config_path)
    effective_group_size = _min_group_size(cfg_ref, min_group_size)

    model, card, model_dir = _load_model(artifacts_root, model_version)
    expected_numeric = list(card.get("features", {}).get("numeric", []))
    expected_cat = list(card.get("features", {}).get("categorical", []))
    seed = int(card.get("seed") or _seed_value(cfg_ref))

    base = artifacts_root / data_version
    canonical_dir = base / "canonical"
    lact = _read_canonical_table(canonical_dir, "dm_lactations")
    animals = _read_canonical_table(canonical_dir, "dm_animals")

    lact = lact.copy()
    lact["calving_date_dt"] = _parse_date_series(lact.get("calving_date"))
    lact["lactation_no_num"] = pd.to_numeric(lact.get("lactation_no"), errors="coerce")
    lact["milk_305d_kg_num"] = pd.to_numeric(lact.get("milk_305d_kg"), errors="coerce")

    animals = animals.copy()
    if "birth_date" in animals.columns:
        animals["birth_date_dt"] = _parse_date_series(animals.get("birth_date"))
    else:
        animals["birth_date_dt"] = pd.NaT

    if "animal_id" not in lact.columns or "animal_id" not in animals.columns:
        raise ValueError("animal_id must exist in dm_lactations and dm_animals")

    joined = lact.merge(
        animals[[c for c in ["animal_id", "farm_id", "ear_tag", "birth_date_dt"] if c in animals.columns]],
        on="animal_id",
        how="left",
    )

    X = pd.DataFrame(index=joined.index)
    X["parity"] = joined["lactation_no_num"]
    X["calving_year"] = joined["calving_date_dt"].dt.year
    X["calving_quarter"] = joined["calving_date_dt"].dt.quarter
    X["calving_season"] = joined["calving_date_dt"].dt.month.map(lambda m: _season_from_month(int(m)) if pd.notna(m) else pd.NA)
    X["age_at_calving"] = (joined["calving_date_dt"] - joined["birth_date_dt"]).dt.days / 365.25

    feature_cols: List[str] = []
    for c in expected_numeric + expected_cat:
        if c not in X.columns:
            X[c] = pd.NA
        feature_cols.append(c)
    X_model = X[feature_cols].copy()

    y_pred = model.predict(X_model)

    scored = joined.copy()
    scored["y_pred"] = y_pred
    scored["y_true"] = scored["milk_305d_kg_num"]
    scored["residual"] = scored["y_true"] - scored["y_pred"]
    scored["row_id"] = scored["animal_id"].astype("string") + "|" + scored["lactation_no"].astype("string")
    scored["parity"] = scored["lactation_no_num"]
    scored["calving_year"] = scored["calving_date_dt"].dt.year
    scored["calving_season"] = scored["calving_date_dt"].dt.month.map(lambda m: _season_from_month(int(m)) if pd.notna(m) else pd.NA)

    latest = _latest_per_animal(scored)
    latest["flag_missing_keys"] = latest[["farm_id", "calving_year", "calving_season", "parity"]].isna().any(axis=1)
    latest["flag_missing_features"] = latest[["lactation_no_num", "calving_date_dt", "farm_id"]].isna().any(axis=1)

    resid_sd = latest["residual"].std(skipna=True)
    latest["flag_outlier"] = False
    if resid_sd is not None and pd.notna(resid_sd) and float(resid_sd) > 0:
        latest.loc[latest["residual"].abs() > (3.0 * float(resid_sd)), "flag_outlier"] = True
    latest.loc[(latest["milk_305d_kg_num"].notna()) & ((latest["milk_305d_kg_num"] < 2000) | (latest["milk_305d_kg_num"] > 20000)), "flag_outlier"] = True

    gcols = ["farm_id", "calving_year", "calving_season", "parity"]
    grp = latest.groupby(gcols, dropna=False)
    latest["group_size"] = grp["row_id"].transform("count")
    latest["flag_small_group"] = latest["group_size"] < int(effective_group_size)

    use_resid = latest["residual"].notna()
    score_for_rank = latest["residual"].where(use_resid, latest["y_pred"])
    latest["score_for_rank"] = score_for_rank
    latest["index_in_group"] = grp["score_for_rank"].transform(_safe_zscore)
    latest["rank_in_group"] = grp["score_for_rank"].rank(method="dense", ascending=False).astype("Int64")
    latest["rank_in_farm"] = latest.groupby("farm_id", dropna=False)["score_for_rank"].rank(method="dense", ascending=False).astype("Int64")

    farm_grp = latest.groupby("farm_id", dropna=False)["score_for_rank"]
    latest["rank_pct_in_farm"] = (farm_grp.rank(method="average", ascending=True) - 1) / (farm_grp.transform("count") - 1)
    latest["rank_pct_in_farm"] = latest["rank_pct_in_farm"].fillna(0.5)

    flag_cols = ["flag_missing_keys", "flag_small_group", "flag_missing_features", "flag_outlier"]
    latest["flag_count"] = latest[flag_cols].sum(axis=1).astype(int)
    latest["confidence"] = pd.cut(latest["flag_count"], bins=[-1, 0, 1, 99], labels=["HIGH", "MEDIUM", "LOW"]).astype("string")

    actions = latest.apply(lambda r: _build_action_and_reasons(r), axis=1, result_type="expand")
    latest["action"] = actions[0]
    latest["action_reasons"] = actions[1]

    group_summary = (
        latest.groupby(gcols, dropna=False)
        .agg(
            n_animals=("animal_id", "count"),
            mean_pred=("y_pred", "mean"),
            mean_residual=("residual", "mean"),
            std_residual=("residual", "std"),
            share_low_conf=("confidence", lambda s: float((s == "LOW").mean())),
        )
        .reset_index()
    )

    sr = scoring_run or generate_run_id(prefix="score")
    out_dir = base / "scoring" / sr
    exports_dir = out_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    animal_ranking_xlsx = exports_dir / "animal_ranking.xlsx"
    group_summary_xlsx = exports_dir / "group_summary.xlsx"
    recommendations_xlsx = exports_dir / "recommendations.xlsx"

    explain_cfg = _load_productivity_explainability_cfg()
    explain_profile = load_explainability_profile(model_dir)
    explanation_rows: List[Dict[str, Any]] = []
    latest["explain_top_factors_json"] = "[]"
    latest["explain_top_factors_text"] = "insufficient_explainability_data"
    latest["explain_counterfactuals_json"] = "[]"
    latest["explain_counterfactuals_text"] = "no_simple_counterfactual"
    if explain_profile and not X_model.empty:
        explain_input = X_model.loc[latest.index].copy()
        for idx in latest.index.tolist():
            try:
                exp = explain_regression_row(row=latest.loc[idx], score_df=explain_input, pipe=model, profile=explain_profile, cfg=explain_cfg)
                latest.loc[idx, "explain_top_factors_json"] = json.dumps(exp.get("top_factors") or [], ensure_ascii=False)
                latest.loc[idx, "explain_top_factors_text"] = str(exp.get("top_factors_text") or "")
                latest.loc[idx, "explain_counterfactuals_json"] = json.dumps(exp.get("counterfactuals") or [], ensure_ascii=False)
                latest.loc[idx, "explain_counterfactuals_text"] = str(exp.get("counterfactuals_text") or "")
                explanation_rows.append(
                    {
                        "row_id": str(latest.loc[idx, "row_id"]),
                        "farm_id": str(latest.loc[idx, "farm_id"]),
                        "animal_id": str(latest.loc[idx, "animal_id"]),
                        "calving_date": str(latest.loc[idx, "calving_date"]),
                        "prediction": float(latest.loc[idx, "y_pred"]),
                        "top_factors_json": latest.loc[idx, "explain_top_factors_json"],
                        "top_factors_text": latest.loc[idx, "explain_top_factors_text"],
                        "counterfactuals_json": latest.loc[idx, "explain_counterfactuals_json"],
                        "counterfactuals_text": latest.loc[idx, "explain_counterfactuals_text"],
                    }
                )
            except Exception:
                continue

    export_cols = [
        "farm_id",
        "animal_id",
        "ear_tag",
        "lactation_no",
        "calving_date",
        "milk_305d_kg",
        "y_pred",
        "residual",
        "index_in_group",
        "rank_in_group",
        "rank_in_farm",
        "group_size",
        "confidence",
        "flag_small_group",
        "flag_outlier",
        "flag_missing_features",
        "flag_missing_keys",
        "action",
        "action_reasons",
        "explain_top_factors_text",
        "explain_counterfactuals_text",
        "row_id",
    ]
    export_cols = [c for c in export_cols if c in latest.columns]
    latest_export = latest[export_cols].copy()

    with pd.ExcelWriter(animal_ranking_xlsx, engine="openpyxl") as xw:
        latest_export.to_excel(xw, index=False, sheet_name="animals_latest")
    with pd.ExcelWriter(group_summary_xlsx, engine="openpyxl") as xw:
        group_summary.to_excel(xw, index=False, sheet_name="groups")

    def _rec_sheet(df: pd.DataFrame) -> pd.DataFrame:
        cols = [c for c in ["farm_id", "animal_id", "ear_tag", "calving_date", "lactation_no", "y_pred", "residual", "confidence", "action_reasons", "explain_top_factors_text", "explain_counterfactuals_text"] if c in df.columns]
        return df[cols].sort_values(["farm_id", "y_pred"], ascending=[True, False])

    priority = latest[latest["action"] == "PRIORITY"].copy()
    observe = latest[latest["action"] == "OBSERVE"].copy()
    cull = latest[latest["action"] == "CULL_CANDIDATE"].copy()

    with pd.ExcelWriter(recommendations_xlsx, engine="openpyxl") as xw:
        _rec_sheet(priority).to_excel(xw, index=False, sheet_name="priority")
        _rec_sheet(observe).to_excel(xw, index=False, sheet_name="observe")
        _rec_sheet(cull).to_excel(xw, index=False, sheet_name="cull_candidates")

    latest_export.to_csv(out_dir / "scored_latest.csv", index=False, encoding="utf-8")
    group_summary.to_csv(out_dir / "group_summary.csv", index=False, encoding="utf-8")
    explanations_csv = out_dir / "productivity_explanations.csv"
    pd.DataFrame(explanation_rows or []).to_csv(explanations_csv, index=False, encoding="utf-8")

    canonical_hash = compute_data_version(canonical_dir, include_globs=["*.csv", "*.parquet"])
    summary = ScoringSummary(
        schema="genomeai.scoring_summary.v1",
        created_at_utc=_utc_now_iso(),
        data_version=data_version,
        model_version=model_version,
        scoring_run=sr,
        config_version=str(card.get("config_version") or cfg_ref.config_version),
        seed=seed,
        inputs={
            "canonical_dir": str(canonical_dir.resolve()),
            "canonical_hash": canonical_hash,
            "model_dir": str(model_dir.resolve()),
            "model_card": str((model_dir / "model_card.json").resolve()),
            "features": {"numeric": expected_numeric, "categorical": expected_cat},
        },
        outputs={
            "animal_ranking_xlsx": str(animal_ranking_xlsx.resolve()),
            "group_summary_xlsx": str(group_summary_xlsx.resolve()),
            "recommendations_xlsx": str(recommendations_xlsx.resolve()),
            "scored_latest_csv": str((out_dir / "scored_latest.csv").resolve()),
            "explanations_csv": str(explanations_csv.resolve()),
        },
        row_counts={
            "n_lactations": int(len(scored)),
            "n_animals_ranked": int(len(latest)),
            "n_priority": int(len(priority)),
            "n_observe": int(len(observe)),
            "n_cull_candidates": int(len(cull)),
        },
        status="OK",
    )
    write_json(out_dir / "scoring_summary.json", asdict(summary))
    meta_dir = base / "metadata"
    meta_dir.mkdir(parents=True, exist_ok=True)
    write_json(meta_dir / f"score_{sr}.json", asdict(summary))

    scoring_manifest_path = register_scoring_manifest(
        artifacts_root=artifacts_root,
        data_version=data_version,
        scoring_run=sr,
        entry={
            "created_at_utc": summary.created_at_utc,
            "model_version": model_version,
            "config_version": summary.config_version,
            "seed": seed,
            "row_counts": summary.row_counts,
            "scoring_summary": str((out_dir / "scoring_summary.json").resolve()),
            "scored_latest_csv": str((out_dir / "scored_latest.csv").resolve()),
            "recommendations_xlsx": str(recommendations_xlsx.resolve()),
        },
    )

    run_root = get_run_root(artifacts_root=artifacts_root, data_version=data_version, run_id=sr)
    copy_tree_into_run(src_dir=out_dir, run_root=run_root, subdir="scoring")
    manifest2 = {
        "schema": "genomeai.run_manifest.v1",
        "step": "score",
        "data_version": data_version,
        "run_id": sr,
        "created_at": summary.created_at_utc,
        "status": "DONE",
        "outputs": {
            "legacy_dir": str(out_dir),
            "run_dir": str(run_root / "scoring"),
            "animal_ranking_xlsx": str(exports_dir / "animal_ranking.xlsx"),
            "group_summary_xlsx": str(exports_dir / "group_summary.xlsx"),
            "recommendations_xlsx": str(exports_dir / "recommendations.xlsx"),
            "explanations_csv": str(out_dir / "productivity_explanations.csv"),
            "scoring_manifest": str(scoring_manifest_path),
        },
        "lineage": {
            "model_version": model_version,
            "canonical_dir": str(base / "canonical"),
            "config_version": summary.config_version,
        },
    }
    write_run_manifest(run_root=run_root, manifest=manifest2)
    write_checksums(run_root=run_root, include_subdirs=["scoring"])
    write_best_effort_ml_audit(
        action="pipeline.score",
        object_type="scoring",
        object_id=sr,
        data_version=data_version,
        run_id=sr,
        after={
            "model_version": model_version,
            "config_version": summary.config_version,
            "seed": seed,
            "row_counts": summary.row_counts,
        },
    )

    return {
        "ok": True,
        "data_version": data_version,
        "model_version": model_version,
        "scoring_run": sr,
        "config_version": summary.config_version,
        "seed": seed,
        "outputs": summary.outputs,
        "row_counts": summary.row_counts,
        "scoring_dir": str(out_dir.resolve()),
    }


__all__ = [
    "MlConfigRef",
    "ScoringSummary",
    "TimeSplitBounds",
    "TrainSummary",
    "build_productivity_feature_frame",
    "build_time_split_bounds",
    "run_scoring",
    "split_feature_frame_time_aware",
    "train_productivity_model",
]
