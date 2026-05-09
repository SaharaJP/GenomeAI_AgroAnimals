"""§3.2.4 NPV cull/keep model.

Formulas (diploma 3.18–3.20):

    NPV_keep = Σ_{t=1..T} (M_t + C_t − H_t) · p_t / (1+r)^t
              + V_salv · p_T / (1+r)^T

    NPV_cull = S_meat − R_heifer
              + Σ_{t=1..T} (M_t^(h) + C_t^(h) − H_t^(h)) · p_t^(h) / (1+r)^t

Decision: keep if NPV_keep > NPV_cull, else cull.

Constants are hardcoded; investor_v1 demo dataset has no dm_prices.csv.
The values reflect Russian dairy market 2025-26 ranges and are documented
in the narrative_md returned by recommend(). To override per-call, pass
arguments to compute_*().
"""
from __future__ import annotations

import datetime
import math
from typing import Any, Optional

import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

DEFAULTS: dict[str, float | int] = {
    "milk_price_rub_per_kg":        30.0,
    "meat_price_rub_per_kg_live":  250.0,
    "heifer_replacement_cost_rub": 150_000.0,
    "feed_cost_rub_per_kg_milk":    12.0,
    "vet_cost_rub_per_year":      5_000.0,
    "discount_rate_default":          0.13,
    "horizon_years_default":          4,
    "monthly_cull_prob":               0.022,   # legacy fallback; production uses _baseline_cull_prob(parity)
    "live_weight_kg_default":         620.0,    # Holstein adult
    "breed_avg_peak_kg":              42.0,     # used to scale M_t per cow
    "peak_fallback_ratio":             1.4,     # peak ≈ 1.4 × avg_daily (305d curve)
}


def _animal_record(animal_id: str, store) -> Optional[dict]:
    df = store.animals()
    if df is None or df.empty:
        return None
    rows = df[df["animal_id"].astype(str) == str(animal_id)]
    if rows.empty:
        return None
    return rows.iloc[0].to_dict()


def _age_years(animal_id: str, store, *, today: Optional[datetime.date] = None) -> Optional[float]:
    rec = _animal_record(animal_id, store)
    if not rec:
        return None
    bd = rec.get("birth_date")
    if not bd:
        return None
    try:
        birth = datetime.date.fromisoformat(str(bd)[:10])
    except (TypeError, ValueError):
        return None
    today = today or datetime.date.today()
    return round((today - birth).days / 365.25, 2)


def _last_calving(animal_id: str, store) -> Optional[datetime.date]:
    lact = _latest_lactation(animal_id, store)
    if not lact or not lact.get("calving_date"):
        return None
    try:
        return datetime.date.fromisoformat(str(lact["calving_date"])[:10])
    except (TypeError, ValueError):
        return None


def _is_open_cow(
    animal_id: str, store, *, today: Optional[datetime.date] = None
) -> tuple[bool, int]:
    """Return (is_open, days_since_calving). Open = >150 DIM and no
    successful breeding after the latest calving."""
    today = today or datetime.date.today()
    calving = _last_calving(animal_id, store)
    if not calving:
        return False, 0
    days_since = (today - calving).days
    if days_since <= 150:
        return False, days_since
    accessor = getattr(store, "breedings", None)
    if accessor is None:
        return days_since > 200, days_since
    df = accessor()
    if df is None or df.empty or "animal_id" not in df.columns:
        return days_since > 200, days_since
    rows = df[df["animal_id"].astype(str) == str(animal_id)].copy()
    if rows.empty or "date" not in rows.columns:
        return True, days_since
    rows["date"] = pd.to_datetime(rows["date"], errors="coerce")
    rows = rows.dropna(subset=["date"])
    rows = rows[rows["date"] >= pd.Timestamp(calving)]
    if rows.empty:
        return True, days_since
    if "result" not in rows.columns:
        return True, days_since
    pregnant = rows[rows["result"].astype(str).str.lower() == "pregnant"]
    return pregnant.empty, days_since


