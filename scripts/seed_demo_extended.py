"""Seed extended demo data for investor_v1 to fill UI gaps.

Generates / backfills tables that the UI surfaces depend on:
  dm_alerts.csv          (new)        — active herd alerts
  dm_decisions.csv       (new)        — decision log
  dm_repro_events.csv    (new)        — reproduction timeline
  dm_economics_daily.csv (new)        — daily P&L
  dm_pen_moves.csv       (new)        — pen relocation history
  dm_milkings_daily.csv  (new)        — derived from milk_yields.json
  dm_testday.csv         (new)        — monthly test-day snapshots
  dm_health_events.csv   (backfill)   — 60 → ~280 animals (~80% coverage)
  dm_treatments.csv      (backfill)   — 60 → ~240 animals (~70% coverage)
  breedings.json         (backfill)   — 159 → ~300 animals (~85% coverage)

Idempotent: respects existing IDs (ON CONFLICT DO NOTHING semantics in csv).
Reproducible: seeded RNG (seed=20260509).
"""
from __future__ import annotations

import csv
import json
import random
import shutil
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data" / "demo" / "investor_v1"
SEED = 20260509
TODAY = date(2026, 5, 9)

rng = random.Random(SEED)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _backup(path: Path) -> None:
    if path.exists():
        bak = path.with_suffix(path.suffix + f".bak_{TODAY.isoformat()}")
        shutil.copy(path, bak)


def _load_animals() -> list[dict]:
    with open(ROOT / "dm_animals.csv") as f:
        return list(csv.DictReader(f))


def _load_lactations() -> list[dict]:
    with open(ROOT / "dm_lactations.csv") as f:
        return list(csv.DictReader(f))


def _load_health_events() -> list[dict]:
    with open(ROOT / "dm_health_events.csv") as f:
        return list(csv.DictReader(f))


def _load_treatments() -> list[dict]:
    with open(ROOT / "dm_treatments.csv") as f:
        return list(csv.DictReader(f))


def _load_breedings() -> list[dict]:
    return json.load(open(ROOT / "breedings.json"))


def _write_csv(path: Path, rows: list[dict], headers: list[str]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in headers})


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def backfill_health_events(animals: list[dict], existing: list[dict]) -> list[dict]:
    """Extend coverage from ~17% to ~80% with plausible events."""
    covered = {row["animal_id"] for row in existing}
    target_coverage = 0.80
    target_n = int(len(animals) * target_coverage)
    needed = max(0, target_n - len(covered))

    # Pick uncovered cows
    uncovered = [a for a in animals if a["animal_id"] not in covered]
    rng.shuffle(uncovered)

    event_types = [
        ("mastitis", ["low", "medium", "high"], [0.5, 0.35, 0.15]),
        ("lameness", ["low", "medium"],         [0.6, 0.4]),
        ("ketosis", ["low", "medium"],          [0.7, 0.3]),
        ("retained_placenta", ["medium"],        [1.0]),
        ("metritis", ["medium", "high"],         [0.7, 0.3]),
        ("milk_fever", ["high"],                 [1.0]),
    ]
    type_weights = [0.42, 0.30, 0.10, 0.08, 0.06, 0.04]

    new_rows: list[dict] = []
    for a in uncovered[:needed]:
        # 1-2 events per newly covered cow
        n_events = rng.choices([1, 2], weights=[0.7, 0.3])[0]
        for i in range(n_events):
            et, severities, sev_weights = rng.choices(event_types, weights=type_weights)[0]
            sev = rng.choices(severities, weights=sev_weights)[0]
            # Spread events over the past 6 months
            days_ago = rng.randint(7, 180)
            ed = TODAY - timedelta(days=days_ago)
            new_rows.append({
                "tenant_id":  "default",
                "event_id":   f"EV_{a['animal_id']}_{et[:4].upper()}_{i+1:02d}",
                "animal_id":  a["animal_id"],
                "event_date": ed.isoformat(),
                "event_type": et,
                "severity":   sev,
                "notes":      "",
            })
    return existing + new_rows


