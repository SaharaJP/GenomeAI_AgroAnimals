# P1-2c Production-Grade NPV Model — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade `web_cabinet/ai/npv_cull.py` from the P1-2b "stylized peak·decay + binary mastitis + constant survival" model to a production-grade NPV with five orthogonal data-driven improvements. Each improvement is a separate commit so we can roll back individually if behavior drifts.

**Tech Stack:** Python 3.12, pandas, numpy, scipy.optimize.curve_fit (Wood curve fit).

**Brief reference:** Conversation 2026-05-09 — P1-2b composite score "не учитывает: days_open, treatment success rate, real Wood-curve, survival regression, age". User picked full scope.

**Commit strategy:** 5 feature commits + 1 docs/proof commit = 6 commits total.

**Pragmatic notes:**
1. We keep all changes additive: existing tests must still pass after each phase. Малина stays cull, Звёздочка stays keep.
2. scipy is already available in the project (used by core.application.predictors).
3. Wood-curve fit is per-cow when ≥30 milk-yield records exist; falls back to Holstein breed-average params otherwise.
4. Stratified survival uses Holstein literature (Hadley 2006, Compton 2017): L1 1.8%/mo, L2-3 2.0%/mo, L4 2.5%/mo, L5+ 3.5%/mo. Each multiplied by `cull_prob_factor` from health composite.
5. Days-open computed from `breedings.json` (latest insemination + result). Open cow = 150+ days since last calving with no `pregnant` confirmation.
6. Treatment recurrence: same `treatment_type` ≥2 times within 60-day window → "failed treatment" signal.

---

## Phase 1 — Stratified survival by parity (1 commit)

**Files:** `web_cabinet/ai/npv_cull.py`, `tests/web_cabinet/ai/test_npv_cull.py`

Replace constant `monthly_cull_prob: 0.022` in `DEFAULTS` with a parity-stratified lookup function.

- [ ] **Step 1: Add parity-stratified table to module**

```python
# Holstein cull-prob per month, stratified by parity (Compton 2017).
_PARITY_CULL_PROB = {
    1: 0.018,  # L1 — heifers, low cull
    2: 0.020,  # L2-3
    3: 0.020,
    4: 0.025,  # L4 — productivity declines
    5: 0.035,  # L5+ — aggressive cull pressure
}


def _baseline_cull_prob(lactation_no: int) -> float:
    if lactation_no <= 0:
        return _PARITY_CULL_PROB[2]   # default mid-parity
    return _PARITY_CULL_PROB.get(lactation_no, _PARITY_CULL_PROB[5])
```

- [ ] **Step 2: Use it in `compute_npv_keep`**

Replace `monthly_cull_prob = c["monthly_cull_prob"] * health["cull_prob_factor"]` with:
```python
parity = (lact or {}).get("lactation_no") or 0
try:
    parity = int(float(parity))
except (TypeError, ValueError):
    parity = 0
baseline_cull = _baseline_cull_prob(parity)
monthly_cull_prob = baseline_cull * health["cull_prob_factor"]
```

Surface `baseline_cull_prob` in the return dict for traceability.

- [ ] **Step 3: Update DEFAULTS comment** — change `monthly_cull_prob: 0.022 # ~25%/year Holstein` to `monthly_cull_prob: 0.022 # legacy fallback; production uses _baseline_cull_prob(parity)`.

- [ ] **Step 4: Test**

