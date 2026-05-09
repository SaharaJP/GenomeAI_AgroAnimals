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

from typing import Any, Optional

DEFAULTS: dict[str, float | int] = {
    "milk_price_rub_per_kg":        30.0,
    "meat_price_rub_per_kg_live":  250.0,
    "heifer_replacement_cost_rub": 150_000.0,
    "feed_cost_rub_per_kg_milk":    12.0,
    "vet_cost_rub_per_year":      5_000.0,
    "discount_rate_default":          0.13,
    "horizon_years_default":          4,
    "monthly_cull_prob":               0.022,   # ~25%/year Holstein
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


def _recurrent_mastitis_signal(animal_id: str, store) -> dict:
    """Detect recurrent mastitis in last 12 months from dm_health_events.

    Per thesis §3.2.4: mastitis history affects M_t (milk loss), H_t (vet cost),
    and survival (higher cull-prob). Signal is binary: ≥2 mastitis events
    in last 12 months → "recurrent" → apply penalties.

    Returns dict with multipliers; defaults (no signal) preserve baseline.
    """
    no_signal = {"recurrent": False, "milk_factor": 1.0, "vet_factor": 1.0, "cull_prob_factor": 1.0, "count": 0}
    if not hasattr(store, "health_events"):
        return no_signal
    df = store.health_events()
    if df is None or df.empty:
        return no_signal
    rows = df[df["animal_id"].astype(str) == str(animal_id)]
    if rows.empty:
        return no_signal
    mastitis = rows[rows["event_type"].astype(str).str.lower() == "mastitis"]
    if "severity" in mastitis.columns:
        high_severity = mastitis[mastitis["severity"].astype(str).str.lower() == "high"]
    else:
        high_severity = mastitis
    count_high = int(len(high_severity))
    count_total = int(len(mastitis))
    # Recurrent ≡ ≥2 high-severity mastitis events. Single-episode or mixed
    # severities are absorbed into baseline vet_cost rather than triggering
    # the chronic-mastitis penalty.
    if count_high < 2:
        return {**no_signal, "count": count_total}
    return {
        "recurrent": True,
        "count": count_total,
        "milk_factor":      0.75,   # ~25% productivity loss from chronic udder inflammation
        "vet_factor":       3.0,    # repeated treatment courses + dry-off therapy
        "cull_prob_factor": 2.0,    # farmer-driven cull pressure
    }


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
    """Project monthly milk production (kg/month) from a Wood-style stylized curve.

    Use a simplified shape: rises to peak by 60 DIM, then declines by ~5%/month.
    For this MVP we approximate as: month_milk = peak_daily · 30 · decay_factor.
    decay_factor: m=1 → 1.0; m=2 → 0.95; m=3 → 0.90; … capped at 0.40.
    """
    months: list[float] = []
    for m in range(horizon_months):
        decay = max(0.40, 1.0 - 0.05 * m)
        months.append(round(peak_kg * 30.0 * decay, 1))
    return months


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

    monthly_milk = _project_monthly_milk(
        peak_daily * health["milk_factor"], 0, horizon_months,
    )
    monthly_vet = c["vet_cost_rub_per_year"] * health["vet_factor"] / 12.0
    monthly_cull_prob = c["monthly_cull_prob"] * health["cull_prob_factor"]

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
    health_block = ""
    if health.get("recurrent"):
        health_block = (
            "\n### Здоровье\n"
            f"- Зафиксирован **рецидивирующий мастит**: {health['count']} эпизодов "
            "(критерий ≥ 2 высоких степеней тяжести за 12 мес).\n"
            f"- Проекция надоя снижена на {(1 - health['milk_factor']) * 100:.0f}% "
            "(хроническое воспаление вымени).\n"
            f"- Ветеринарные затраты увеличены ×{health['vet_factor']:.0f} "
            "(повторные курсы, сухостойная терапия).\n"
            f"- Месячная вероятность выбытия ×{health['cull_prob_factor']:.0f}.\n"
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
    if health.get("recurrent"):
        rationale.append(
            f"Рецидивирующий мастит ({health['count']} эпизодов) — "
            f"надой ×{health['milk_factor']:.2f}, ветзатраты ×{health['vet_factor']:.0f}, "
            f"вероятность выбытия ×{health['cull_prob_factor']:.0f}."
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