def backfill_treatments(animals: list[dict], existing: list[dict],
                        health_events: list[dict]) -> list[dict]:
    """Each high/medium event generates a treatment (~70% coverage target)."""
    existing_event_ids = {row["reason_event_id"] for row in existing if row.get("reason_event_id")}
    treatment_protocol = {
        "mastitis":          "mastitis_protocol",
        "lameness":          "lameness_protocol",
        "ketosis":           "ketosis_treatment",
        "retained_placenta": "rp_protocol",
        "metritis":          "metritis_protocol",
        "milk_fever":        "calcium_iv",
    }
    duration_days = {
        "mastitis_protocol":   3,
        "lameness_protocol":   2,
        "ketosis_treatment":   5,
        "rp_protocol":         4,
        "metritis_protocol":   5,
        "calcium_iv":          1,
    }
    withdrawal_days = {
        "mastitis_protocol":  5,
        "lameness_protocol":  3,
        "ketosis_treatment":  3,
        "rp_protocol":        4,
        "metritis_protocol":  6,
        "calcium_iv":         1,
    }

    new_rows: list[dict] = []
    for ev in health_events:
        if ev["event_id"] in existing_event_ids:
            continue
        if ev["severity"] == "low":
            continue
        if rng.random() > 0.85:  # 85% of medium/high events get treatments
            continue
        protocol = treatment_protocol.get(ev["event_type"], "supportive_care")
        start = date.fromisoformat(ev["event_date"])
        dur = duration_days.get(protocol, 3)
        wdr = withdrawal_days.get(protocol, 3)
        end = start + timedelta(days=dur)
        new_rows.append({
            "tenant_id":   "default",
            "treatment_id": f"TR_{ev['animal_id']}_{ev['event_type'][:4].upper()}_{ev['event_id'].split('_')[-1]}",
            "animal_id":    ev["animal_id"],
            "start_date":   start.isoformat(),
            "end_date":     end.isoformat(),
            "treatment_type": protocol,
            "reason_event_id": ev["event_id"],
            "withdrawal_end_date": (end + timedelta(days=wdr)).isoformat(),
        })
    return existing + new_rows


def backfill_breedings(animals: list[dict], existing: list[dict],
                       lactations_by_id: dict) -> list[dict]:
    """Extend coverage from ~45% to ~85% with plausible breedings."""
    covered = {row["animal_id"] for row in existing}
    target_coverage = 0.85
    target_n = int(len(animals) * target_coverage)
    needed = max(0, target_n - len(covered))

    uncovered = [a for a in animals if a["animal_id"] not in covered]
    rng.shuffle(uncovered)

    bulls = ["Ильич", "Граф", "Орёл", "Зорро", "Атлас", "Бой", "Витязь", "Каскад"]
    methods = ["AI", "AI", "AI", "natural"]  # 75% AI

    new_rows: list[dict] = list(existing)
    for a in uncovered[:needed]:
        lact = lactations_by_id.get(a["animal_id"])
        if not lact:
            continue
        try:
            calving = date.fromisoformat(lact["calving_date"][:10])
        except Exception:
            continue
        # First insemination 60-90 days after calving
        bd = calving + timedelta(days=rng.randint(60, 130))
        if bd > TODAY:
            continue
        method = rng.choice(methods)
        result = rng.choices(["pregnant", "open", "open"], weights=[0.55, 0.25, 0.20])[0]
        new_rows.append({
            "breeding_id":    f"BR_{a['animal_id']}_01",
            "animal_id":      a["animal_id"],
            "date":           bd.isoformat(),
            "method":         method,
            "bull_name":      rng.choice(bulls) if method == "AI" else "stockyard_bull_01",
            "heat_detected":  rng.random() > 0.05,
            "result":         result,
            "preg_check_date": (bd + timedelta(days=35)).isoformat(),
        })
    return new_rows


