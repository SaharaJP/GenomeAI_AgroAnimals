"""Append demo briefs & insights derived from the freshly seeded alerts.

Runs after `seed_demo_extended.py`. Augments three JSON files so that
manual refresh of /morning-brief, /weekly-brief and /insights surfaces
fresh, varied content on different dates:

  morning_briefs_seeded.json  — append 5 briefs (one per day, last 5 days)
  weekly_briefs_seeded.json   — append 2 briefs (last 2 weeks)
  insights_seeded.json        — append 8 insights tied to real alerts

Idempotent: refuses to add a brief whose brief_id already exists.
"""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "data" / "demo" / "investor_v1"
TODAY = date(2026, 5, 9)
FARM_ID = "demo-farm-v1"


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def _load_alerts() -> list[dict]:
    p = ROOT / "dm_alerts.csv"
    return list(csv.DictReader(open(p))) if p.exists() else []


def _load_decisions() -> list[dict]:
    p = ROOT / "dm_decisions.csv"
    return list(csv.DictReader(open(p))) if p.exists() else []


def _animal_label(animal_id: str, animals_by_id: dict) -> str:
    a = animals_by_id.get(animal_id, {})
    return f"№{animal_id}"


def _load_animals_by_id() -> dict:
    p = ROOT / "dm_animals.csv"
    return {r["animal_id"]: r for r in csv.DictReader(open(p))}


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def make_morning_briefs(alerts: list[dict], animals_by_id: dict) -> list[dict]:
    """Five morning briefs covering 5 most recent days."""
    by_animal = defaultdict(list)
    for al in alerts:
        by_animal[al["animal_id"]].append(al)

    # Sort alerts by created_at desc
    alerts_sorted = sorted(alerts, key=lambda a: a["created_at"], reverse=True)
    n_recurrent = sum(1 for a in alerts if a["alert_type"] == "recurrent_mastitis")
    n_open      = sum(1 for a in alerts if a["alert_type"] == "open_cow_long")
    n_lame      = sum(1 for a in alerts if a["alert_type"] == "lameness")
    n_lowyield  = sum(1 for a in alerts if a["alert_type"] == "low_yield_drop")

    briefs: list[dict] = []
    for day_offset in range(5):
        d = TODAY - timedelta(days=day_offset)
        # Pick 3 alerts whose created_at is on/before this date for "overnight changes"
        relevant = [a for a in alerts_sorted
                    if datetime.fromisoformat(a["created_at"]).date() <= d][:3]

        overnight = []
        for al in relevant[:3]:
            label = _animal_label(al["animal_id"], animals_by_id)
            overnight.append({
                "text": f"{label}: {al['message']} [evidence: {al['alert_id']}]",
                "evidence_id": al["alert_id"],
            })

        actions = []
        # If there's a recurrent_mastitis alert, schedule a vet visit
        rm = next((a for a in relevant if a["alert_type"] == "recurrent_mastitis"), None)
        if rm:
            actions.append({
                "action": f"Осмотр {_animal_label(rm['animal_id'], animals_by_id)}: клиническая оценка рецидивирующего мастита, NPV-анализ",
                "priority": "high", "due": "до 11:00", "role": "vet",
            })
        oc = next((a for a in relevant if a["alert_type"] == "open_cow_long"), None)
        if oc:
            actions.append({
                "action": f"{_animal_label(oc['animal_id'], animals_by_id)}: ресинхронизация (OvSynch) или решение по выбраковке",
                "priority": "medium", "due": "сегодня", "role": "zootech",
            })
        ly = next((a for a in relevant if a["alert_type"] == "low_yield_drop"), None)
        if ly:
            actions.append({
                "action": f"{_animal_label(ly['animal_id'], animals_by_id)}: проверить потребление концентратов, отбор молока на тест",
                "priority": "medium", "due": "до 14:00", "role": "zootech",
            })
        if not actions:
            actions.append({
                "action": "Стандартный обход, измерение BCS у группы 1",
                "priority": "low", "due": "в течение дня", "role": "zootech",
            })

        briefs.append({
            "brief_id":          f"MBRIEF_{d.strftime('%Y%m%d')}",
            "farm_id":           FARM_ID,
            "generated_at_utc":  d.isoformat() + "T03:00:00",
            "date":              d.isoformat(),
            "headline":          (
                f"Активных алертов: {len(alerts_sorted)} (recurrent_mast={n_recurrent}, "
                f"open_cow={n_open}, lameness={n_lame}, low_yield={n_lowyield})"
            ),
            "main_takeaway":     (
                f"За ночь зафиксировано {len(relevant)} новых сигналов. "
                f"Текущий приоритет — {len([a for a in relevant if a['severity'] == 'high'])} "
                f"high-severity случай(ев) требует осмотра ветврачом до полудня. "
                f"Дополнительно открытых коров с длинным DIM: {n_open}; всё это попадает в P2-1 NPV-расчёт автоматически."
            ),
            "overnight_changes": overnight,
            "today_actions":     actions,
            "kpi_snapshot": {
                "total_milk_kg":     round(2900 + (-day_offset) * 12, 0),
                "avg_scc_k":         round(255 + day_offset * 4, 0),
                "active_alerts":     len([a for a in alerts if a["status"] == "new"]),
                "completed_decisions": sum(1 for d_ in alerts if d_["status"] == "acknowledged"),
            },
        })
    return briefs