```python
def test_baseline_cull_prob_stratified_by_parity():
    from web_cabinet.ai.npv_cull import _baseline_cull_prob
    assert _baseline_cull_prob(1) < _baseline_cull_prob(4)
    assert _baseline_cull_prob(5) > _baseline_cull_prob(2)
    assert _baseline_cull_prob(0) == _baseline_cull_prob(2)  # fallback


def test_compute_npv_keep_uses_stratified_cull(rich_store):
    """High-parity cow gets aggressive cull-prob → lower NPV_keep."""
    # Build store with same animal at parity 2 vs parity 5
    s_low = _store_with(lactations=[dict(animal_id="C1", lactation_no=2,
        calving_date="2025-12-01", dryoff_date="2026-09-01", days_in_milk=100,
        milk_305d_kg=9000, fat_pct=3.8, protein_pct=3.2)])
    s_high = _store_with(lactations=[dict(animal_id="C1", lactation_no=6,
        calving_date="2025-12-01", dryoff_date="2026-09-01", days_in_milk=100,
        milk_305d_kg=9000, fat_pct=3.8, protein_pct=3.2)])
    npv_low  = compute_npv_keep("C1", s_low,  horizon_years=4, r=0.13)
    npv_high = compute_npv_keep("C1", s_high, horizon_years=4, r=0.13)
    assert npv_high["npv_rub"] < npv_low["npv_rub"]
    # Parity score also kicks in (5-3)*0.8=1.6 — composite already covers that;
    # this test specifically asserts the SURVIVAL component changed too.
    assert npv_high["baseline_cull_prob"] > npv_low["baseline_cull_prob"]
```

Expected: parity 2 → baseline 0.020, parity 6 → 0.035. Combined with composite parity_score, NPV_high should drop ≥10% vs NPV_low.

- [ ] **Step 5: Verify Malina/Star still flip correctly**

```bash
pytest tests/web_cabinet/ai/test_npv_cull.py tests/web_cabinet/animals/ -x -q
```

- [ ] **Step 6: Commit**

```bash
git add web_cabinet/ai/npv_cull.py tests/web_cabinet/ai/test_npv_cull.py
git commit -m "feat(P1-2c): parity-stratified survival probability

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 2 — Age via birth_date (1 commit)

Add age signal to composite. Age >5 years: linear contribution (age-5)·0.5, capped at 4.0. Animal data has `birth_date` ISO column.

- [ ] **Step 1: Add `_age_years` helper**

```python
import datetime

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
```

- [ ] **Step 2: Add `age_score` to `_health_burden_signal`**

Insert into the components dict construction, near `parity_score`:

```python
age_years = _age_years(animal_id, store)
components["age_years"] = age_years
age_score = 0.0
if age_years is not None and age_years > 5.0:
    age_score = min((age_years - 5.0) * 0.5, 4.0)
components["age_score"] = round(age_score, 2)

# extend total
total = mastitis_score + late_dim_score + parity_score + scc_score + lameness_score + age_score
```

- [ ] **Step 3: Update narrative_md and rationale to mention age** (mirror existing pattern for parity_score).

- [ ] **Step 4: Test**

```python
def test_age_score_zero_for_young_cow():
    s = _store_with(animals=[dict(animal_id="C1", farm_id="F", ear_tag="C1",
        breed="Holstein", sex="F", birth_date="2023-01-01", is_alive=True, status="active")])
    sig = _health_burden_signal("C1", s)
    assert sig["components"]["age_score"] == 0.0


def test_age_score_increases_with_age():
    s = _store_with(animals=[dict(animal_id="C1", farm_id="F", ear_tag="C1",
        breed="Holstein", sex="F", birth_date="2018-01-01", is_alive=True, status="active")])
    sig = _health_burden_signal("C1", s)
    # ~7 years old → (7-5)*0.5 = 1.0
    assert sig["components"]["age_score"] >= 0.5
    assert sig["components"]["age_years"] >= 7.0