def gen_repro_events(animals: list[dict], lactations_by_id: dict,
                     breedings: list[dict]) -> list[dict]:
    """Build reproduction timeline: heat -> insemination -> preg_check -> calving -> dryoff."""
    breedings_by_id: dict[str, list] = defaultdict(list)
    for br in breedings:
        breedings_by_id[br["animal_id"]].append(br)

    rows: list[dict] = []
    for a in animals:
        aid = a["animal_id"]
        lact = lactations_by_id.get(aid)
        if not lact:
            continue
        try:
            calving = date.fromisoformat(lact["calving_date"][:10])
            dryoff = date.fromisoformat(lact["dryoff_date"][:10]) if lact.get("dryoff_date") else None
        except Exception:
            continue

        # Calving event
        rows.append({
            "tenant_id":  "default",
            "event_id":   f"RE_{aid}_CALV_{lact['lactation_no']}",
            "animal_id":  aid,
            "event_date": calving.isoformat(),
            "event_type": "calving",
            "result":     rng.choice(["normal", "normal", "normal", "assisted"]),
            "notes":      "",
        })

        # Heat events (one per breeding)
        for br in breedings_by_id.get(aid, []):
            try:
                bd = date.fromisoformat(br["date"][:10])
            except Exception:
                continue
            heat_date = bd - timedelta(days=1)
            rows.append({
                "tenant_id":  "default",
                "event_id":   f"RE_{aid}_HEAT_{bd.isoformat().replace('-', '')}",
                "animal_id":  aid,
                "event_date": heat_date.isoformat(),
                "event_type": "heat",
                "result":     "detected" if br.get("heat_detected") else "missed",
                "notes":      "",
            })
            rows.append({
                "tenant_id":  "default",
                "event_id":   f"RE_{aid}_INS_{bd.isoformat().replace('-', '')}",
                "animal_id":  aid,
                "event_date": bd.isoformat(),
                "event_type": "insemination",
                "result":     br.get("result", "open"),
                "notes":      f"method={br.get('method')} bull={br.get('bull_name')}",
            })
            if br.get("preg_check_date"):
                rows.append({
                    "tenant_id":  "default",
                    "event_id":   f"RE_{aid}_PREGCK_{bd.isoformat().replace('-', '')}",
                    "animal_id":  aid,
                    "event_date": br["preg_check_date"],
                    "event_type": "preg_check",
                    "result":     br.get("result", "open"),
                    "notes":      "",
                })

        # Dryoff
        if dryoff and dryoff <= TODAY:
            rows.append({
                "tenant_id":  "default",
                "event_id":   f"RE_{aid}_DRY_{lact['lactation_no']}",
                "animal_id":  aid,
                "event_date": dryoff.isoformat(),
                "event_type": "dryoff",
                "result":     "completed",
                "notes":      "",
            })

    return rows


def gen_alerts(animals: list[dict], lactations_by_id: dict,
               health_events: list[dict], breedings: list[dict]) -> list[dict]:
    """Synthesize active alerts from underlying signals."""
    he_by_animal: dict[str, list] = defaultdict(list)
    for ev in health_events:
        he_by_animal[ev["animal_id"]].append(ev)
    br_by_animal: dict[str, list] = defaultdict(list)
    for br in breedings:
        br_by_animal[br["animal_id"]].append(br)

    alert_id_seq = 1
    rows: list[dict] = []
    for a in animals:
        aid = a["animal_id"]
        lact = lactations_by_id.get(aid)
        if not lact:
            continue
        try:
            calving = date.fromisoformat(lact["calving_date"][:10])
        except Exception:
            calving = None

        # Recurrent mastitis alert
        recent_mast_high = [
            ev for ev in he_by_animal.get(aid, [])
            if ev["event_type"] == "mastitis" and ev["severity"] == "high"
            and (TODAY - date.fromisoformat(ev["event_date"])).days <= 90
        ]
        if len(recent_mast_high) >= 2:
            rows.append({
                "tenant_id":   "default",
                "alert_id":    f"AL_{alert_id_seq:05d}",
                "animal_id":   aid,
                "alert_type":  "recurrent_mastitis",
                "severity":    "high",
                "status":      rng.choices(["new", "acknowledged"], weights=[0.6, 0.4])[0],
                "dedupe_key":  f"recurrent_mastitis:{aid}",
                "created_at":  (TODAY - timedelta(days=rng.randint(1, 14))).isoformat(),
                "resolved_at": "",
                "message":     f"≥2 эпизода клинического мастита за 90 дней",
            })
            alert_id_seq += 1

        # Open cow (long days-open)
        if calving and (TODAY - calving).days > 150:
            recent_brs = [b for b in br_by_animal.get(aid, [])
                          if date.fromisoformat(b["date"][:10]) >= calving]
            if not any(b.get("result") == "pregnant" for b in recent_brs):
                rows.append({
                    "tenant_id":   "default",
                    "alert_id":    f"AL_{alert_id_seq:05d}",
                    "animal_id":   aid,
                    "alert_type":  "open_cow_long",
                    "severity":    "medium",
                    "status":      rng.choices(["new", "acknowledged"], weights=[0.5, 0.5])[0],
                    "dedupe_key":  f"open_cow:{aid}",
                    "created_at":  (TODAY - timedelta(days=rng.randint(1, 7))).isoformat(),
                    "resolved_at": "",
                    "message":     f"DIM={(TODAY-calving).days}, нет подтверждённой стельности",
                })
                alert_id_seq += 1

        # Lameness flag
        recent_lame = [ev for ev in he_by_animal.get(aid, []) if ev["event_type"] == "lameness"
                       and (TODAY - date.fromisoformat(ev["event_date"])).days <= 30]
        if recent_lame and rng.random() < 0.7:
            rows.append({
                "tenant_id":   "default",
                "alert_id":    f"AL_{alert_id_seq:05d}",
                "animal_id":   aid,
                "alert_type":  "lameness",
                "severity":    "medium",
                "status":      "new",
                "dedupe_key":  f"lameness:{aid}",
                "created_at":  (TODAY - timedelta(days=rng.randint(1, 5))).isoformat(),
                "resolved_at": "",
                "message":     "Зарегистрирован эпизод хромоты, требуется осмотр",
            })
            alert_id_seq += 1

        # Low yield (random ~12% of cows)
        if rng.random() < 0.12:
            rows.append({
                "tenant_id":   "default",
                "alert_id":    f"AL_{alert_id_seq:05d}",
                "animal_id":   aid,
                "alert_type":  "low_yield_drop",
                "severity":    rng.choice(["low", "medium"]),
                "status":      "new",
                "dedupe_key":  f"low_yield:{aid}",
                "created_at":  (TODAY - timedelta(days=rng.randint(1, 10))).isoformat(),
                "resolved_at": "",
                "message":     "Падение надоя >15% за 7 дней относительно baseline",
            })
            alert_id_seq += 1

    return rows