def make_weekly_briefs(alerts: list[dict], decisions: list[dict],
                       animals_by_id: dict) -> list[dict]:
    """Two weekly briefs covering the past two weeks."""
    briefs = []
    for week_offset in range(2):
        week_end = TODAY - timedelta(days=week_offset * 7)
        week_start = week_end - timedelta(days=6)
        in_week = [a for a in alerts
                   if week_start <= datetime.fromisoformat(a["created_at"]).date() <= week_end]
        decisions_in_week = [d for d in decisions
                             if week_start <= datetime.fromisoformat(d["created_at"]).date() <= week_end]
        briefs.append({
            "brief_id":          f"WBRIEF_{week_end.strftime('%Y%m%d')}",
            "farm_id":           FARM_ID,
            "generated_at_utc":  week_end.isoformat() + "T07:00:00",
            "week_start":        week_start.isoformat(),
            "week_end":          week_end.isoformat(),
            "executive_summary": (
                f"За неделю {week_start} — {week_end}: новых алертов {len(in_week)}, "
                f"принятых решений {len(decisions_in_week)}. "
                f"Доля high-severity {sum(1 for a in in_week if a['severity']=='high')}/{max(1,len(in_week))} "
                f"({(sum(1 for a in in_week if a['severity']=='high') / max(1,len(in_week)) * 100):.0f}%). "
                f"Композитный health-score выявил {sum(1 for a in in_week if a['alert_type']=='recurrent_mastitis')} "
                "случаев рецидивирующего мастита — кандидаты на NPV-cull review."
            ),
            "sections": [
                {
                    "title": "Здоровье стада",
                    "body": f"Зарегистрировано {len(in_week)} алертов, "
                            f"из них {sum(1 for a in in_week if a['alert_type']=='recurrent_mastitis')} рецидивирующих маститов, "
                            f"{sum(1 for a in in_week if a['alert_type']=='lameness')} эпизодов хромоты.",
                },
                {
                    "title": "Воспроизводство",
                    "body": f"Открытых коров с DIM>150: {sum(1 for a in in_week if a['alert_type']=='open_cow_long')}. "
                            "Рекомендация — пакет ресинхронизации для всех с приоритетом 2-я неделя.",
                },
                {
                    "title": "Экономика",
                    "body": "Расчётная маржа на корову — стабильна. "
                            f"Принятые решения cull_recommended: {sum(1 for d in decisions_in_week if d['action']=='cull_recommended')}.",
                },
            ],
            "key_recommendations": [
                {"text": "Провести NPV-review всех recurrent_mastitis кандидатов до конца недели", "priority": "high"},
                {"text": "Запустить OvSynch на всех open_cow_long >180 DIM", "priority": "medium"},
                {"text": "Контроль качества лактации в группе High Production", "priority": "low"},
            ],
        })
    return briefs


def make_insights(alerts: list[dict], animals_by_id: dict) -> list[dict]:
    """Eight insights tied to real alerts."""
    out = []
    seq = 100
    severities = {"recurrent_mastitis": "urgent", "open_cow_long": "high",
                  "lameness": "medium", "low_yield_drop": "medium"}

    for al in alerts[:8]:  # take first 8 for variety
        seq += 1
        sev = severities.get(al["alert_type"], "medium")
        label = _animal_label(al["animal_id"], animals_by_id)
        out.append({
            "insight_id": f"INS_{seq:03d}",
            "type":       al["alert_type"],
            "severity":   sev,
            "date":       al["created_at"][:10],
            "animal_ids": [al["animal_id"]],
            "title":      f"{label}: {al['message'][:60]}",
            "body":       (
                f"Алерт {al['alert_id']} (severity={al['severity']}, "
                f"status={al['status']}). Сигнал интегрирован в композитный "
                "health-score (P1-2c) и в P2-1 knapsack farm-context."
            ),
            "action":     "Открыть карточку животного, проверить рекомендацию NPV",
            "tags":       [al["alert_type"], "auto_generated", "p1_2c_signal"],
        })
    return out


# ---------------------------------------------------------------------------
# Augmenters
# ---------------------------------------------------------------------------

def _augment(json_path: Path, new_items: list[dict], pk_field: str) -> int:
    existing = json.load(open(json_path)) if json_path.exists() else []
    existing_ids = {item.get(pk_field) for item in existing}
    added = [item for item in new_items if item.get(pk_field) not in existing_ids]
    if added:
        merged = list(existing) + added
        json.dump(merged, open(json_path, "w"), indent=2, ensure_ascii=False)
    return len(added)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    alerts = _load_alerts()
    decisions = _load_decisions()
    animals_by_id = _load_animals_by_id()
    print(f"[seed_demo_ai_artefacts] {len(alerts)} alerts, {len(decisions)} decisions, "
          f"{len(animals_by_id)} animals")

    if not alerts:
        print("[seed_demo_ai_artefacts] No alerts — run seed_demo_extended.py first")
        return

    morning = make_morning_briefs(alerts, animals_by_id)
    weekly = make_weekly_briefs(alerts, decisions, animals_by_id)
    insights = make_insights(alerts, animals_by_id)

    n_morning = _augment(ROOT / "morning_briefs_seeded.json", morning, "brief_id")
    n_weekly = _augment(ROOT / "weekly_briefs_seeded.json", weekly, "brief_id")
    n_insights = _augment(ROOT / "insights_seeded.json", insights, "insight_id")

    print(f"[seed_demo_ai_artefacts] morning_briefs_seeded.json: +{n_morning}")
    print(f"[seed_demo_ai_artefacts] weekly_briefs_seeded.json:  +{n_weekly}")
    print(f"[seed_demo_ai_artefacts] insights_seeded.json:       +{n_insights}")
    print("[seed_demo_ai_artefacts] DONE")


if __name__ == "__main__":
    main()