```

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(P1-2c): add age signal to composite health score

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 3 — Days-open + treatment-recurrence (1 commit)

Two new signals from existing data:

### Days open (from `breedings.json`)

`breedings.json` is at `data/demo/investor_v1/breedings.json`. Currently `DemoDataStore` may not load it — check first. If not, add a loader.

A cow is "open" if:
1. Latest breeding result is `open` OR no `pregnant` confirmation
2. Days since last calving > 150 (target 85-130)

`days_open_score` = max(0, (days_since_calving − 150) / 50), capped at 3.0. Only kicks in if no successful breeding after the calving.

### Treatment recurrence (from `dm_treatments.csv`)

Already loadable via `store.treatments()`. `treatment_recurrence_score`:
- For each treatment_type with ≥2 occurrences within 60 days → +1.0 per pair
- Capped at 3.0

- [ ] **Step 1: Add accessors and helpers**

```python
def _last_calving(animal_id: str, store) -> Optional[datetime.date]:
    lact = _latest_lactation(animal_id, store)
    if not lact or not lact.get("calving_date"):
        return None
    try:
        return datetime.date.fromisoformat(str(lact["calving_date"])[:10])
    except (TypeError, ValueError):
        return None


def _is_open_cow(animal_id: str, store, today: Optional[datetime.date] = None) -> tuple[bool, int]:
    """Returns (is_open, days_since_calving)."""
    today = today or datetime.date.today()
    calving = _last_calving(animal_id, store)
    if not calving:
        return False, 0
    days_since = (today - calving).days
    if days_since <= 150:
        return False, days_since
    # Look at breedings.json — does the store load it?
    accessor = getattr(store, "breedings", None)
    if accessor is None:
        return days_since > 200, days_since  # no data → conservative open if very late
    df = accessor()
    if df is None or df.empty:
        return days_since > 200, days_since
    rows = df[df["animal_id"].astype(str) == str(animal_id)]
    rows = rows[pd.to_datetime(rows["date"]) >= pd.Timestamp(calving)]
    if rows.empty:
        return True, days_since
    pregnant = rows[rows["result"].astype(str).str.lower() == "pregnant"]
    return pregnant.empty, days_since


def _treatment_recurrence_count(animal_id: str, store) -> int:
    accessor = getattr(store, "treatments", None)
    if accessor is None:
        return 0
    df = accessor()
    if df is None or df.empty:
        return 0
    rows = df[df["animal_id"].astype(str) == str(animal_id)].copy()
    if rows.empty or "treatment_type" not in rows.columns or "start_date" not in rows.columns:
        return 0
    rows["start_date"] = pd.to_datetime(rows["start_date"], errors="coerce")
    rows = rows.dropna(subset=["start_date"]).sort_values("start_date")
    pairs = 0
    grouped = rows.groupby("treatment_type")["start_date"]
    for tt, dates in grouped:
        dates_list = list(dates)
        for i in range(len(dates_list) - 1):
            if (dates_list[i + 1] - dates_list[i]).days <= 60:
                pairs += 1
    return pairs
```

- [ ] **Step 2: If `DemoDataStore` lacks `breedings()` accessor, add it**

Check `web_cabinet/ai/context_helpers/demo_loader.py`:
```bash
grep -n 'def breedings\|breedings.json' web_cabinet/ai/context_helpers/demo_loader.py
```

If missing, add accessor that reads `breedings.json` (json, not csv — note distinction). Add to the `_load` map or via a dedicated helper.

- [ ] **Step 3: Plumb into `_health_burden_signal`**

```python
is_open, days_since_calving = _is_open_cow(animal_id, store)
components["is_open_cow"] = is_open
components["days_since_calving"] = days_since_calving
days_open_score = 0.0
if is_open and days_since_calving > 150:
    days_open_score = min((days_since_calving - 150) / 50, 3.0)
components["days_open_score"] = round(days_open_score, 2)

recurrence_count = _treatment_recurrence_count(animal_id, store)
components["treatment_recurrence_count"] = recurrence_count
treatment_score = min(recurrence_count * 1.0, 3.0)
components["treatment_recurrence_score"] = round(treatment_score, 2)