def gen_decisions(animals: list[dict], alerts: list[dict]) -> list[dict]:
    """Decisions tied to alerts (acknowledged + resolved actions)."""
    rows: list[dict] = []
    decision_seq = 1
    actions_for_type = {
        "recurrent_mastitis": ["cull_recommended", "treat_protocol_extended", "deferred"],
        "open_cow_long":      ["resync_protocol", "cull_recommended", "deferred"],
        "lameness":           ["hoof_trim_scheduled", "treat_protocol", "deferred"],
        "low_yield_drop":     ["nutritional_review", "deferred", "monitor"],
    }
    for al in alerts:
        if al["status"] not in ("acknowledged",) and rng.random() > 0.40:
            continue
        action = rng.choice(actions_for_type.get(al["alert_type"], ["monitor"]))
        rows.append({
            "tenant_id":     "default",
            "decision_id":   f"DC_{decision_seq:05d}",
            "animal_id":     al["animal_id"],
            "decision_type": al["alert_type"],
            "action":        action,
            "reason_code":   "alert_response",
            "recommendation_id": al["alert_id"],
            "user_id":       "9000002",
            "created_at":    al["created_at"],
            "metadata_json": json.dumps({"alert_id": al["alert_id"], "severity": al["severity"]}, ensure_ascii=False),
        })
        decision_seq += 1

    return rows


def gen_economics_daily(farm_id: str, days: int = 365) -> list[dict]:
    """Daily P&L aggregate for the herd."""
    rows: list[dict] = []
    for i in range(days):
        d = TODAY - timedelta(days=days - i - 1)
        # Seasonal swing ±8% around base
        season = 1.0 + 0.08 * ((d.month - 6) / 6.0)
        n_lactating = rng.randint(285, 315)
        avg_kg = rng.uniform(24.0, 30.0) * season
        total_milk = round(n_lactating * avg_kg, 1)
        milk_revenue = round(total_milk * 30.0, 0)
        feed_cost = round(total_milk * 12.0, 0)
        vet_cost = round(rng.uniform(800, 4500), 0)
        rows.append({
            "tenant_id": "default",
            "farm_id": farm_id,
            "date": d.isoformat(),
            "n_lactating": n_lactating,
            "avg_milk_kg_per_cow": round(avg_kg, 1),
            "total_milk_kg": total_milk,
            "milk_revenue_rub": milk_revenue,
            "feed_cost_rub":   feed_cost,
            "vet_cost_rub":    vet_cost,
            "gross_margin_rub": milk_revenue - feed_cost - vet_cost,
        })
    return rows


def gen_milkings_daily() -> list[dict]:
    """Derive AM/PM split from milk_yields.json."""
    rows: list[dict] = []
    for r in json.load(open(ROOT / "milk_yields.json")):
        total = float(r["milk_kg"])
        am_share = rng.uniform(0.48, 0.55)
        am = round(total * am_share, 2)
        pm = round(total - am, 2)
        rows.append({
            "tenant_id": "default",
            "animal_id": r["animal_id"],
            "date":      r["date"],
            "am_kg":     am,
            "pm_kg":     pm,
            "total_kg":  round(total, 2),
            "scc_cells_ml": r.get("scc_cells_ml", ""),
        })
    return rows