def _treatment_recurrence_count(animal_id: str, store) -> int:
    """Count pairs of same-treatment_type within 60 days for animal."""
    accessor = getattr(store, "treatments", None)
    if accessor is None:
        return 0
    df = accessor()
    if df is None or df.empty or "animal_id" not in df.columns:
        return 0
    rows = df[df["animal_id"].astype(str) == str(animal_id)].copy()
    if rows.empty or "treatment_type" not in rows.columns or "start_date" not in rows.columns:
        return 0
    rows["start_date"] = pd.to_datetime(rows["start_date"], errors="coerce")
    rows = rows.dropna(subset=["start_date"]).sort_values("start_date")
    pairs = 0
    for _tt, dates in rows.groupby("treatment_type")["start_date"]:
        dates_list = list(dates)
        for i in range(len(dates_list) - 1):
            if (dates_list[i + 1] - dates_list[i]).days <= 60:
                pairs += 1
    return pairs


def _latest_lactation(animal_id: str, store) -> Optional[dict]:
    """Return the most recent lactation record for an animal, or None."""
    if not hasattr(store, "lactations"):
        return None
    df = store.lactations()
    if df is None or df.empty:
        return None
    rows = df[df["animal_id"].astype(str) == str(animal_id)]
    if rows.empty:
        return None
    rows = rows.sort_values("calving_date", ascending=False)
    return rows.iloc[0].to_dict()


def _count_high_mastitis(animal_id: str, store) -> int:
    """Count high-severity mastitis events for the animal in available history."""
    if not hasattr(store, "health_events"):
        return 0
    df = store.health_events()
    if df is None or df.empty:
        return 0
    rows = df[df["animal_id"].astype(str) == str(animal_id)]
    if rows.empty:
        return 0
    mastitis = rows[rows["event_type"].astype(str).str.lower() == "mastitis"]
    if "severity" in mastitis.columns:
        return int(len(mastitis[mastitis["severity"].astype(str).str.lower() == "high"]))
    return int(len(mastitis))


def _count_lameness(animal_id: str, store) -> int:
    """Count lameness events (any severity)."""
    if not hasattr(store, "health_events"):
        return 0
    df = store.health_events()
    if df is None or df.empty:
        return 0
    rows = df[df["animal_id"].astype(str) == str(animal_id)]
    if rows.empty:
        return 0
    return int(len(rows[rows["event_type"].astype(str).str.lower() == "lameness"]))


def _avg_recent_scc(animal_id: str, store) -> Optional[float]:
    """Mean SCC across the milkings the store has for this animal. None if no data."""
    accessor = getattr(store, "milk_yields", None) or getattr(store, "milkings", None)
    if accessor is None:
        return None
    df = accessor()
    if df is None or df.empty or "scc_cells_ml" not in df.columns:
        return None
    rows = df[df["animal_id"].astype(str) == str(animal_id)]
    if rows.empty:
        return None
    series = rows["scc_cells_ml"].dropna()
    if series.empty:
        return None
    return float(series.mean())


