"""Generate synthetic sensor data for data/demo/investor_v1/.

180 days of daily readings (activity_count, rumination_min, lying_min, temperature_c)
for all 350 cows in dm_animals.csv.

Reference date: 2026-02-28 — exactly 10 days before Звёздочка's seeded mastitis event
(2026-03-10).  The detector evaluates the *last observed day*, so all three anomalies
are designed to appear at the tail of the 180-day window.

Window: 2025-08-31 → 2026-02-28.

Design for zero false positives
--------------------------------
The detector evaluates g_obs.iloc[-1] (last observed day) for outlier checks.
To guarantee no accidental z > 5.0 hit from random noise, the LAST OBSERVED DAY
of every animal is pinned to the exact baseline mean (μ) for each metric.
Days 1–179 carry realistic Gaussian noise; only the last observed day is clamped.

Seeded anomalies:
  4821 (Звёздочка): rum[last] overridden to 200 min (vs μ=500).
                    z ≈ –20 >> 5.0 → rumination_drop fired (no confirmation needed).
                    Recent-7-day mean ≈ 457 → Δ% ≈ –8.6 % < 20 % → no drift.

  3891 (Малина):    last 5 days all NaN (is_observed_sensors → False).
                    gap_days = 5 ≥ 2 → data_dropout fired.
                    Day before the gap (last observed) pinned to μ → no outlier.

  3142 (Ночка):     tmp[last 3] = 39.5 °C (vs μ=38.5).
                    z ≈ 22 >> 5.0 → temp_spike fired (no confirmation needed).
                    3 spike days in 7-day recent window → Δ ≈ 0.43 °C < 0.7 °C → no drift.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# ── paths ──────────────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).parents[1]
_ANIMALS_CSV = _REPO_ROOT / "data" / "demo" / "investor_v1" / "dm_animals.csv"
_OUTPUT_CSV = _REPO_ROOT / "data" / "demo" / "investor_v1" / "dm_sensors_daily.csv"

# ── constants ──────────────────────────────────────────────────────────────────
SEED = 42
# 10 days before Звёздочка mastitis (2026-03-10) — sensor anomaly detected here
REFERENCE_DATE = date(2026, 2, 28)
N_DAYS = 180

# Seeded anomaly targets
_ZVEZDOCHKA = "4821"   # rumination_drop
_MALINA = "3891"       # data_dropout
_NOCHKA = "3142"       # temp_spike

# Normal baselines: (μ, σ) — realistic dairy-cow values
_ACT_MU, _ACT_SD = 4500.0, 200.0   # activity_count (steps/day)
_RUM_MU, _RUM_SD = 500.0,  15.0    # rumination_min
_LYI_MU, _LYI_SD = 720.0,  20.0   # lying_min
_TMP_MU, _TMP_SD = 38.5,    0.10   # temperature_c (°C)

# Anomaly values
_RUM_DROP = 200.0   # Звёздочка: extreme low → z ≈ –20
_TMP_SPIKE = 39.5   # Ночка: fever → z ≈ 22
_DROPOUT_DAYS = 5   # Малина: 5-day sensor gap
_SPIKE_DAYS = 3     # Ночка: 3 consecutive fever days


def _generate() -> pd.DataFrame:
    rng = np.random.default_rng(SEED)
    animals = pd.read_csv(_ANIMALS_CSV)["animal_id"].astype(str).tolist()
    start = REFERENCE_DATE - timedelta(days=N_DAYS - 1)
    dates = [start + timedelta(days=i) for i in range(N_DAYS)]

    rows: list[dict] = []
    for animal_id in animals:
        # 179 noisy days, then last day pinned to μ (prevents accidental z > 5.0 at eval point)
        act = np.append(rng.normal(_ACT_MU, _ACT_SD, N_DAYS - 1).clip(0), _ACT_MU)
        rum = np.append(rng.normal(_RUM_MU, _RUM_SD, N_DAYS - 1).clip(0), _RUM_MU)
        lyi = np.append(rng.normal(_LYI_MU, _LYI_SD, N_DAYS - 1).clip(0), _LYI_MU)
        tmp = np.append(rng.normal(_TMP_MU, _TMP_SD, N_DAYS - 1).clip(36.0, 42.0), _TMP_MU)

        if animal_id == _ZVEZDOCHKA:
            # Pre-mastitis signal: extreme rumination drop on last day only.
            # z = (200 – 500) / (1.4826 × MAD_baseline) >> 5.0 → no confirmation needed.
            rum[-1] = _RUM_DROP

        elif animal_id == _MALINA:
            # Broken sensor: last 5 days NaN → gap_days = 5 → data_dropout.
            # Pin day before gap (index –6) to μ so last-observed-day has z = 0.
            act[-_DROPOUT_DAYS - 1] = _ACT_MU
            rum[-_DROPOUT_DAYS - 1] = _RUM_MU
            lyi[-_DROPOUT_DAYS - 1] = _LYI_MU
            tmp[-_DROPOUT_DAYS - 1] = _TMP_MU
            act[-_DROPOUT_DAYS:] = np.nan
            rum[-_DROPOUT_DAYS:] = np.nan
            lyi[-_DROPOUT_DAYS:] = np.nan
            tmp[-_DROPOUT_DAYS:] = np.nan

        elif animal_id == _NOCHKA:
            # Fever: last 3 days at 39.5 °C.
            # Last day already pinned to μ in step above; override with spike value.
            tmp[-_SPIKE_DAYS:] = _TMP_SPIKE

        for i, d in enumerate(dates):
            a, r, l_, t = act[i], rum[i], lyi[i], tmp[i]
            rows.append(
                {
                    "animal_id": animal_id,
                    "date": d.isoformat(),
                    "activity_count": round(float(a), 1) if not np.isnan(a) else None,
                    "rumination_min": round(float(r), 1) if not np.isnan(r) else None,
                    "lying_min": round(float(l_), 1) if not np.isnan(l_) else None,
                    "temperature_c": round(float(t), 2) if not np.isnan(t) else None,
                }
            )

    return pd.DataFrame(rows)


def _smoke_check(df: pd.DataFrame) -> bool:
    """Return True iff detect_sensor_anomalies finds exactly the 3 seeded anomalies."""
    import sys  # noqa: PLC0415
    _src = str(_REPO_ROOT / "src")
    if _src not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
        sys.path.insert(0, _src)
    from genomeai.sensor_anomaly_v1 import detect_sensor_anomalies  # noqa: PLC0415

    check = df.rename(
        columns={"activity_count": "activity_steps", "temperature_c": "body_temp_c"}
    ).copy()
    check["farm_id"] = "INV_FARM_001"

    anomalies = detect_sensor_anomalies(check)
    expected = {_ZVEZDOCHKA: "rumination_drop", _MALINA: "data_dropout", _NOCHKA: "temp_spike"}
    found = {str(r["animal_id"]): str(r["anomaly_type"]) for _, r in anomalies.iterrows()}

    ok = len(anomalies) == 3
    if not ok:
        print(f"  [FAIL] Expected 3 anomalies, got {len(anomalies)}")
        if not anomalies.empty:
            print(anomalies[["animal_id", "anomaly_type", "score"]].to_string(index=False))
    for aid, atype in expected.items():
        actual = found.get(aid, "<missing>")
        status = "OK" if actual == atype else "FAIL"
        if status == "FAIL":
            ok = False
        print(f"  [{status}] animal {aid}: expected {atype!r}, got {actual!r}")

    print(f"  Smoke: {'PASS' if ok else 'FAIL'} — {len(anomalies)} anomalies detected")
    return ok


def main() -> None:
    print(f"Reading animals from {_ANIMALS_CSV} …")
    df = _generate()
    n_animals = df["animal_id"].nunique()
    n_dates = df["date"].nunique()
    print(f"  Generated {len(df):,} rows — {n_animals} animals × {n_dates} days")
    print(f"  Date range: {df['date'].min()} → {df['date'].max()}")

    print(f"Saving to {_OUTPUT_CSV} …")
    _OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(_OUTPUT_CSV, index=False)
    print("  Saved.")

    print("Running smoke check …")
    if not _smoke_check(df):
        sys.exit(1)


if __name__ == "__main__":
    main()