def gen_pen_moves(animals: list[dict], lactations_by_id: dict) -> list[dict]:
    """Each cow has 2-3 pen moves over the year."""
    pens = ["P_FRESH", "P_HIGH_PRO", "P_MID_PRO", "P_LATE_LACT", "P_DRY_FAR_OFF",
            "P_DRY_CLOSE_UP", "P_HOSPITAL", "P_HEIFER"]
    rows: list[dict] = []
    seq = 1
    for a in animals:
        aid = a["animal_id"]
        lact = lactations_by_id.get(aid)
        if not lact:
            continue
        try:
            calving = date.fromisoformat(lact["calving_date"][:10])
        except Exception:
            continue
        # Move into fresh pen at calving
        rows.append({
            "tenant_id": "default",
            "move_id":   f"PM_{seq:06d}",
            "animal_id": aid,
            "move_date": calving.isoformat(),
            "from_pen":  "P_DRY_CLOSE_UP",
            "to_pen":    "P_FRESH",
            "reason":    "post_calving",
        })
        seq += 1
        # Move to high production after fresh period
        rows.append({
            "tenant_id": "default",
            "move_id":   f"PM_{seq:06d}",
            "animal_id": aid,
            "move_date": (calving + timedelta(days=21)).isoformat(),
            "from_pen":  "P_FRESH",
            "to_pen":    "P_HIGH_PRO",
            "reason":    "lactation_curve_progression",
        })
        seq += 1
        # Maybe a third move (to mid/late) if DIM allows
        try:
            dim = int(float(lact.get("days_in_milk") or 0))
        except Exception:
            dim = 0
        if dim > 150:
            rows.append({
                "tenant_id": "default",
                "move_id":   f"PM_{seq:06d}",
                "animal_id": aid,
                "move_date": (calving + timedelta(days=120)).isoformat(),
                "from_pen":  "P_HIGH_PRO",
                "to_pen":    "P_MID_PRO",
                "reason":    "yield_decline",
            })
            seq += 1
    return rows