def _health_burden_signal(animal_id: str, store) -> dict:
    """Composite health-economic score combining four orthogonal signals.

    Design (P1-2b): each component contributes to a continuous total_score in
    [0, ~10]; multipliers are smooth functions of total_score so a clean cow
    has near-baseline penalty and a chronically-sick cow gets aggressive
    penalty. This replaces the earlier binary "≥2 high-severity mastitis"
    rule which was honestly calibrated to flip Малина (3891) but gave
    discrete behavior for any other cow.

    Components:
        mastitis_score   = min(count_high_severity × 1.5, 4.0)
        late_dim_score   = max(0, (days_in_milk − 200) / 50)         # 0..2.1
        parity_score     = max(0, lactation_no − 3) × 0.8            # 0..N
        scc_score        = clamp((avg_scc − 200k) / 200k, 0, 3.0)
        lameness_score   = min(count_lameness × 1.0, 3.0)

    Multiplier mapping (linear):
        milk_factor      = max(0.50, 1.0 − total × 0.06)
        vet_factor       = 1.0 + total × 0.40
        cull_prob_factor = 1.0 + total × 0.15

    Returns the full structured signal (components + multipliers) so the
    API response, narrative_md and rationale can show the operator exactly
    why the score landed where it did. Diploma §3.2.4 still drives the
    formulas; this fn supplies M_t / H_t / p_t adjustments per animal.
    """
    components: dict[str, Any] = {}

    high_mast = _count_high_mastitis(animal_id, store)
    components["mastitis_high_count"] = high_mast
    mastitis_score = min(high_mast * 1.5, 4.0)
    components["mastitis_score"] = round(mastitis_score, 2)

    lact = _latest_lactation(animal_id, store)
    dim = 0
    lact_no = 0
    if lact is not None:
        try:
            dim = int(float(lact.get("days_in_milk") or 0))
        except (TypeError, ValueError):
            dim = 0
        try:
            lact_no = int(float(lact.get("lactation_no") or 0))
        except (TypeError, ValueError):
            lact_no = 0
    components["days_in_milk"] = dim
    components["lactation_no"] = lact_no

    late_dim_score = max(0.0, (dim - 200) / 50.0) if dim > 200 else 0.0
    components["late_dim_score"] = round(late_dim_score, 2)

    parity_score = max(0, lact_no - 3) * 0.8
    components["parity_score"] = round(parity_score, 2)

    avg_scc = _avg_recent_scc(animal_id, store)
    components["avg_scc_recent"] = round(avg_scc, 0) if avg_scc is not None else None
    if avg_scc is not None and avg_scc > 200_000:
        scc_score = min((avg_scc - 200_000) / 200_000, 3.0)
    else:
        scc_score = 0.0
    components["scc_score"] = round(scc_score, 2)

    lameness_count = _count_lameness(animal_id, store)
    components["lameness_count"] = lameness_count
    lameness_score = min(lameness_count * 1.0, 3.0)
    components["lameness_score"] = round(lameness_score, 2)

    age_years = _age_years(animal_id, store)
    components["age_years"] = age_years
    age_score = 0.0
    if age_years is not None and age_years > 5.0:
        age_score = min((age_years - 5.0) * 0.5, 4.0)
    components["age_score"] = round(age_score, 2)

    is_open, days_since_calving = _is_open_cow(animal_id, store)
    components["is_open_cow"] = is_open
    components["days_since_calving"] = days_since_calving
    days_open_score = 0.0
    if is_open and days_since_calving > 150:
        days_open_score = min((days_since_calving - 150) / 50.0, 3.0)
    components["days_open_score"] = round(days_open_score, 2)

    recurrence_count = _treatment_recurrence_count(animal_id, store)
    components["treatment_recurrence_count"] = recurrence_count
    treatment_score = min(recurrence_count * 1.0, 3.0)
    components["treatment_recurrence_score"] = round(treatment_score, 2)

    total = (
        mastitis_score + late_dim_score + parity_score + scc_score
        + lameness_score + age_score + days_open_score + treatment_score
    )
    components["total_score"] = round(total, 2)

    milk_factor      = max(0.50, 1.0 - total * 0.06)
    vet_factor       = 1.0 + total * 0.40
    cull_prob_factor = 1.0 + total * 0.15

    return {
        # Backward-compat keys used by older narrative paths
        "recurrent":        bool(high_mast >= 2),
        "count":            high_mast,
        # Composite output (P1-2b)
        "components":       components,
        "milk_factor":      round(milk_factor, 4),
        "vet_factor":       round(vet_factor, 4),
        "cull_prob_factor": round(cull_prob_factor, 4),
    }


# Legacy alias — kept so external callers (and the narrative builder) that
# expect the old name keep working. The new signature is what compute_npv_keep
# actually consumes.
_recurrent_mastitis_signal = _health_burden_signal


# Holstein cull-prob per month, stratified by parity (Compton 2017).
_PARITY_CULL_PROB = {
    1: 0.018,  # L1 — heifers, low cull
    2: 0.020,  # L2-3
    3: 0.020,
    4: 0.025,  # L4 — productivity declines
    5: 0.035,  # L5+ — aggressive cull pressure
}


def _baseline_cull_prob(lactation_no: int) -> float:
    """Return monthly baseline cull probability stratified by parity.

    Uses Holstein survival literature (Hadley 2006, Compton 2017).
    Falls back to DEFAULTS["monthly_cull_prob"] (0.022) via L2 entry for
    unknown/zero parity. For parity ≥5, uses the L5 rate (0.035).
    """
    if lactation_no <= 0:
        return _PARITY_CULL_PROB[2]  # default mid-parity
    return _PARITY_CULL_PROB.get(lactation_no, _PARITY_CULL_PROB[5])