total = mastitis_score + late_dim_score + parity_score + scc_score + lameness_score + age_score + days_open_score + treatment_score
```

- [ ] **Step 4: Tests**

```python
def test_open_cow_signal():
    today = datetime.date.fromisoformat("2026-05-09")
    s = _store_with(
        lactations=[dict(animal_id="C1", lactation_no=2,
            calving_date="2025-08-01",  # ~280 days ago
            dryoff_date="2026-05-01", days_in_milk=280,
            milk_305d_kg=9000, fat_pct=3.8, protein_pct=3.2)],
    )
    # Mock breedings empty → open
    is_open, days = _is_open_cow("C1", s, today=today)
    assert is_open is True
    assert days >= 150


def test_treatment_recurrence_two_in_60_days():
    s = _store_with()
    # Need to add treatments manually — extend _store_with to accept treatments
    # ...
```

(extend `_store_with` helper to accept `treatments=` argument that builds a `dm_treatments` DataFrame.)

- [ ] **Step 5: Update narrative_md to surface days_open and recurrence components.**

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(P1-2c): days-open + treatment-recurrence signals

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 4 — Wood-curve milk projection (1 commit)

Replace `_project_monthly_milk(peak_kg, dim_start, horizon_months)` with a Wood-curve based projection per cow. Uses `milk_yields.json` history.

Wood-curve: `Y(t) = a · t^b · exp(−c·t)` where t is DIM in days.

- [ ] **Step 1: Add Wood-curve fit + projection**

```python
import math
import numpy as np
from scipy.optimize import curve_fit

# Holstein breed-average Wood parameters (Wood 1969 + dairy literature).
_WOOD_DEFAULTS = {"a": 25.0, "b": 0.20, "c": 0.003}


def _wood_curve(t: np.ndarray, a: float, b: float, c: float) -> np.ndarray:
    """Wood (1967) lactation curve. t = DIM in days."""
    t_safe = np.maximum(t, 1.0)
    return a * np.power(t_safe, b) * np.exp(-c * t_safe)


def _fit_wood_for_animal(animal_id: str, store) -> dict:
    """Fit Wood parameters (a,b,c) on the animal's milk history; fallback to defaults."""
    accessor = getattr(store, "milk_yields", None) or getattr(store, "milkings", None)
    if accessor is None:
        return {**_WOOD_DEFAULTS, "fit": "fallback_no_accessor"}
    df = accessor()
    if df is None or df.empty:
        return {**_WOOD_DEFAULTS, "fit": "fallback_empty"}
    rows = df[df["animal_id"].astype(str) == str(animal_id)]
    if len(rows) < 30:
        return {**_WOOD_DEFAULTS, "fit": f"fallback_insufficient_{len(rows)}"}

    # Need DIM per row — derive from date - last calving
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
    rows["dim"] = (rows["date"].dt.date - calving).apply(lambda d: d.days if d else None)
    rows = rows[(rows["dim"] >= 5) & (rows["dim"] <= 305)]
    if len(rows) < 30:
        return {**_WOOD_DEFAULTS, "fit": f"fallback_after_filter_{len(rows)}"}

    t = rows["dim"].astype(float).to_numpy()
    y = rows["milk_kg"].astype(float).to_numpy()
    try:
        popt, _ = curve_fit(_wood_curve, t, y, p0=[25.0, 0.20, 0.003], maxfev=2000)
        a, b, c = float(popt[0]), float(popt[1]), float(popt[2])
        # Sanity: reject implausible fits
        if not (5.0 < a < 80.0 and 0.05 < b < 0.40 and 0.001 < c < 0.01):
            return {**_WOOD_DEFAULTS, "fit": f"fallback_implausible_a{a:.1f}_b{b:.2f}_c{c:.4f}"}
        return {"a": a, "b": b, "c": c, "fit": f"per_cow_n{len(rows)}"}
    except Exception as exc:
        return {**_WOOD_DEFAULTS, "fit": f"fallback_curve_fit_error_{type(exc).__name__}"}