def gen_testday(animals: list[dict], lactations_by_id: dict) -> list[dict]:
    """Monthly test-day: milk_kg + fat + protein + scc per cow."""
    rows: list[dict] = []
    # Test-days on 5th of each month, last 6 months
    test_days = []
    for m_back in range(6):
        td = TODAY.replace(day=5)
        for _ in range(m_back):
            # Step back by approx 30 days, snap to 5th of prior month
            td = (td.replace(day=1) - timedelta(days=1)).replace(day=5)
        test_days.append(td)
    for a in animals:
        aid = a["animal_id"]
        lact = lactations_by_id.get(aid)
        if not lact:
            continue
        try:
            milk_305 = float(lact.get("milk_305d_kg") or 8500)
            fat = float(lact.get("fat_pct") or 3.8)
            prot = float(lact.get("protein_pct") or 3.2)
        except Exception:
            milk_305 = 8500
            fat = 3.8
            prot = 3.2
        peak_daily = milk_305 / 305.0 * 1.4
        for td in test_days:
            # Rough variation ±20%
            milk = round(peak_daily * rng.uniform(0.55, 1.05), 2)
            rows.append({
                "tenant_id":      "default",
                "animal_id":      aid,
                "test_date":      td.isoformat(),
                "milk_kg":        milk,
                "fat_pct":        round(fat + rng.uniform(-0.3, 0.3), 2),
                "protein_pct":    round(prot + rng.uniform(-0.2, 0.2), 2),
                "scc_cells_ml":   max(80_000, int(rng.gauss(280_000, 180_000))),
            })
    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    animals = _load_animals()
    farm_id = animals[0]["farm_id"]
    print(f"[seed_demo_extended] Loaded {len(animals)} animals (farm={farm_id})")

    lactations = _load_lactations()
    lactations_by_id = {l["animal_id"]: l for l in lactations}

    # ---- 1. Backfill health_events ----
    he_existing = _load_health_events()
    he_full = backfill_health_events(animals, he_existing)
    _backup(ROOT / "dm_health_events.csv")
    _write_csv(
        ROOT / "dm_health_events.csv",
        he_full,
        ["tenant_id", "event_id", "animal_id", "event_date", "event_type", "severity", "notes"],
    )
    print(f"[seed_demo_extended] dm_health_events.csv: {len(he_existing)} → {len(he_full)} rows")

    # ---- 2. Backfill treatments ----
    tr_existing = _load_treatments()
    tr_full = backfill_treatments(animals, tr_existing, he_full)
    _backup(ROOT / "dm_treatments.csv")
    _write_csv(
        ROOT / "dm_treatments.csv",
        tr_full,
        ["tenant_id", "treatment_id", "animal_id", "start_date", "end_date",
         "treatment_type", "reason_event_id", "withdrawal_end_date"],
    )
    print(f"[seed_demo_extended] dm_treatments.csv: {len(tr_existing)} → {len(tr_full)} rows")

    # ---- 3. Backfill breedings ----
    br_existing = _load_breedings()
    br_full = backfill_breedings(animals, br_existing, lactations_by_id)
    _backup(ROOT / "breedings.json")
    json.dump(br_full, open(ROOT / "breedings.json", "w"), indent=2, ensure_ascii=False)
    print(f"[seed_demo_extended] breedings.json: {len(br_existing)} → {len(br_full)} rows")

    # ---- 4. New: dm_repro_events.csv ----
    repro_rows = gen_repro_events(animals, lactations_by_id, br_full)
    _write_csv(
        ROOT / "dm_repro_events.csv",
        repro_rows,
        ["tenant_id", "event_id", "animal_id", "event_date", "event_type", "result", "notes"],
    )
    print(f"[seed_demo_extended] dm_repro_events.csv: NEW {len(repro_rows)} rows")

    # ---- 5. New: dm_alerts.csv ----
    alert_rows = gen_alerts(animals, lactations_by_id, he_full, br_full)
    _write_csv(
        ROOT / "dm_alerts.csv",
        alert_rows,
        ["tenant_id", "alert_id", "animal_id", "alert_type", "severity", "status",
         "dedupe_key", "created_at", "resolved_at", "message"],
    )
    print(f"[seed_demo_extended] dm_alerts.csv: NEW {len(alert_rows)} rows")

    # ---- 6. New: dm_decisions.csv ----
    decision_rows = gen_decisions(animals, alert_rows)
    _write_csv(
        ROOT / "dm_decisions.csv",
        decision_rows,
        ["tenant_id", "decision_id", "animal_id", "decision_type", "action", "reason_code",
         "recommendation_id", "user_id", "created_at", "metadata_json"],
    )
    print(f"[seed_demo_extended] dm_decisions.csv: NEW {len(decision_rows)} rows")

    # ---- 7. New: dm_economics_daily.csv ----
    econ_rows = gen_economics_daily(farm_id, days=365)
    _write_csv(
        ROOT / "dm_economics_daily.csv",
        econ_rows,
        ["tenant_id", "farm_id", "date", "n_lactating", "avg_milk_kg_per_cow", "total_milk_kg",
         "milk_revenue_rub", "feed_cost_rub", "vet_cost_rub", "gross_margin_rub"],
    )
    print(f"[seed_demo_extended] dm_economics_daily.csv: NEW {len(econ_rows)} rows")

    # ---- 8. New: dm_milkings_daily.csv ----
    milk_rows = gen_milkings_daily()
    _write_csv(
        ROOT / "dm_milkings_daily.csv",
        milk_rows,
        ["tenant_id", "animal_id", "date", "am_kg", "pm_kg", "total_kg", "scc_cells_ml"],
    )
    print(f"[seed_demo_extended] dm_milkings_daily.csv: NEW {len(milk_rows)} rows")

    # ---- 9. New: dm_pen_moves.csv ----
    pen_rows = gen_pen_moves(animals, lactations_by_id)
    _write_csv(
        ROOT / "dm_pen_moves.csv",
        pen_rows,
        ["tenant_id", "move_id", "animal_id", "move_date", "from_pen", "to_pen", "reason"],
    )
    print(f"[seed_demo_extended] dm_pen_moves.csv: NEW {len(pen_rows)} rows")

    # ---- 10. New: dm_testday.csv ----
    testday_rows = gen_testday(animals, lactations_by_id)
    _write_csv(
        ROOT / "dm_testday.csv",
        testday_rows,
        ["tenant_id", "animal_id", "test_date", "milk_kg", "fat_pct", "protein_pct", "scc_cells_ml"],
    )
    print(f"[seed_demo_extended] dm_testday.csv: NEW {len(testday_rows)} rows")

    print("[seed_demo_extended] DONE.")


if __name__ == "__main__":
    main()