def _peak_daily_from_lactation(lact: Optional[dict], c: dict) -> float:
    """Derive peak daily milk (kg) from a lactation record.

    Priority:
    1. peak_milk_kg column (if present and non-null).
    2. milk_305d_kg / 305 * peak_fallback_ratio  (dm_lactations.csv lacks peak col).
    3. breed_avg_peak_kg constant.
    """
    if lact is None:
        return float(c["breed_avg_peak_kg"])

    # 1. Direct peak column
    pk = lact.get("peak_milk_kg")
    if pk is not None:
        try:
            v = float(pk)
            if v > 0:
                return v
        except (TypeError, ValueError):
            pass

    # 2. Fallback: milk_305d_kg / 305 * 1.4
    m305 = lact.get("milk_305d_kg")
    if m305 is not None:
        try:
            v = float(m305)
            if v > 0:
                return v / 305.0 * float(c["peak_fallback_ratio"])
        except (TypeError, ValueError):
            pass

    # 3. Breed average
    return float(c["breed_avg_peak_kg"])


def _project_monthly_milk(peak_kg: float, lactation_dim_start: int, horizon_months: int) -> list[float]:
    """Stylized monthly milk projection (kg/month). Used for the heifer scenario
    in compute_npv_cull where there is no animal-specific history. Per-cow
    projections in compute_npv_keep go through _project_monthly_milk_wood.
    """
    months: list[float] = []
    for m in range(horizon_months):
        decay = max(0.40, 1.0 - 0.05 * m)
        months.append(round(peak_kg * 30.0 * decay, 1))
    return months


# Holstein breed-average Wood (1967) parameters.
_WOOD_DEFAULTS = {"a": 25.0, "b": 0.20, "c": 0.003}


def _wood_curve(t, a: float, b: float, c: float):
    """Wood (1967) lactation curve. t = DIM in days."""
    t_safe = np.maximum(np.asarray(t, dtype=float), 1.0)
    return a * np.power(t_safe, b) * np.exp(-c * t_safe)


def _fit_wood_for_animal(animal_id: str, store) -> dict:
    """Fit Wood (a,b,c) on the animal's milk history; fallback to defaults."""
    accessor = getattr(store, "milk_yields", None) or getattr(store, "milkings", None)
    if accessor is None:
        return {**_WOOD_DEFAULTS, "fit": "fallback_no_accessor"}
    df = accessor()
    if df is None or df.empty or "animal_id" not in df.columns:
        return {**_WOOD_DEFAULTS, "fit": "fallback_empty"}
    rows = df[df["animal_id"].astype(str) == str(animal_id)]
    if len(rows) < 30:
        return {**_WOOD_DEFAULTS, "fit": f"fallback_insufficient_{len(rows)}"}

    lact = _latest_lactation(animal_id, store)
    if not lact or not lact.get("calving_date"):
        return {**_WOOD_DEFAULTS, "fit": "fallback_no_calving"}
    try:
        calving = datetime.date.fromisoformat(str(lact["calving_date"])[:10])
    except (TypeError, ValueError):
        return {**_WOOD_DEFAULTS, "fit": "fallback_bad_calving"}

    rows = rows.copy()
    rows["date"] = pd.to_datetime(rows["date"], errors="coerce")
    rows = rows.dropna(subset=["date", "milk_kg"])
    rows["dim"] = (rows["date"].dt.date - calving).apply(
        lambda d: d.days if d is not None else None
    )
    rows = rows[(rows["dim"] >= 5) & (rows["dim"] <= 305)]
    if len(rows) < 30:
        return {**_WOOD_DEFAULTS, "fit": f"fallback_after_filter_{len(rows)}"}

    t = rows["dim"].astype(float).to_numpy()
    y = rows["milk_kg"].astype(float).to_numpy()
    try:
        popt, _ = curve_fit(_wood_curve, t, y, p0=[25.0, 0.20, 0.003], maxfev=2000)
        a, b, c = float(popt[0]), float(popt[1]), float(popt[2])
        if not (5.0 < a < 80.0 and 0.05 < b < 0.40 and 0.001 < c < 0.01):
            return {**_WOOD_DEFAULTS, "fit": f"fallback_implausible_a{a:.1f}_b{b:.2f}_c{c:.4f}"}
        return {"a": a, "b": b, "c": c, "fit": f"per_cow_n{len(rows)}"}
    except Exception as exc:
        return {**_WOOD_DEFAULTS, "fit": f"fallback_curve_fit_error_{type(exc).__name__}"}


