from __future__ import annotations

"""Rule-based sensor anomaly detector (v1) for daily aggregates.

This module is **offline-core**.

Anomaly types (v1):
  1) data_dropout: sensor data missing for N consecutive days.
  2) outlier: robust z-score spike/drop relative to recent baseline.
  3) baseline_drift: sustained shift of recent mean relative to baseline.

Hysteresis/noise suppression (v1):
  - outlier requires 2-day confirmation OR an extreme single-day deviation.
  - drift requires sustained deviation on a 3-day moving average.
  - dropout triggers only when gap_days >= gap_min_days.

The detector works primarily on the `cow_day` mart produced by `marts_timeseries`.
If mart is unavailable, callers may pass a DataFrame derived from canonical sources.
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class DetectorConfig:
    # dropout
    gap_min_days: int = 2
    # baseline windows
    baseline_days: int = 21
    recent_days: int = 7
    # outlier
    outlier_z: float = 3.5
    outlier_z_extreme: float = 5.0
    confirm_days: int = 2
    # drift
    drift_confirm_days: int = 3
    drift_activity_pct: float = 0.25  # 25% drop/raise
    drift_rumination_pct: float = 0.20
    drift_temp_abs_c: float = 0.7


def _robust_z(x: float, median: float, mad: float) -> Optional[float]:
    if mad is None or not np.isfinite(mad) or mad <= 1e-9:
        return None
    return (x - median) / (1.4826 * mad)


def _median_mad(values: np.ndarray) -> Tuple[Optional[float], Optional[float]]:
    if values.size == 0:
        return None, None
    med = float(np.nanmedian(values))
    mad = float(np.nanmedian(np.abs(values - med)))
    if not np.isfinite(med):
        return None, None
    return med, mad


def _as_date(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce").dt.date


def find_latest_cow_day(artifacts_root: Path, data_version: str) -> Optional[Path]:
    """Return path to the latest cow_day.pkl for a data_version, if exists."""
    root = Path(artifacts_root) / data_version / "marts"
    if not root.exists():
        return None
    runs = sorted([p for p in root.iterdir() if p.is_dir()])
    if not runs:
        return None
    # pick latest by name (run_id includes timestamp prefix in this repo)
    for run in reversed(runs):
        p = run / "cow_day.pkl"
        if p.exists():
            return p
    return None


def load_cow_day(artifacts_root: Path, data_version: str) -> pd.DataFrame:
    p = find_latest_cow_day(artifacts_root, data_version)
    if not p:
        return pd.DataFrame()
    try:
        return pd.read_pickle(p)
    except Exception:
        return pd.DataFrame()


def detect_sensor_anomalies(
    cow_day: pd.DataFrame,
    *,
    cfg: DetectorConfig = DetectorConfig(),
) -> pd.DataFrame:
    """Detect anomalies and return a normalized anomaly table.

    Expected columns in cow_day (flexible):
      - farm_id, animal_id, date
      - is_observed_sensors (bool)
      - activity_steps, rumination_min, body_temp_c
    """
    if cow_day is None or cow_day.empty:
        return pd.DataFrame(
            columns=[
                "farm_id",
                "animal_id",
                "date",
                "metric",
                "anomaly_type",
                "severity",
                "score",
                "details_json",
            ]
        )

    df = cow_day.copy()
    if "date" not in df.columns or "animal_id" not in df.columns:
        return pd.DataFrame(
            columns=[
                "farm_id",
                "animal_id",
                "date",
                "metric",
                "anomaly_type",
                "severity",
                "score",
                "details_json",
            ]
        )

    if "farm_id" not in df.columns:
        df["farm_id"] = pd.NA
    df["date"] = _as_date(df["date"])
    df = df.dropna(subset=["animal_id", "date"], how="any")
    df = df.sort_values(["farm_id", "animal_id", "date"], kind="mergesort")

    # normalize observed flag
    if "is_observed_sensors" not in df.columns:
        # best-effort: observed if any sensor metric exists
        mcols = [c for c in ["activity_steps", "rumination_min", "body_temp_c"] if c in df.columns]
        if mcols:
            df["is_observed_sensors"] = df[mcols].notna().any(axis=1)
        else:
            df["is_observed_sensors"] = False

    for c in ["activity_steps", "rumination_min", "body_temp_c"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    anomalies: List[Dict[str, object]] = []

    metrics = {
        "activity_steps": {"kind": "drop", "pct_threshold": cfg.drift_activity_pct},
        "rumination_min": {"kind": "drop", "pct_threshold": cfg.drift_rumination_pct},
        "body_temp_c": {"kind": "spike", "abs_threshold": cfg.drift_temp_abs_c},
    }
    metrics = {k: v for k, v in metrics.items() if k in df.columns}

    for (farm_id, animal_id), g in df.groupby(["farm_id", "animal_id"], dropna=False):
        if g.empty:
            continue
        g = g.reset_index(drop=True)
        dates = g["date"].tolist()
        max_date = dates[-1]

        # 1) dropout (based on last observed)
        obs = g[g["is_observed_sensors"] == True]  # noqa: E712
        if not obs.empty:
            last_obs = obs["date"].iloc[-1]
            gap_days = (max_date - last_obs).days
            if gap_days >= cfg.gap_min_days:
                anomalies.append(
                    {
                        "farm_id": farm_id,
                        "animal_id": animal_id,
                        "date": max_date,
                        "metric": "sensors",
                        "anomaly_type": "data_dropout",
                        "severity": "LOW" if gap_days < 5 else "MEDIUM",
                        "score": float(gap_days),
                        "details_json": {
                            "last_observed_date": last_obs.isoformat(),
                            "gap_days": int(gap_days),
                            "max_date": max_date.isoformat(),
                        },
                    }
                )
        else:
            # never observed
            anomalies.append(
                {
                    "farm_id": farm_id,
                    "animal_id": animal_id,
                    "date": max_date,
                    "metric": "sensors",
                    "anomaly_type": "data_dropout",
                    "severity": "MEDIUM",
                    "score": float(len(g)),
                    "details_json": {"last_observed_date": None, "gap_days": None, "max_date": max_date.isoformat()},
                }
            )

        # 2) outliers (evaluate on the latest observed day)
        # choose last day with sensors present
        g_obs = g[g["is_observed_sensors"] == True]  # noqa: E712
        if len(g_obs) >= 8:
            cur_row = g_obs.iloc[-1]
            prev_row = g_obs.iloc[-2] if len(g_obs) >= 2 else None
            cur_date = cur_row["date"]
            for m, spec in metrics.items():
                if pd.isna(cur_row.get(m)):
                    continue

                # baseline: last N days excluding current
                base = g_obs.iloc[:-1].tail(14)
                vals = base[m].to_numpy(dtype=float)
                vals = vals[np.isfinite(vals)]
                if vals.size < 7:
                    continue

                med, mad = _median_mad(vals)
                if med is None or mad is None:
                    continue

                # If MAD is ~0 (perfectly stable baseline), robust z-score is undefined.
                # For body_temp_c we still want to catch obvious fever spikes using absolute delta.
                if (mad is not None) and (mad <= 1e-9) and m == "body_temp_c":
                    delta = float(cur_row[m]) - float(med)
                    prev_delta = None
                    if prev_row is not None and pd.notna(prev_row.get(m)):
                        prev_delta = float(prev_row[m]) - float(med)
                    # confirmation: 2-day confirmation OR extreme single-day delta
                    confirm_delta = (delta >= 1.5) or (delta >= 1.0 and (prev_delta is not None and prev_delta >= 1.0))
                    if confirm_delta:
                        anomalies.append(
                            {
                                "farm_id": farm_id,
                                "animal_id": animal_id,
                                "date": cur_row["date"],
                                "metric": m,
                                "anomaly_type": "temp_spike",
                                "severity": "HIGH" if delta >= 2.0 else "MEDIUM",
                                "score": float(delta),
                                "details_json": {
                                    "median": float(med),
                                    "mad": float(mad),
                                    "delta": float(delta),
                                    "value": float(cur_row[m]),
                                    "baseline_n": int(vals.size),
                                    "fallback_reason": "mad_zero",
                                },
                            }
                        )
                    continue

                z = _robust_z(float(cur_row[m]), med, mad)
                if z is None:
                    continue

                # confirmation / hysteresis: 2-day confirmation OR extreme
                confirm = False
                if abs(z) >= cfg.outlier_z_extreme:
                    confirm = True
                elif abs(z) >= cfg.outlier_z and prev_row is not None:
                    # prev also outlier?
                    pz = _robust_z(float(prev_row[m]), med, mad)
                    if pz is not None and abs(pz) >= cfg.outlier_z:
                        confirm = True

                if not confirm:
                    continue

                # map to anomaly type
                if m == "body_temp_c" and z >= cfg.outlier_z:
                    a_type = "temp_spike"
                    sev = "HIGH" if z >= 4.5 else "MEDIUM"
                elif m == "rumination_min" and z <= -cfg.outlier_z:
                    a_type = "rumination_drop"
                    sev = "MEDIUM"
                elif m == "activity_steps" and z <= -cfg.outlier_z:
                    a_type = "activity_drop"
                    sev = "LOW" if z > -4.5 else "MEDIUM"
                else:
                    a_type = "outlier"
                    sev = "MEDIUM"

                anomalies.append(
                    {
                        "farm_id": farm_id,
                        "animal_id": animal_id,
                        "date": cur_date,
                        "metric": m,
                        "anomaly_type": a_type,
                        "severity": sev,
                        "score": float(z),
                        "details_json": {
                            "median": float(med),
                            "mad": float(mad),
                            "z": float(z),
                            "value": float(cur_row[m]),
                            "baseline_n": int(vals.size),
                        },
                    }
                )

        # 3) baseline drift (sustained)
        if len(g_obs) >= (cfg.baseline_days + cfg.recent_days):
            for m, spec in metrics.items():
                series = g_obs[["date", m]].dropna()
                if len(series) < (cfg.baseline_days + cfg.recent_days):
                    continue
                # take last baseline_days+recent_days observations
                tail = series.tail(cfg.baseline_days + cfg.recent_days)
                base_part = tail.iloc[: cfg.baseline_days]
                recent_part = tail.iloc[cfg.baseline_days :]

                base_vals = base_part[m].to_numpy(dtype=float)
                recent_vals = recent_part[m].to_numpy(dtype=float)
                base_vals = base_vals[np.isfinite(base_vals)]
                recent_vals = recent_vals[np.isfinite(recent_vals)]
                if base_vals.size < 14 or recent_vals.size < 5:
                    continue

                base_mean = float(np.nanmean(base_vals))
                recent_mean = float(np.nanmean(recent_vals))
                if not np.isfinite(base_mean) or abs(base_mean) < 1e-9:
                    continue

                drift = False
                drift_score = 0.0
                if m == "body_temp_c":
                    delta = recent_mean - base_mean
                    if abs(delta) >= cfg.drift_temp_abs_c:
                        drift = True
                        drift_score = float(delta)
                else:
                    delta_pct = (recent_mean - base_mean) / base_mean
                    thr = float(spec.get("pct_threshold") or 0.2)
                    if abs(delta_pct) >= thr:
                        drift = True
                        drift_score = float(delta_pct)

                if not drift:
                    continue

                # hysteresis: confirm by 3-day moving average in the most recent tail
                last_k = series.tail(cfg.drift_confirm_days)
                if len(last_k) < cfg.drift_confirm_days:
                    continue
                last_k_mean = float(np.nanmean(last_k[m].to_numpy(dtype=float)))
                if m == "body_temp_c":
                    if abs(last_k_mean - base_mean) < cfg.drift_temp_abs_c:
                        continue
                else:
                    last_k_pct = (last_k_mean - base_mean) / base_mean
                    thr = float(spec.get("pct_threshold") or 0.2)
                    if abs(last_k_pct) < thr:
                        continue

                anomalies.append(
                    {
                        "farm_id": farm_id,
                        "animal_id": animal_id,
                        "date": series["date"].iloc[-1],
                        "metric": m,
                        "anomaly_type": "baseline_drift",
                        "severity": "MEDIUM",
                        "score": float(drift_score),
                        "details_json": {
                            "baseline_days": int(cfg.baseline_days),
                            "recent_days": int(cfg.recent_days),
                            "baseline_mean": float(base_mean),
                            "recent_mean": float(recent_mean),
                            "recent_tail_mean": float(last_k_mean),
                        },
                    }
                )

    out = pd.DataFrame(anomalies)
    if out.empty:
        return out
    # Ensure stable dtypes
    out["date"] = _as_date(out["date"])
    return out