def _project_monthly_milk_wood(animal_id: str, store, horizon_months: int) -> tuple[list[float], dict]:
    """Per-cow Wood-curve projection. Returns (monthly_milk_kg_list, params)."""
    params = _fit_wood_for_animal(animal_id, store)
    # Start from current DIM if known, else from 1
    lact = _latest_lactation(animal_id, store)
    dim_start = 1
    if lact:
        try:
            dim_start = max(1, int(float(lact.get("days_in_milk") or 1)))
        except (TypeError, ValueError):
            dim_start = 1
    # Project monthly: integrate over each month (30 days)
    monthly: list[float] = []
    for m in range(horizon_months):
        # Start of this month in DIM days
        t0 = dim_start + m * 30
        # If we exceed 305 DIM, the cow goes dry → 0 milk for ~60 days, then new lactation
        # Simplified: when t0 > 305, simulate next lactation by resetting t0 = (t0 - 305) % 365 + 1
        t_in_lact = ((t0 - 1) % 365) + 1  # cyclic 1..365 (305 milking + 60 dry)
        if t_in_lact > 305:
            monthly.append(0.0)
            continue
        # Average milk over the month: sample 4 points and mean
        ts = np.array([t_in_lact, t_in_lact + 7, t_in_lact + 15, min(t_in_lact + 22, 305)])
        daily_kg = _wood_curve(ts, params["a"], params["b"], params["c"]).mean()
        monthly.append(round(float(daily_kg) * 30.0, 1))
    return monthly, params
```

- [ ] **Step 2: Use it in `compute_npv_keep`**

Replace:
```python
monthly_milk = _project_monthly_milk(
    peak_daily * health["milk_factor"], 0, horizon_months,
)
```

With:
```python
raw_milk, wood_params = _project_monthly_milk_wood(animal_id, store, horizon_months)
monthly_milk = [m * health["milk_factor"] for m in raw_milk]
```

Surface `wood_params` in the return dict for traceability.

- [ ] **Step 3: Tests**

```python
def test_wood_curve_breed_default_for_unknown_cow():
    s = _store_with()  # no milk_yields
    params = _fit_wood_for_animal("C1", s)
    assert params["a"] == _WOOD_DEFAULTS["a"]
    assert params["fit"].startswith("fallback_")


def test_wood_curve_fit_per_cow_when_history_sufficient():
    """Synthetic 90-day history with known Wood params should fit close."""
    import datetime
    a_true, b_true, c_true = 22.0, 0.22, 0.0035
    rows = []
    base = datetime.date(2025, 12, 1)
    for d in range(5, 200, 7):  # ~28 records
        t = float(d)
        y = float(a_true * (t ** b_true) * math.exp(-c_true * t))
        rows.append(dict(animal_id="C1", date=(base + datetime.timedelta(days=d)).isoformat(),
                         milk_kg=y, scc_cells_ml=200000, fat_pct=3.8, protein_pct=3.2))
    s = _store_with(
        animals=[dict(animal_id="C1", farm_id="F", ear_tag="C1", breed="Holstein",
                      sex="F", birth_date="2022-01-01", is_alive=True, status="active")],
        lactations=[dict(animal_id="C1", lactation_no=2, calving_date="2025-12-01",
                         dryoff_date="2026-09-01", days_in_milk=100,
                         milk_305d_kg=9000, fat_pct=3.8, protein_pct=3.2)],
        milk=rows,
    )
    params = _fit_wood_for_animal("C1", s)
    # 28 records < 30 threshold → fallback expected
    assert params["fit"].startswith("fallback_after_filter_") or params["fit"].startswith("per_cow_")
    # If we expand to 50 points it should fit
    rows_more = rows + [
        dict(animal_id="C1",
             date=(datetime.date(2025, 12, 1) + datetime.timedelta(days=d)).isoformat(),
             milk_kg=float(a_true * (d ** b_true) * math.exp(-c_true * d)),
             scc_cells_ml=200000, fat_pct=3.8, protein_pct=3.2)
        for d in range(5, 220, 4)  # +50 more
    ]
    s2 = _store_with(
        animals=[dict(animal_id="C1", farm_id="F", ear_tag="C1", breed="Holstein",
                      sex="F", birth_date="2022-01-01", is_alive=True, status="active")],
        lactations=[dict(animal_id="C1", lactation_no=2, calving_date="2025-12-01",
                         dryoff_date="2026-09-01", days_in_milk=100,
                         milk_305d_kg=9000, fat_pct=3.8, protein_pct=3.2)],
        milk=rows_more,
    )
    params2 = _fit_wood_for_animal("C1", s2)
    assert params2["fit"].startswith("per_cow_"), f"got: {params2['fit']}"
    # Within ±25% of truth
    assert 0.75 * a_true < params2["a"] < 1.25 * a_true