def _project_monthly_milk_wood(
    animal_id: str, store, horizon_months: int
) -> tuple[list[float], dict]:
    """Per-cow Wood-curve projection. Returns (monthly_milk_kg, params)."""
    params = _fit_wood_for_animal(animal_id, store)
    lact = _latest_lactation(animal_id, store)
    dim_start = 1
    if lact:
        try:
            dim_start = max(1, int(float(lact.get("days_in_milk") or 1)))
        except (TypeError, ValueError):
            dim_start = 1
    monthly: list[float] = []
    for m in range(horizon_months):
        t0 = dim_start + m * 30
        # Cyclic 1..365 (305 milking + 60 dry); >305 = dry month → 0.
        t_in_lact = ((t0 - 1) % 365) + 1
        if t_in_lact > 305:
            monthly.append(0.0)
            continue
        ts = np.array([t_in_lact, t_in_lact + 7, t_in_lact + 15,
                       min(t_in_lact + 22, 305)], dtype=float)
        daily_kg = _wood_curve(ts, params["a"], params["b"], params["c"]).mean()
        monthly.append(round(float(daily_kg) * 30.0, 1))
    return monthly, params


def compute_npv_keep(
    animal_id: str,
    store,
    *,
    horizon_years: int = DEFAULTS["horizon_years_default"],
    r: float = DEFAULTS["discount_rate_default"],
    constants: Optional[dict] = None,
) -> dict:
    c = {**DEFAULTS, **(constants or {})}
    horizon_months = horizon_years * 12

    lact = _latest_lactation(animal_id, store)
    peak_daily = _peak_daily_from_lactation(lact, c)
    health = _recurrent_mastitis_signal(animal_id, store)

    raw_milk, wood_params = _project_monthly_milk_wood(
        animal_id, store, horizon_months
    )
    monthly_milk = [m * health["milk_factor"] for m in raw_milk]
    monthly_vet = c["vet_cost_rub_per_year"] * health["vet_factor"] / 12.0
    parity = (lact or {}).get("lactation_no") or 0
    try:
        parity = int(float(parity))
    except (TypeError, ValueError):
        parity = 0
    baseline_cull = _baseline_cull_prob(parity)
    monthly_cull_prob = baseline_cull * health["cull_prob_factor"]

    npv = 0.0
    breakdown: list[dict] = []
    survival = 1.0
    for t, milk_kg in enumerate(monthly_milk, start=1):
        revenue   = milk_kg * c["milk_price_rub_per_kg"]
        feed_cost = milk_kg * c["feed_cost_rub_per_kg_milk"]
        vet_cost  = monthly_vet
        cash_flow = revenue - feed_cost - vet_cost
        survival *= (1.0 - monthly_cull_prob)
        discount  = (1.0 + r) ** (t / 12.0)
        contrib   = cash_flow * survival / discount
        npv += contrib
        if t <= 6 or t == horizon_months:
            breakdown.append({
                "month": t,
                "milk_kg": round(milk_kg, 1),
                "cash_flow_rub": round(cash_flow, 2),
                "survival": round(survival, 4),
                "discounted_rub": round(contrib, 2),
            })

    salvage = float(c["live_weight_kg_default"]) * c["meat_price_rub_per_kg_live"]
    salvage_pv = salvage * survival / ((1.0 + r) ** horizon_years)
    npv += salvage_pv

    return {
        "animal_id": str(animal_id),
        "horizon_months": horizon_months,
        "discount_rate": r,
        "peak_kg_used": peak_daily,
        "baseline_cull_prob": baseline_cull,
        "wood_params": wood_params,
        "salvage_rub_pv": round(salvage_pv, 2),
        "npv_rub": round(npv, 2),
        "monthly_breakdown": breakdown,
        "health_signal": health,
    }


def compute_npv_cull(
    animal_id: str,
    store,
    *,
    horizon_years: int = DEFAULTS["horizon_years_default"],
    r: float = DEFAULTS["discount_rate_default"],
    constants: Optional[dict] = None,
) -> dict:
    """NPV of culling now and replacing with a heifer.

    Heifer's earnings: ~70% of an established cow's M_t for the first 12 months,
    then comparable. Simplified: scale heifer's monthly_milk by 0.7 throughout.
    """
    c = {**DEFAULTS, **(constants or {})}
    horizon_months = horizon_years * 12

    salvage_meat = float(c["live_weight_kg_default"]) * c["meat_price_rub_per_kg_live"]
    replacement  = c["heifer_replacement_cost_rub"]

    heifer_peak = float(c["breed_avg_peak_kg"]) * 0.85  # conservative first-lact peak
    monthly_milk = [m * 0.7 for m in _project_monthly_milk(heifer_peak, 0, horizon_months)]

    npv_heifer = 0.0
    survival = 1.0
    for t, milk_kg in enumerate(monthly_milk, start=1):
        revenue   = milk_kg * c["milk_price_rub_per_kg"]
        feed_cost = milk_kg * c["feed_cost_rub_per_kg_milk"]
        vet_cost  = c["vet_cost_rub_per_year"] / 12.0
        cash_flow = revenue - feed_cost - vet_cost
        survival *= (1.0 - c["monthly_cull_prob"])
        discount  = (1.0 + r) ** (t / 12.0)
        npv_heifer += cash_flow * survival / discount

    npv = salvage_meat - replacement + npv_heifer

    return {
        "animal_id": str(animal_id),
        "horizon_months": horizon_months,
        "discount_rate": r,
        "salvage_meat_rub": round(salvage_meat, 2),
        "replacement_cost_rub": round(replacement, 2),
        "heifer_lifetime_npv_rub": round(npv_heifer, 2),
        "npv_rub": round(npv, 2),
    }


def _build_sensitivity_table(animal_id: str, store, base_r: float) -> list[dict]:
    """3×3 grid: discount-rate × milk-price (variant ±20%)."""
    rows: list[dict] = []
    rate_grid  = [base_r * 0.77, base_r, base_r * 1.23]
    price_grid = [DEFAULTS["milk_price_rub_per_kg"] * 0.80,
                  DEFAULTS["milk_price_rub_per_kg"],
                  DEFAULTS["milk_price_rub_per_kg"] * 1.20]

    for r_val in rate_grid:
        for p_milk in price_grid:
            constants = {"milk_price_rub_per_kg": p_milk}
            keep = compute_npv_keep(animal_id, store, r=r_val, constants=constants)["npv_rub"]
            cull = compute_npv_cull(animal_id, store, r=r_val, constants=constants)["npv_rub"]
            rows.append({
                "discount_rate": round(r_val, 4),
                "milk_price_rub_per_kg": round(p_milk, 2),
                "npv_keep_rub": round(keep, 2),
                "npv_cull_rub": round(cull, 2),
                "decision": "keep" if keep > cull else "cull",
            })
    return rows


def _build_narrative_md(animal_id: str, keep: dict, cull: dict, decision: str) -> str:
    diff = keep["npv_rub"] - cull["npv_rub"]
    health = keep.get("health_signal") or {}
    components = (health or {}).get("components") or {}
    total_score = components.get("total_score", 0.0)
    health_block = ""
    if total_score > 0.5:
        rows: list[str] = []
        if components.get("mastitis_score", 0) > 0:
            rows.append(
                f"- Мастит (high severity): {components['mastitis_high_count']} эпизодов "
                f"→ +{components['mastitis_score']:.1f} б."
            )
        if components.get("late_dim_score", 0) > 0:
            rows.append(
                f"- DIM = {components['days_in_milk']} (late lactation, близко к сухостою) "
                f"→ +{components['late_dim_score']:.1f} б."
            )
        if components.get("parity_score", 0) > 0:
            rows.append(
                f"- Лактация № {components['lactation_no']} (≥4 → снижение продуктивности) "
                f"→ +{components['parity_score']:.1f} б."
            )
        scc_avg = components.get("avg_scc_recent")
        if components.get("scc_score", 0) > 0 and scc_avg is not None:
            rows.append(
                f"- Хронически высокий SCC: {int(scc_avg):,}/мл (порог 200к) "
                f"→ +{components['scc_score']:.1f} б."
            )
        if components.get("lameness_score", 0) > 0:
            rows.append(
                f"- Хромота: {components['lameness_count']} эпизодов "
                f"→ +{components['lameness_score']:.1f} б."
            )
        if components.get("age_score", 0) > 0 and components.get("age_years") is not None:
            rows.append(
                f"- Возраст {components['age_years']:.1f} лет (>5 — амортизация продуктивности) "
                f"→ +{components['age_score']:.1f} б."
            )
        if components.get("days_open_score", 0) > 0:
            rows.append(
                f"- Открытая корова: {components['days_since_calving']} дн. с отёла без подтверждённой стельности "
                f"→ +{components['days_open_score']:.1f} б."
            )
        if components.get("treatment_recurrence_score", 0) > 0:
            rows.append(
                f"- Рецидивирующее лечение: {components['treatment_recurrence_count']} пар за 60 дн. "
                f"→ +{components['treatment_recurrence_score']:.1f} б."
            )
        rows_md = "\n".join(rows) if rows else "- (factor breakdown empty)"
        health_block = (
            "\n### Композитный health-score\n"
            f"**Total score: {total_score:.2f}** "
            f"(milk ×{health['milk_factor']:.2f}, vet ×{health['vet_factor']:.2f}, "
            f"cull-prob ×{health['cull_prob_factor']:.2f})\n\n"
            f"{rows_md}\n"
        )
    return f"""## Рекомендация по корове {animal_id}

**Решение: {'оставить' if decision == 'keep' else 'выбраковать'}**

- NPV(оставить) = {keep['npv_rub']:,.0f} ₽
- NPV(выбраковать) = {cull['npv_rub']:,.0f} ₽
- Разница: {diff:,.0f} ₽ ({'в пользу оставления' if diff > 0 else 'в пользу выбраковки'})
{health_block}
### Ключевые параметры
- Горизонт: {keep['horizon_months'] // 12} лет
- Ставка дисконтирования: {keep['discount_rate']:.1%}
- Цена молока: {DEFAULTS['milk_price_rub_per_kg']:.0f} ₽/кг
- Цена живого веса: {DEFAULTS['meat_price_rub_per_kg_live']:.0f} ₽/кг
- Стоимость нетели: {DEFAULTS['heifer_replacement_cost_rub']:,.0f} ₽

### Ограничения модели
- Параметры цен и стоимостей зашиты в код (investor_v1 dataset не содержит dm_prices.csv).
- Кривая надоя — упрощённая (∝ peak · decay), без полной аппроксимации Wood-curve.
- Базовая вероятность выбытия — постоянная для породы (Holstein ~2.2%/мес).
- Здоровье: учитывается только бинарный сигнал «рецидивирующий мастит» (≥2 high-severity).

См. также: §3.2.4 ВКР, формулы 3.18–3.20.
""".strip()