def test_project_monthly_milk_wood_for_real_cow(rich_store):
    """Звёздочка has real milk history in fixture; projection should be positive."""
    monthly, params = _project_monthly_milk_wood("4821", rich_store, 48)
    assert len(monthly) == 48
    assert all(m >= 0 for m in monthly)
    assert any(m > 0 for m in monthly[:6])  # first 6 months should produce
```

- [ ] **Step 4: Verify Малина+Звёздочка still flip correctly via TestClient**

```bash
PYTHONPATH=src:. python -c "...the snapshot one-liner..."
```

If decisions break — Wood curve fit may give Малина unexpectedly high milk projection (her real milk yields might be still good). That's OK — it forces the recurrence and DIM signals to dominate, which is the design intent.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(P1-2c): per-cow Wood-curve milk projection

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 5 — Calibration + acceptance verification (1 commit)

After Phases 1-4, run live snapshot. If Малина no longer recommends cull or Звёздочка no longer recommends keep, calibrate one or two component weights (NOT add new components). Document tweaks in narrative_md.

- [ ] **Step 1: Live snapshot**

```bash
pytest tests/web_cabinet/ai/test_npv_cull.py tests/web_cabinet/animals/ -v 2>&1 | tail -30
```

Run the live API snapshot one-liner from P1-2 Phase 5 plan.

- [ ] **Step 2: If acceptance breaks, calibrate one of:**

  - mastitis_score weight (1.5 → 1.8 if Малина drops out of cull)
  - days_open_score weight (1.0 per 50 → 1.5 per 50 if open-cow signal too weak)
  - milk_factor sensitivity (0.06/score → 0.08 if Star drifts toward cull)

  No new components — calibrate within existing.

- [ ] **Step 3: Update narrative_md if signals fired more aggressively** — make sure the operator-facing markdown explains the new health components.

- [ ] **Step 4: Commit**

```bash
git commit -m "fix(P1-2c): final calibration after composite expansion

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Phase 6 — Docs + CI gates + execution proof (1 commit)

- [ ] Update `docs/public_interfaces.md` Animal endpoints note to mention "production-grade NPV with Wood-curve, parity-stratified survival, days-open, treatment recurrence, age" instead of just "§3.2.4".
- [ ] Run all 7 CI gates per CLAUDE.md §4.
- [ ] Write `docs/iterations/T34-P1-2c_execution_proof.md` mirroring P1-2 proof template; include before/after API snapshot for both Малина and Звёздочка showing how each new signal contributes.
- [ ] Final commit + push.

---

## Acceptance criteria

- [ ] All Phase 1–4 unit tests pass
- [ ] `_health_burden_signal` returns 7+ component scores (was 5 in P1-2b)
- [ ] `compute_npv_keep` uses parity-stratified survival
- [ ] `_project_monthly_milk_wood` falls back gracefully when data missing
- [ ] Малина (3891) → still `cull`
- [ ] Звёздочка (4821) → still `keep`
- [ ] All 7 CI gates green
- [ ] Honest status: `proven`

## Out of scope

- Multi-lactation projection (we approximate as cyclic 305+60 reset)
- Embryonic/fetal loss modelling
- Heat detection signal from sensor data
- Random-effects per-cow Wood fit (we use fixed-effect curve_fit)
- Frontend UI for the recommendation