def recommend(animal_id: str, store, *, horizon_years: int = 4, r: float = 0.13) -> dict[str, Any]:
    """Public API used by the FastAPI endpoint and by the AI tool executor."""
    keep = compute_npv_keep(animal_id, store, horizon_years=horizon_years, r=r)
    cull = compute_npv_cull(animal_id, store, horizon_years=horizon_years, r=r)
    decision = "keep" if keep["npv_rub"] > cull["npv_rub"] else "cull"
    sensitivity = _build_sensitivity_table(animal_id, store, base_r=r)
    narrative = _build_narrative_md(animal_id, keep, cull, decision)

    rationale: list[str] = []
    diff = keep["npv_rub"] - cull["npv_rub"]
    rationale.append(f"NPV_keep = {keep['npv_rub']:,.0f} ₽; NPV_cull = {cull['npv_rub']:,.0f} ₽")
    rationale.append(f"Разница {diff:+,.0f} ₽ ({'в пользу оставления' if diff > 0 else 'в пользу выбраковки'})")
    if abs(diff) < 50_000:
        rationale.append("Разница менее 50 000 ₽ — рекомендация чувствительна к цене молока и ставке.")
    health = keep.get("health_signal") or {}
    components = (health or {}).get("components") or {}
    total_score = components.get("total_score", 0.0)
    if total_score > 0.5:
        active_factors = [
            label for key, label in (
                ("mastitis_score", "мастит"),
                ("late_dim_score", "поздний DIM"),
                ("parity_score", "паритет"),
                ("scc_score", "хроничный SCC"),
                ("lameness_score", "хромота"),
                ("age_score", "возраст"),
                ("days_open_score", "затянувшаяся открытость"),
                ("treatment_recurrence_score", "рецидив лечения"),
            )
            if components.get(key, 0) > 0
        ]
        rationale.append(
            f"Health composite-score = {total_score:.2f} "
            f"({', '.join(active_factors) if active_factors else 'нет активных факторов'}) — "
            f"надой ×{health['milk_factor']:.2f}, "
            f"ветзатраты ×{health['vet_factor']:.2f}, "
            f"вероятность выбытия ×{health['cull_prob_factor']:.2f}."
        )

    return {
        "animal_id": str(animal_id),
        "decision": decision,
        "npv_keep": keep,
        "npv_cull": cull,
        "rationale": rationale,
        "sensitivity_table": sensitivity,
        "narrative_md": narrative,
        "evidence_chips": [{"type": "cow", "id": str(animal_id)}],
    }
