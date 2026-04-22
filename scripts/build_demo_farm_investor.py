#!/usr/bin/env python3
"""
Build investor-grade demo farm dataset v2: 350 active dairy cows, 6-month history.

Usage:
    python scripts/build_demo_farm_investor.py --mode connecterra
    python scripts/build_demo_farm_investor.py --mode connecterra --with-ai-seeds
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# ─── constants ────────────────────────────────────────────────────────────────
SEED = 42
TODAY = date(2026, 4, 21)
HISTORY_START = TODAY - timedelta(days=180)  # 2025-10-21

FARM_ID   = "INV_FARM_001"
FARM_NAME = "Демо-ферма"
HOLDING   = "Агрохолдинг Заря"
ADDRESS   = "с. Васильково"
DIRECTOR  = "Андрей Жиров"
TENANT_ID = "default"

COW_NAMES = [
    "Бурёнка", "Зорька", "Ночка", "Ласточка", "Звёздочка",
    "Милка", "Умница", "Красавица", "Белянка", "Пеструха",
    "Роза", "Майка", "Весна", "Малина", "Чернушка",
    "Снежинка", "Рябинка", "Калинка", "Любава", "Забава",
    "Марта", "Мальвина", "Сирень", "Василёк", "Берёзка",
    "Ивушка", "Ромашка", "Лютик", "Незабудка", "Голубка",
    "Зая", "Кнопка", "Линда", "Лада", "Макара",
    "Нежность", "Облачко", "Полина", "Радуга", "Салфетка",
    "Туча", "Удача", "Фиалка", "Хатыль", "Цветочек",
    "Шалунья", "Щеголиха", "Эличка", "Юла", "Яна",
]

BULL_NAMES = [
    "Атаман", "Буран", "Вихрь", "Гром", "Дунай",
    "Ермак", "Жигули", "Зевс", "Ильич", "Кавказ",
]

PENS = [
    {"pen_id": "PEN_FRESH_1",  "pen_name": "Свежее стадо",    "pen_type": "fresh",     "capacity": 55},
    {"pen_id": "PEN_LACT_1",   "pen_name": "Лактирующие I",   "pen_type": "lactating", "capacity": 130},
    {"pen_id": "PEN_LACT_2",   "pen_name": "Лактирующие II",  "pen_type": "lactating", "capacity": 120},
    {"pen_id": "PEN_LACT_3",   "pen_name": "Лактирующие III", "pen_type": "lactating", "capacity": 100},
    {"pen_id": "PEN_DRY_1",    "pen_name": "Сухостой",        "pen_type": "dry",       "capacity": 60},
    {"pen_id": "PEN_HOSPITAL", "pen_name": "Лазарет",         "pen_type": "hospital",  "capacity": 20},
]

DRUG_PROTOCOLS: dict[str, tuple[str, str, int]] = {
    "mastitis":   ("Цефквином",       "intramammary", 3),
    "mastitis_alt": ("Пенициллин",    "intramammary", 5),
    "lameness":   ("Мелоксикам",      "subcutaneous", 3),
    "ketosis":    ("Бутафосфан+В12",  "intravenous",  0),
    "metritis":   ("Окситетрациклин", "intrauterine", 7),
}

# IDs reserved for seeded cows
SEEDED_IDS = {3142, 3891, 4821}


# ─── helpers ──────────────────────────────────────────────────────────────────

def _ts(d: date, hour: int = 8) -> str:
    return datetime(d.year, d.month, d.day, hour, 0, tzinfo=timezone.utc).isoformat()


def wood_milk(dim: int, peak_kg: float, peak_dim: int = 65) -> float:
    if dim <= 0:
        return 0.0
    if dim <= peak_dim:
        return peak_kg * 0.55 + peak_kg * 0.45 * (dim / peak_dim)
    return max(6.0, peak_kg * math.exp(-0.0022 * (dim - peak_dim)))


def cow_display_name(idx: int) -> str:
    base = COW_NAMES[idx % len(COW_NAMES)]
    suffix = idx // len(COW_NAMES)
    return f"{base}-{suffix}" if suffix > 0 else base


def pen_for_cow(dim: int, is_dry: bool, group: int = 1) -> str:
    if is_dry or dim <= 0:
        return "PEN_DRY_1"
    if dim <= 30:
        return "PEN_FRESH_1"
    if group == 3:
        return "PEN_LACT_3"
    if dim <= 160:
        return "PEN_LACT_1"
    return "PEN_LACT_2"


def _milk_rec(cow_id: str, d: date, milk_kg: float, fat: float, prot: float, scc: int) -> dict:
    return {
        "record_id":    f"MY_{cow_id}_{d.isoformat().replace('-', '')}",
        "animal_id":    cow_id,
        "date":         d.isoformat(),
        "milk_kg":      round(max(0.0, milk_kg), 1),
        "fat_pct":      round(fat, 2),
        "protein_pct":  round(prot, 2),
        "scc_cells_ml": int(max(40000, scc)),
    }


# ─── seeded cow builders ───────────────────────────────────────────────────────

def _build_zvezdochka(events: list, treatments: list, milk_yields: list) -> dict:
    """Акт 2: Звёздочка (ID 4821), 3-я лактация, 156 DIM."""
    aid    = "4821"
    dim    = 156
    calving = TODAY - timedelta(days=dim)   # 2025-11-16
    peak   = 37.0

    day_m42 = TODAY - timedelta(days=42)   # 2026-03-10 mastitis onset
    day_m38 = TODAY - timedelta(days=38)   # 2026-03-14 pen move
    day_m34 = TODAY - timedelta(days=34)   # 2026-03-18 withdrawal ends
    day_m28 = TODAY - timedelta(days=28)   # 2026-03-24 yield drop

    rng = random.Random(SEED ^ 4821)
    for i in range(180):
        d = HISTORY_START + timedelta(days=i)
        cur_dim = (d - calving).days
        if cur_dim <= 0:
            continue
        base = wood_milk(cur_dim, peak)
        if day_m38 <= d < day_m28:
            base *= 0.86
        elif d >= day_m28:
            base = 28.0
        scc = 160000
        if day_m42 - timedelta(days=3) <= d < day_m38:
            scc = 420000 + rng.randint(-30000, 80000)
        elif day_m38 <= d < day_m28:
            scc = 280000 + rng.randint(-20000, 40000)
        elif d >= day_m28:
            scc = 200000 + rng.randint(-20000, 30000)
        milk_yields.append(_milk_rec(
            aid, d,
            base + rng.gauss(0, 0.3),
            3.8 + rng.gauss(0, 0.12),
            3.2 + rng.gauss(0, 0.08),
            scc,
        ))

    ev_mast = f"EV_{aid}_MAST_01"
    events.append({
        "event_id":   ev_mast,
        "animal_id":  aid,
        "event_type": "mastitis",
        "event_date": _ts(day_m42),
        "severity":   "medium",
        "details": {
            "quarter": "rear_left", "scc_before": 230000,
            "scc_at_detection": 450000, "conductivity": "abnormal",
        },
        "reporter":    "demo_vet",
        "evidence_ids": [f"SCC_{aid}_{day_m42.isoformat()}"],
    })
    events.append({
        "event_id":   f"EV_{aid}_PMOV_01",
        "animal_id":  aid,
        "event_type": "pen_move",
        "event_date": _ts(day_m38, hour=10),
        "severity":   "info",
        "details": {
            "from_pen": "PEN_LACT_1", "to_pen": "PEN_LACT_3",
            "reason": "post_treatment_social_stress", "intake_drop_pct": 14,
        },
        "reporter": "demo_zootech", "evidence_ids": [],
    })
    treatments.append({
        "treatment_id":       f"TR_{aid}_MAST_01",
        "animal_id":          aid,
        "start_date":         day_m42.isoformat(),
        "end_date":           (day_m38 - timedelta(days=1)).isoformat(),
        "drug_name":          "Цефквином",
        "drug_route":         "intramammary",
        "dose_ml":            10,
        "frequency":          "bid",
        "withdrawal_end_date": day_m34.isoformat(),
        "reason_event_id":    ev_mast,
        "prescribed_by":      "demo_vet",
        "executed_by":        "demo_operator",
    })

    return {
        "animal_id": aid, "name": "Звёздочка", "farm_id": FARM_ID,
        "tenant_id": TENANT_ID, "sex": "F", "breed": "Holstein",
        "birth_date": (calving - timedelta(days=730 + 2 * 380)).isoformat(),
        "status": "active", "lactation_no": 3, "calving_date": calving.isoformat(),
        "dim": dim, "current_pen_id": "PEN_LACT_3",
        "milk_305d_kg": 10200, "peak_milk_kg": peak, "current_milk_kg": 28.0,
        "tags": ["act2_ai_copilot", "mastitis_history", "yield_drop"],
    }


def _build_malina(events: list, treatments: list, milk_yields: list) -> dict:
    """Акт 3: Малина (ID 3891), 3-я лактация, 285 DIM, выбраковка."""
    aid    = "3891"
    dim    = 285
    calving = TODAY - timedelta(days=dim)   # 2025-07-10
    peak   = 28.0

    day_m60 = TODAY - timedelta(days=60)
    day_m30 = TODAY - timedelta(days=30)

    rng = random.Random(SEED ^ 3891)
    for i in range(180):
        d = HISTORY_START + timedelta(days=i)
        cur_dim = (d - calving).days
        if cur_dim <= 0 or cur_dim > 305:
            continue
        base = wood_milk(cur_dim, peak)
        if day_m60 <= d < day_m60 + timedelta(days=7):
            base *= 0.70
        elif day_m30 <= d < day_m30 + timedelta(days=5):
            base *= 0.65
        scc = 180000
        if day_m60 - timedelta(days=2) <= d < day_m60 + timedelta(days=10):
            scc = 620000 + rng.randint(-50000, 100000)
        elif day_m30 - timedelta(days=2) <= d < day_m30 + timedelta(days=8):
            scc = 760000 + rng.randint(-50000, 120000)
        milk_yields.append(_milk_rec(
            aid, d,
            base + rng.gauss(0, 0.4),
            3.9 + rng.gauss(0, 0.15),
            3.3 + rng.gauss(0, 0.09),
            scc,
        ))

    for ep, (ev_d, scc_val, drug) in enumerate([
        (day_m60, 680000, "mastitis"),
        (day_m30, 800000, "mastitis_alt"),
    ], start=1):
        ev_id = f"EV_{aid}_MAST_0{ep}"
        events.append({
            "event_id": ev_id, "animal_id": aid, "event_type": "mastitis",
            "event_date": _ts(ev_d), "severity": "high",
            "details": {"scc": scc_val, "quarter": "rear_right",
                        "conductivity": "abnormal", "episode": ep,
                        "recurrence": ep > 1},
            "reporter": "demo_vet",
            "evidence_ids": [f"SCC_{aid}_{ev_d.isoformat()}"],
        })
        dname, route, wd = DRUG_PROTOCOLS[drug]
        dur = 4
        treatments.append({
            "treatment_id":       f"TR_{aid}_MAST_0{ep}",
            "animal_id":          aid,
            "start_date":         ev_d.isoformat(),
            "end_date":           (ev_d + timedelta(days=dur)).isoformat(),
            "drug_name":          dname,
            "drug_route":         route,
            "dose_ml":            10,
            "frequency":          "bid",
            "withdrawal_end_date": (ev_d + timedelta(days=dur + wd)).isoformat(),
            "reason_event_id":    ev_id,
            "prescribed_by":      "demo_vet",
            "executed_by":        "demo_operator",
        })

    return {
        "animal_id": aid, "name": "Малина", "farm_id": FARM_ID,
        "tenant_id": TENANT_ID, "sex": "F", "breed": "Holstein",
        "birth_date": (calving - timedelta(days=730 + 2 * 380)).isoformat(),
        "status": "active", "lactation_no": 3, "calving_date": calving.isoformat(),
        "dim": dim, "current_pen_id": "PEN_LACT_2",
        "milk_305d_kg": 8800, "peak_milk_kg": peak, "current_milk_kg": 14.5,
        "days_open": 145, "npv_30d_usd": -180, "culling_score": 82,
        "culling_recommendation": "SELL",
        "tags": ["act3_culling", "mastitis_recurrence", "open_cow", "negative_npv"],
    }


def _build_nochka(events: list, treatments: list, milk_yields: list) -> dict:
    """Акт 4: Ночка (ID 3142), 2-я лактация, 45 DIM, нет открытого лечения."""
    aid    = "3142"
    dim    = 45
    calving = TODAY - timedelta(days=dim)   # 2026-03-07
    peak   = 33.0

    rng = random.Random(SEED ^ 3142)
    for i in range(180):
        d = HISTORY_START + timedelta(days=i)
        cur_dim = (d - calving).days
        if cur_dim <= 0:
            continue
        base = wood_milk(cur_dim, peak)
        scc  = 160000
        if cur_dim >= dim - 4:
            base *= 0.93
            scc  = 430000 + rng.randint(-30000, 60000)
        milk_yields.append(_milk_rec(
            aid, d,
            base + rng.gauss(0, 0.4),
            3.85 + rng.gauss(0, 0.12),
            3.15 + rng.gauss(0, 0.08),
            scc,
        ))

    for offset, score in [(3, 78), (2, 72), (1, 65)]:
        events.append({
            "event_id":   f"EV_{aid}_ACT_{offset}",
            "animal_id":  aid,
            "event_type": "activity_alert",
            "event_date": _ts(TODAY - timedelta(days=offset), hour=6),
            "severity":   "warn",
            "details": {
                "activity_score": score, "baseline": 91, "trend": "declining_3d",
            },
            "reporter": "system", "evidence_ids": [],
        })
    events.append({
        "event_id":   f"EV_{aid}_SCC_01",
        "animal_id":  aid,
        "event_type": "scc_alert",
        "event_date": _ts(TODAY - timedelta(days=1), hour=7),
        "severity":   "high",
        "details": {
            "scc_cells_ml": 450000, "conductivity": "abnormal",
            "quarter": "front_right", "no_open_treatment": True,
        },
        "reporter": "system", "evidence_ids": [],
    })

    return {
        "animal_id": aid, "name": "Ночка", "farm_id": FARM_ID,
        "tenant_id": TENANT_ID, "sex": "F", "breed": "Holstein",
        "birth_date": (calving - timedelta(days=730 + 380)).isoformat(),
        "status": "active", "lactation_no": 2, "calving_date": calving.isoformat(),
        "dim": dim, "current_pen_id": "PEN_FRESH_1",
        "milk_305d_kg": 9100, "peak_milk_kg": peak, "current_milk_kg": 30.7,
        "current_activity_score": 65, "current_scc": 450000,
        "tags": ["act4_vet_record", "scc_alert", "activity_drop", "no_open_treatment"],
    }


# ─── seeded briefs / insights / timeline ──────────────────────────────────────

def _build_insights(with_ai_seeds: bool) -> list:
    today_s = TODAY.isoformat()
    return [
        {
            "insight_id": "INS_001", "type": "health_alert", "severity": "urgent",
            "date": today_s, "animal_ids": ["3142"],
            "title": "Ночка: признаки мастита без назначенного лечения",
            "body": (
                "Активность снизилась на 29% за 3 дня. СКК 450k, "
                "проводимость аномальная. Открытых протоколов лечения нет."
            ),
            "action": "Открыть карточку Ночки и назначить протокол мастита",
            "tags": ["act4", "mastitis_suspect", "no_treatment"],
        },
        {
            "insight_id": "INS_002", "type": "yield_drop_analysis", "severity": "high",
            "date": today_s, "animal_ids": ["4821"],
            "title": "Звёздочка: удой снизился на 22% после мастита и переводa",
            "body": (
                "3-я лактация, 156 DIM. Мастит выявлен -42 дня назад. "
                "Лечение Цефквином завершено. Перевод в группу 3 вызвал "
                "падение DMI на 14%, удой удерживается 28 кг/день (-22%)."
            ),
            "action": "Оценить возможность возврата в группу 1 через 14 дней",
            "tags": ["act2", "yield_drop", "mastitis_history"],
        },
        {
            "insight_id": "INS_003", "type": "culling_recommendation", "severity": "high",
            "date": today_s, "animal_ids": ["3891"],
            "title": "Малина: рекомендация — выбраковка",
            "body": (
                "285 DIM, 3-я лактация. 2 эпизода мастита за 60 дней. "
                "Open 145 дней. NPV последних 30 дней: -$180. "
                "Индекс выбраковки: 82/100."
            ),
            "action": "Принять решение о выбраковке или консервативном лечении",
            "tags": ["act3", "culling", "negative_npv"],
        },
        {
            "insight_id": "INS_004", "type": "pregnancy_rate", "severity": "info",
            "date": today_s, "animal_ids": [],
            "title": "Индекс стельности 21d: 24% — уровень бенчмарка",
            "body": "Pregnancy Rate за последние 21 день: 24%. Целевой показатель: ≥22%. +2pp к прошлому месяцу.",
            "action": "Поддерживать текущий протокол синхронизации",
            "tags": ["act1", "kpi", "repro"],
        },
        {
            "insight_id": "INS_005", "type": "scc_trend", "severity": "warn",
            "date": today_s, "animal_ids": [],
            "title": "СКК в группе Лактирующие III растёт второй месяц",
            "body": "Среднее СКК PEN_LACT_3 выросло с 185k до 247k за 45 дней. 6 коров пересекли порог 400k.",
            "action": "Провести ревизию доильного оборудования и гигиены",
            "tags": ["scc", "milk_quality", "group"],
        },
        {
            "insight_id": "INS_006", "type": "heat_detection", "severity": "info",
            "date": today_s, "animal_ids": ["3067", "3112"],
            "title": "2 коровы с высокой активностью охоты сегодня утром",
            "body": "3067 (Лада, активность +140% vs baseline) и 3112 (Радуга, +128%). Рекомендуется AI сегодня.",
            "action": "Запланировать осеменение в операторский worklist",
            "tags": ["act5", "heat_detection", "repro"],
        },
        {
            "insight_id": "INS_007", "type": "withdrawal_compliance", "severity": "warn",
            "date": today_s, "animal_ids": ["3033", "3078", "3101"],
            "title": "5 коров в карантине: молоко не сдаётся на танк",
            "body": "Withdrawal период активен: 3033 (-2д), 3078 (-1д), 3101 (-3д), 3155 (-5д), 3201 (-4д).",
            "action": "Проверить дату снятия карантина у каждой",
            "tags": ["withdrawal", "compliance", "milk_quality"],
        },
        {
            "insight_id": "INS_008", "type": "economics", "severity": "info",
            "date": today_s, "animal_ids": [],
            "title": "Средний надой сегодня: 28.5 кг/гол — в плановом диапазоне",
            "body": "Фактический надой 28.5 кг/гол/день. Плановый: 28.0–30.0. Health index: 94%.",
            "action": "Мониторинг без действий",
            "tags": ["act1", "kpi", "milk_yield"],
        },
        {
            "insight_id": "INS_009", "type": "benchmark", "severity": "info",
            "date": today_s, "animal_ids": [],
            "title": "Ферма на 3pp выше медианы аналогов по Pregnancy Rate",
            "body": "PR 21d = 24% vs медиана аналогичных хозяйств 21%. Разница +3pp даёт +14 стельностей в квартал.",
            "action": "Поделиться с директором как KPI успеха",
            "tags": ["benchmark", "repro", "kpi"],
        },
        {
            "insight_id": "INS_010", "type": "dim_group_analysis", "severity": "info",
            "date": today_s, "animal_ids": [],
            "title": "Группа Fresh (DIM 1-30): 50 коров, кетоз у 3",
            "body": "50 свежеотёлившихся коров. 3 с признаками субклинического кетоза (BHBA >1.2). Плановый скрининг сработал.",
            "action": "Проверить протокол кормления fresh-группы",
            "tags": ["ketosis", "fresh_cow", "dim_group"],
        },
        {
            "insight_id": "INS_011", "type": "upcoming_events", "severity": "info",
            "date": today_s, "animal_ids": [],
            "title": "Прогноз: 8 отёлов ожидается в течение 14 дней",
            "body": "8 коров с расчётной датой отёла до 2026-05-05. Проверьте готовность родильного отделения.",
            "action": "Подготовить родильное отделение, запас препаратов для fresh-протокола",
            "tags": ["calving", "planning"],
        },
        {
            "insight_id": "INS_012", "type": "feed_efficiency", "severity": "warn",
            "date": today_s, "animal_ids": [],
            "title": "DMI PEN_LACT_3 снизился на 8% за неделю",
            "body": "Группа Лактирующие III: средний DMI 20.1 кг vs 21.8 кг прошлой недели (-8%). Связано с переводом 3 коров после лечения.",
            "action": "Проверить качество корма и провести подгонку рациона",
            "tags": ["feed", "dmi", "group"],
        },
    ]


def _build_timeline_events() -> list:
    def te(tid: str, d: date, etype: str, title: str, body: str,
           animal_ids: list, impact: str, impact_val: str) -> dict:
        return {
            "timeline_event_id": tid, "date": d.isoformat(),
            "event_type": etype, "title": title, "body": body,
            "animal_ids": animal_ids, "impact": impact, "impact_value": impact_val,
        }

    return [
        te("TL_001", TODAY - timedelta(days=42),
           "mastitis_outbreak", "Мастит у Звёздочки — начало лечения",
           "СКК 450k, проводимость аномальная. Начат протокол Цефквином.",
           ["4821"], "yield_loss", "-22% удоя на 28 дней"),
        te("TL_002", TODAY - timedelta(days=38),
           "pen_move", "Звёздочка переведена в группу 3",
           "Социальный стресс после лечения. DMI -14%.",
           ["4821"], "dmi_drop", "-14% DMI на 10 дней"),
        te("TL_003", TODAY - timedelta(days=60),
           "mastitis_recurrence", "Малина: первый эпизод мастита",
           "Задняя правая четверть. СКК 680k. Эпизод 1 из 2.",
           ["3891"], "yield_loss", "-30% удоя на 7 дней"),
        te("TL_004", TODAY - timedelta(days=30),
           "mastitis_recurrence", "Малина: повторный мастит",
           "Тот же сектор. СКК 800k. Рецидив — изменение рекомендации на SELL.",
           ["3891"], "culling_trigger", "Score 82 → SELL"),
        te("TL_005", TODAY - timedelta(days=3),
           "activity_drop", "Ночка: падение активности 3 дня подряд",
           "Активность снизилась с 91 до 65 (-29%). СКК растёт.",
           ["3142"], "health_risk", "Вероятность мастита 78%"),
        te("TL_006", TODAY - timedelta(days=1),
           "scc_alert", "Ночка: СКК 450k, проводимость аномальная",
           "Нет открытого лечения. Требуется осмотр ветврача сегодня.",
           ["3142"], "milk_quality_risk", "Потеря >2 кг/день при развитии"),
        te("TL_007", TODAY - timedelta(days=14),
           "heat_detection", "Волна охоты: 11 коров осеменены за 3 дня",
           "Система активности зафиксировала 14 коров. 11 осеменено. 3 пропущено.",
           [], "repro_opportunity", "PR 21d +2pp"),
        te("TL_008", TODAY - timedelta(days=45),
           "calving_wave", "6 отёлов за 5 дней",
           "Все с исходом «лёгкий». 1 задержание последа (3088). Fresh-протокол соблюдён.",
           ["3085", "3086", "3087", "3088", "3089", "3090"],
           "herd_expansion", "+6 в лактацию"),
        te("TL_009", TODAY - timedelta(days=90),
           "scc_group_rise", "Рост СКК в PEN_LACT_3 — начало тренда",
           "Среднее СКК 185k → 210k за 2 недели. Первый сигнал.",
           [], "milk_quality", "Trend -3 балла качества"),
        te("TL_010", TODAY - timedelta(days=21),
           "withdrawal_compliance", "Карантин: 5 коров — молоко не в танк",
           "Соблюдение карантина 100%. Потери: 5 × 3 дня × 28 кг = 420 кг.",
           [], "milk_loss", "-420 кг за период"),
        te("TL_011", TODAY - timedelta(days=7),
           "benchmark_update", "Pregnancy Rate 21d вышел на уровень 24%",
           "Новый рекорд фермы. +3pp к медиане аналогов.",
           [], "repro_kpi", "PR 24% vs benchmark 21%"),
        te("TL_012", TODAY,
           "daily_kpi_snapshot", "Утренний снапшот KPI — сегодня",
           "Надой 28.5 кг/гол. Health index 94%. 3 коровы требуют внимания.",
           ["3142"], "ops_summary", "3 действия в worklist"),
    ]


def _build_morning_briefs() -> list:
    def brief(bid: str, d: date, avg_milk: float, health_idx: int,
              pr21: int, attention: int, highlights: list) -> dict:
        return {
            "brief_id": bid, "date": d.isoformat(), "farm_id": FARM_ID,
            "director_greeting": f"Доброе утро, {DIRECTOR}!",
            "kpis": {
                "avg_milk_yield_kg": avg_milk,
                "health_index_pct": health_idx,
                "pregnancy_rate_21d_pct": pr21,
                "cows_need_attention_today": attention,
                "active_cows": 350, "lactating_cows": 300, "dry_cows": 50,
            },
            "highlights": highlights,
            "generated_at": _ts(d, hour=5),
        }

    return [
        brief("MBRIEF_20260421", TODAY, 28.5, 94, 24, 3, [
            "Ночка (3142): активность упала 3 дня, СКК 450k — ветврачу на осмотр",
            "Звёздочка (4821): удой стабилизировался на 28 кг после мастита",
            "2 коровы с охотой: AI запланировано оператору",
        ]),
        brief("MBRIEF_20260420", TODAY - timedelta(days=1), 28.2, 94, 24, 2, [
            "Ночка (3142): второй день снижения активности",
            "СКК Ночки 420k при контроле вечером — формируется алерт",
        ]),
        brief("MBRIEF_20260419", TODAY - timedelta(days=2), 28.7, 95, 24, 1, [
            "Ночка (3142): первое снижение активности, мониторинг",
            "Малина (3891): консультация ветврача по выбраковке",
        ]),
    ]


def _build_weekly_briefs() -> list:
    def wbrief(bid: str, week_end: date, avg_milk: float, health_idx: int,
               conceptions: int, calvings: int, summary: str) -> dict:
        return {
            "brief_id": bid, "week_end": week_end.isoformat(),
            "week_start": (week_end - timedelta(days=6)).isoformat(),
            "farm_id": FARM_ID,
            "kpis": {
                "avg_milk_yield_kg": avg_milk, "health_index_pct": health_idx,
                "conceptions_confirmed": conceptions, "calvings": calvings,
            },
            "summary": summary,
        }

    return [
        wbrief("WBRIEF_20260421", TODAY, 28.4, 94, 5, 1,
               "Стабильная неделя. Мастит у Ночки на контроле. PR 24% — рекорд фермы."),
        wbrief("WBRIEF_20260414", TODAY - timedelta(days=7), 29.1, 95, 7, 2,
               "Высокая продуктивность. 2 отёла. Heat detection волна: 11 осеменений."),
    ]


def _build_impact_analyses() -> list:
    return [
        {
            "impact_id": "IMP_TL_001",
            "timeline_event_id": "TL_001",
            "animal_id": "4821",
            "metric": "milk_yield",
            "period_days": 28,
            "baseline_kg_day": 36.0,
            "actual_kg_day": 28.0,
            "loss_kg_total": round((36.0 - 28.0) * 28, 1),
            "loss_rub": round((36.0 - 28.0) * 28 * 32, 0),
            "note": "Расчёт при цене 32 руб/кг",
        },
        {
            "impact_id": "IMP_TL_003",
            "timeline_event_id": "TL_003",
            "animal_id": "3891",
            "metric": "milk_yield",
            "period_days": 7,
            "baseline_kg_day": 16.0,
            "actual_kg_day": 11.2,
            "loss_kg_total": round((16.0 - 11.2) * 7, 1),
            "loss_rub": round((16.0 - 11.2) * 7 * 32, 0),
            "note": "Эпизод 1, мастит",
        },
        {
            "impact_id": "IMP_TL_004",
            "timeline_event_id": "TL_004",
            "animal_id": "3891",
            "metric": "npv_30d",
            "period_days": 30,
            "npv_usd": -180,
            "culling_recommendation_triggered": True,
            "note": "Рецидив мастита → SELL",
        },
        {
            "impact_id": "IMP_TL_010",
            "timeline_event_id": "TL_010",
            "animal_id": None,
            "metric": "withdrawal_milk_loss",
            "period_days": 3,
            "cows_in_withdrawal": 5,
            "avg_milk_kg": 28.0,
            "loss_kg_total": 420.0,
            "loss_rub": round(420.0 * 32, 0),
            "note": "Соблюдение карантина 100% — потери плановые",
        },
    ]


# ─── Act 5 operator tasks and Act 3 culling ───────────────────────────────────

def _operator_tasks() -> list:
    return [
        {"task_id": "TASK_001", "task_type": "pregnancy_check", "animal_id": "3015",
         "due_date": TODAY.isoformat(), "priority": "high",
         "notes": "30 дней после AI #2", "assigned_to": "demo_operator"},
        {"task_id": "TASK_002", "task_type": "pregnancy_check", "animal_id": "3028",
         "due_date": TODAY.isoformat(), "priority": "high",
         "notes": "32 дня после AI", "assigned_to": "demo_operator"},
        {"task_id": "TASK_003", "task_type": "pregnancy_check", "animal_id": "3044",
         "due_date": TODAY.isoformat(), "priority": "normal",
         "notes": "35 дней после AI", "assigned_to": "demo_operator"},
        {"task_id": "TASK_004", "task_type": "insemination", "animal_id": "3067",
         "due_date": TODAY.isoformat(), "priority": "high",
         "notes": "Охота зафиксирована в 08:00", "assigned_to": "demo_operator"},
        {"task_id": "TASK_005", "task_type": "insemination", "animal_id": "3112",
         "due_date": TODAY.isoformat(), "priority": "high",
         "notes": "Охота обнаружена ночью", "assigned_to": "demo_operator"},
        {"task_id": "TASK_006", "task_type": "health_check", "animal_id": "3142",
         "due_date": TODAY.isoformat(), "priority": "urgent",
         "notes": "Падение активности + СКК алерт — Ночка", "assigned_to": "demo_vet"},
        {"task_id": "TASK_007", "task_type": "health_check", "animal_id": "3078",
         "due_date": TODAY.isoformat(), "priority": "normal",
         "notes": "Контроль хромоты, оценка локомоции", "assigned_to": "demo_vet"},
        {"task_id": "TASK_008", "task_type": "intake_record", "animal_id": "3200",
         "due_date": TODAY.isoformat(), "priority": "normal",
         "notes": "Ежедневный контроль DMI", "assigned_to": "demo_operator"},
    ]


def _culling_candidates() -> list:
    return [
        {"animal_id": "3891", "name": "Малина",    "recommendation": "SELL",  "score": 82, "reason": "recurrent_mastitis_open_cow_negative_npv"},
        {"animal_id": "3055", "name": "Бурёнка-1", "recommendation": "SELL",  "score": 78, "reason": "chronic_lameness"},
        {"animal_id": "3099", "name": "Зорька-1",  "recommendation": "SELL",  "score": 75, "reason": "low_production_4th_lact"},
        {"animal_id": "3180", "name": "Ночка-3",   "recommendation": "SELL",  "score": 71, "reason": "mastitis_recurrence"},
        {"animal_id": "3220", "name": "Ласточка-4","recommendation": "SELL",  "score": 70, "reason": "open_180d"},
        {"animal_id": "3007", "name": "Бурёнка",   "recommendation": "WATCH", "score": 58, "reason": "borderline_production"},
        {"animal_id": "3033", "name": "Зорька",    "recommendation": "WATCH", "score": 55, "reason": "scc_trending_up"},
        {"animal_id": "3071", "name": "Ласточка",  "recommendation": "WATCH", "score": 52, "reason": "slow_conception"},
        {"animal_id": "3145", "name": "Звёздочка-2","recommendation": "WATCH","score": 50, "reason": "yield_below_benchmark"},
        {"animal_id": "3199", "name": "Милка-3",   "recommendation": "WATCH", "score": 48, "reason": "lameness_history"},
        {"animal_id": "3010", "name": "Умница",    "recommendation": "KEEP",  "score": 22, "reason": "high_producer_good_health"},
        {"animal_id": "3025", "name": "Красавица", "recommendation": "KEEP",  "score": 18, "reason": "pregnant_good_yield"},
        {"animal_id": "3060", "name": "Белянка",   "recommendation": "KEEP",  "score": 15, "reason": "strong_2nd_lact"},
        {"animal_id": "3090", "name": "Пеструха",  "recommendation": "KEEP",  "score": 12, "reason": "excellent_conception_rate"},
        {"animal_id": "3130", "name": "Роза",      "recommendation": "KEEP",  "score":  8, "reason": "top_quartile_milk"},
    ]


# ─── main dataset builder ─────────────────────────────────────────────────────

def build_dataset(with_ai_seeds: bool = False) -> dict[str, Any]:
    rng = random.Random(SEED)

    animals: list[dict]   = []
    events: list[dict]    = []
    treatments: list[dict] = []
    breedings: list[dict]  = []
    milk_yields: list[dict] = []

    # Build seeded cows first
    zvezdochka = _build_zvezdochka(events, treatments, milk_yields)
    malina     = _build_malina(events, treatments, milk_yields)
    nochka     = _build_nochka(events, treatments, milk_yields)
    animals.extend([zvezdochka, malina, nochka])

    # DIM pool for 347 regular cows — match required distribution
    dim_pool: list[int] = []
    for _ in range(49):   dim_pool.append(rng.randint(1, 30))      # Fresh  (one slot taken by Ночка)
    for _ in range(100):  dim_pool.append(rng.randint(31, 100))     # Early
    for _ in range(99):   dim_pool.append(rng.randint(101, 200))    # Mid    (one slot Звёздочка)
    for _ in range(49):   dim_pool.append(rng.randint(201, 305))    # Late   (one slot Малина)
    for _ in range(50):   dim_pool.append(rng.randint(306, 400))    # Dry
    rng.shuffle(dim_pool)

    # Lactation pool: 30/35/20/15 minus 2 (3rd-lact seeded)
    lact_pool: list[int] = [1] * 105 + [2] * 122 + [3] * 68 + [4] * 52
    rng.shuffle(lact_pool)

    next_id   = 3000
    name_idx  = 0
    skip_names = {"Ночка", "Малина", "Звёздочка"}  # natural first-occurrence names reserved

    for reg_idx in range(347):
        while next_id in SEEDED_IDS:
            next_id += 1
        cow_id = str(next_id)
        next_id += 1

        # Skip reserved names at their natural slot (first occurrence)
        while (name_idx // len(COW_NAMES) == 0 and
               COW_NAMES[name_idx % len(COW_NAMES)] in skip_names):
            name_idx += 1
        name = cow_display_name(name_idx)
        name_idx += 1

        dim    = dim_pool[reg_idx % len(dim_pool)]
        lact   = lact_pool[reg_idx % len(lact_pool)]
        is_dry = dim > 305

        calving = TODAY - timedelta(days=dim)
        birth   = calving - timedelta(
            days=730 + (lact - 1) * 380 + rng.randint(-60, 60)
        )
        peak_kg = rng.uniform(32.0, 40.0)
        milk305 = int(peak_kg * 280)

        cow: dict[str, Any] = {
            "animal_id":    cow_id,
            "name":         name,
            "farm_id":      FARM_ID,
            "tenant_id":    TENANT_ID,
            "sex":          "F",
            "breed":        "Holstein",
            "birth_date":   birth.isoformat(),
            "status":       "active",
            "lactation_no": lact,
            "calving_date": calving.isoformat(),
            "dim":          dim,
            "current_pen_id": pen_for_cow(dim, is_dry),
            "milk_305d_kg": milk305,
            "peak_milk_kg": round(peak_kg, 1),
        }
        animals.append(cow)

        # Milk yield — every day cow was lactating within history window
        for day_i in range(180):
            d = HISTORY_START + timedelta(days=day_i)
            cur_dim = (d - calving).days
            if cur_dim <= 0 or cur_dim > 305:
                continue
            mk = wood_milk(cur_dim, peak_kg) + rng.gauss(0, 0.5)
            milk_yields.append(_milk_rec(
                cow_id, d, mk,
                3.7 + rng.gauss(0, 0.15),
                3.1 + rng.gauss(0, 0.09),
                int(max(50000, 150000 + rng.gauss(0, 40000))),
            ))

        # Health events (probabilistic)
        roll = rng.random()
        if roll < 0.15:                              # 15% mastitis
            ev_d = HISTORY_START + timedelta(days=rng.randint(10, 170))
            if HISTORY_START <= ev_d <= TODAY and (ev_d - calving).days > 0:
                ev_id = f"EV_{cow_id}_MAST_01"
                events.append({
                    "event_id": ev_id, "animal_id": cow_id,
                    "event_type": "mastitis", "event_date": _ts(ev_d),
                    "severity": rng.choice(["medium", "high"]),
                    "details": {
                        "scc": rng.randint(350000, 900000),
                        "quarter": rng.choice(["rear_left", "rear_right", "front_left", "front_right"]),
                    },
                    "reporter": "demo_vet", "evidence_ids": [],
                })
                dname, route, wd = DRUG_PROTOCOLS["mastitis"]
                dur = rng.randint(3, 5)
                treatments.append({
                    "treatment_id":       f"TR_{cow_id}_MAST_01",
                    "animal_id":          cow_id,
                    "start_date":         ev_d.isoformat(),
                    "end_date":           (ev_d + timedelta(days=dur)).isoformat(),
                    "drug_name":          dname,
                    "drug_route":         route,
                    "withdrawal_end_date": (ev_d + timedelta(days=dur + wd)).isoformat(),
                    "reason_event_id":    ev_id,
                    "prescribed_by":      "demo_vet",
                    "executed_by":        "demo_operator",
                })
        elif roll < 0.23:                            # 8% lameness
            ev_d = HISTORY_START + timedelta(days=rng.randint(10, 170))
            if HISTORY_START <= ev_d <= TODAY and (ev_d - calving).days > 0:
                ev_id = f"EV_{cow_id}_LAM_01"
                events.append({
                    "event_id": ev_id, "animal_id": cow_id,
                    "event_type": "lameness", "event_date": _ts(ev_d),
                    "severity": rng.choice(["medium", "high"]),
                    "details": {
                        "locomotion_score": rng.randint(3, 5),
                        "limb": rng.choice(["RF", "LF", "RR", "LR"]),
                    },
                    "reporter": "demo_vet", "evidence_ids": [],
                })
                dname, route, wd = DRUG_PROTOCOLS["lameness"]
                treatments.append({
                    "treatment_id":       f"TR_{cow_id}_LAM_01",
                    "animal_id":          cow_id,
                    "start_date":         ev_d.isoformat(),
                    "end_date":           (ev_d + timedelta(days=3)).isoformat(),
                    "drug_name":          dname,
                    "drug_route":         route,
                    "withdrawal_end_date": (ev_d + timedelta(days=6)).isoformat(),
                    "reason_event_id":    ev_id,
                    "prescribed_by":      "demo_vet",
                    "executed_by":        "demo_operator",
                })
        elif roll < 0.28 and dim <= 60:              # 5% ketosis (fresh cows only)
            ev_d = calving + timedelta(days=rng.randint(3, 21))
            if HISTORY_START <= ev_d <= TODAY:
                ev_id = f"EV_{cow_id}_KET_01"
                events.append({
                    "event_id": ev_id, "animal_id": cow_id,
                    "event_type": "ketosis", "event_date": _ts(ev_d),
                    "severity": "medium",
                    "details": {"bhba_mmol_l": round(rng.uniform(1.2, 3.5), 2)},
                    "reporter": "demo_vet", "evidence_ids": [],
                })
                dname, route, wd = DRUG_PROTOCOLS["ketosis"]
                treatments.append({
                    "treatment_id":       f"TR_{cow_id}_KET_01",
                    "animal_id":          cow_id,
                    "start_date":         ev_d.isoformat(),
                    "end_date":           (ev_d + timedelta(days=3)).isoformat(),
                    "drug_name":          dname,
                    "drug_route":         route,
                    "withdrawal_end_date": ev_d.isoformat(),
                    "reason_event_id":    ev_id,
                    "prescribed_by":      "demo_vet",
                    "executed_by":        "demo_operator",
                })

        # Calving event (if within history window)
        if HISTORY_START <= calving <= TODAY:
            events.append({
                "event_id":   f"EV_{cow_id}_CALV_01",
                "animal_id":  cow_id,
                "event_type": "calving",
                "event_date": _ts(calving, hour=rng.randint(0, 23)),
                "severity":   "info",
                "details": {
                    "calf_sex":         rng.choice(["M", "F"]),
                    "calf_weight_kg":   round(rng.uniform(35.0, 48.0), 1),
                    "ease_of_calving":  rng.choice(["easy", "easy", "easy", "assisted"]),
                    "complications":    rng.choice([None, None, None, "retained_placenta"]),
                },
                "reporter": "demo_zootech", "evidence_ids": [],
            })

        # Breeding (cows past voluntary waiting period)
        vwp_end = calving + timedelta(days=60)
        if dim > 40 and vwp_end <= TODAY:
            first_ai = vwp_end + timedelta(days=rng.randint(0, 30))
            if HISTORY_START <= first_ai <= TODAY:
                bull = rng.choice(BULL_NAMES)
                result = rng.choice(["pregnant", "pregnant", "open", "open", "open"])
                preg_check = (first_ai + timedelta(days=35)).isoformat() \
                    if first_ai + timedelta(days=35) <= TODAY else None
                breedings.append({
                    "breeding_id":    f"BR_{cow_id}_01",
                    "animal_id":      cow_id,
                    "date":           first_ai.isoformat(),
                    "method":         "AI",
                    "bull_name":      bull,
                    "heat_detected":  rng.choice([True, True, False]),
                    "result":         result,
                    "preg_check_date": preg_check,
                })
                if result == "pregnant" and preg_check:
                    events.append({
                        "event_id":   f"EV_{cow_id}_PREGCK_01",
                        "animal_id":  cow_id,
                        "event_type": "pregnancy_check",
                        "event_date": _ts(first_ai + timedelta(days=35), hour=10),
                        "severity":   "info",
                        "details":    {"result": "pregnant", "method": "ultrasound"},
                        "reporter":   "demo_vet", "evidence_ids": [],
                    })

        # Monthly BCS measurements (6 per cow over 180-day window)
        for bcs_i in range(6):
            bcs_d = HISTORY_START + timedelta(days=bcs_i * 30 + rng.randint(0, 5))
            if bcs_d > TODAY:
                break
            cur_dim_bcs = (bcs_d - calving).days
            if cur_dim_bcs <= 0:
                continue
            bcs_base = 3.25 if cur_dim_bcs < 100 else (3.0 if cur_dim_bcs < 200 else 3.5)
            events.append({
                "event_id":   f"EV_{cow_id}_BCS_{bcs_i:02d}",
                "animal_id":  cow_id,
                "event_type": "bcs_measurement",
                "event_date": _ts(bcs_d, hour=9),
                "severity":   "info",
                "details":    {
                    "bcs":        round(bcs_base + rng.gauss(0, 0.2), 2),
                    "dim_at_bcs": cur_dim_bcs,
                    "recorder":   "demo_zootech",
                },
                "reporter": "demo_zootech", "evidence_ids": [],
            })

        # Bi-weekly SCC / milk quality readings
        for scc_i in range(9):
            scc_d = HISTORY_START + timedelta(days=scc_i * 21)
            if scc_d > TODAY:
                break
            cur_dim_scc = (scc_d - calving).days
            if cur_dim_scc <= 0 or cur_dim_scc > 305:
                continue
            scc_val = int(max(50000, 150000 + rng.gauss(0, 50000)))
            events.append({
                "event_id":   f"EV_{cow_id}_SCCR_{scc_i:02d}",
                "animal_id":  cow_id,
                "event_type": "milk_quality_reading",
                "event_date": _ts(scc_d, hour=8),
                "severity":   "high" if scc_val > 400000 else ("warn" if scc_val > 250000 else "info"),
                "details":    {
                    "scc_cells_ml": scc_val,
                    "fat_pct":      round(3.7 + rng.gauss(0, 0.15), 2),
                    "protein_pct":  round(3.1 + rng.gauss(0, 0.09), 2),
                    "conductivity": "abnormal" if scc_val > 350000 else "normal",
                },
                "reporter": "system", "evidence_ids": [],
            })

    return {
        "animals":              animals,
        "events":               events,
        "treatments":           treatments,
        "breedings":            breedings,
        "milk_yields":          milk_yields,
        "operator_tasks":       _operator_tasks(),
        "culling_candidates":   _culling_candidates(),
        "insights_seeded":      _build_insights(with_ai_seeds),
        "timeline_events_seeded": _build_timeline_events(),
        "morning_briefs_seeded":  _build_morning_briefs(),
        "weekly_briefs_seeded":   _build_weekly_briefs(),
        "impact_analyses_seeded": _build_impact_analyses(),
    }


# ─── SQL generator ────────────────────────────────────────────────────────────

def _build_sql(data: dict[str, Any]) -> str:
    lines = [
        "-- GenomeAI investor demo farm v1 — SQL seed",
        "-- SYNTHETIC DATA ONLY. Never mix with production evidence.",
        f"-- Generated: {TODAY.isoformat()}",
        "-- Load: psql $GENOMEAI_DB_DSN -f seed.sql",
        "",
        "BEGIN;",
        "",
        "CREATE SCHEMA IF NOT EXISTS demo_investor;",
        "",
        "CREATE TABLE IF NOT EXISTS demo_investor.animals (",
        "  animal_id TEXT PRIMARY KEY,",
        "  name TEXT NOT NULL,",
        "  farm_id TEXT NOT NULL,",
        "  tenant_id TEXT NOT NULL DEFAULT 'default',",
        "  sex CHAR(1) NOT NULL DEFAULT 'F',",
        "  breed TEXT,",
        "  birth_date DATE,",
        "  status TEXT,",
        "  lactation_no INT,",
        "  calving_date DATE,",
        "  dim INT,",
        "  current_pen_id TEXT,",
        "  milk_305d_kg INT,",
        "  peak_milk_kg NUMERIC(5,1),",
        "  tags TEXT[]",
        ");",
        "",
        "CREATE TABLE IF NOT EXISTS demo_investor.events (",
        "  event_id TEXT PRIMARY KEY,",
        "  animal_id TEXT NOT NULL,",
        "  event_type TEXT NOT NULL,",
        "  event_date TIMESTAMPTZ,",
        "  severity TEXT,",
        "  details JSONB,",
        "  reporter TEXT,",
        "  evidence_ids TEXT[]",
        ");",
        "",
        "CREATE TABLE IF NOT EXISTS demo_investor.treatments (",
        "  treatment_id TEXT PRIMARY KEY,",
        "  animal_id TEXT NOT NULL,",
        "  start_date DATE,",
        "  end_date DATE,",
        "  drug_name TEXT,",
        "  drug_route TEXT,",
        "  withdrawal_end_date DATE,",
        "  reason_event_id TEXT,",
        "  prescribed_by TEXT,",
        "  executed_by TEXT",
        ");",
        "",
        "CREATE TABLE IF NOT EXISTS demo_investor.milk_yields (",
        "  record_id TEXT PRIMARY KEY,",
        "  animal_id TEXT NOT NULL,",
        "  date DATE NOT NULL,",
        "  milk_kg NUMERIC(5,1),",
        "  fat_pct NUMERIC(4,2),",
        "  protein_pct NUMERIC(4,2),",
        "  scc_cells_ml INT",
        ");",
        "",
        "CREATE TABLE IF NOT EXISTS demo_investor.breedings (",
        "  breeding_id TEXT PRIMARY KEY,",
        "  animal_id TEXT NOT NULL,",
        "  date DATE,",
        "  method TEXT,",
        "  bull_name TEXT,",
        "  heat_detected BOOLEAN,",
        "  result TEXT,",
        "  preg_check_date DATE",
        ");",
        "",
        "-- Bulk data is loaded from JSON fixtures via the Python script.",
        "-- Insert the 3 seeded cows explicitly for quick reference:",
        "",
    ]

    seeded_ids = ["4821", "3891", "3142"]
    seeded_animals = [a for a in data["animals"] if a["animal_id"] in seeded_ids]
    for a in seeded_animals:
        tags_sql = "ARRAY[" + ", ".join(f"'{t}'" for t in (a.get("tags") or [])) + "]"
        lines.append(
            f"INSERT INTO demo_investor.animals "
            f"(animal_id,name,farm_id,tenant_id,sex,breed,birth_date,status,"
            f"lactation_no,calving_date,dim,current_pen_id,milk_305d_kg,peak_milk_kg,tags) "
            f"VALUES ("
            f"'{a['animal_id']}','{a['name']}','{a['farm_id']}','{a['tenant_id']}',"
            f"'F','Holstein','{a['birth_date']}','{a['status']}',"
            f"{a['lactation_no']},'{a['calving_date']}',{a['dim']},"
            f"'{a['current_pen_id']}',{a['milk_305d_kg']},{a['peak_milk_kg']},"
            f"{tags_sql}"
            f") ON CONFLICT (animal_id) DO NOTHING;"
        )

    lines += [
        "",
        "-- To load full dataset into Postgres from JSON:",
        "-- python scripts/build_demo_farm_investor.py --mode connecterra",
        "-- Then use: \\copy demo_investor.milk_yields FROM PROGRAM",
        "--   'python -c \"import json,csv,sys; ...'",
        "-- Or use psycopg2 / asyncpg bulk insert in seed_demo_investor.sh",
        "",
        "COMMIT;",
    ]
    return "\n".join(lines)


# ─── file writers ─────────────────────────────────────────────────────────────

def _write_json(path: Path, obj: Any) -> int:
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8")
    if isinstance(obj, list):
        return len(obj)
    return 1


def _write_csvs(data: dict[str, Any], out: Path) -> None:
    """Write CSV fixtures compatible with configs/contracts/ schemas."""
    import csv

    HEALTH_TYPES = {"mastitis", "lameness", "ketosis", "metritis"}
    SEV_MAP = {"urgent": "critical", "high": "high", "medium": "medium",
               "warn": "low", "info": "low"}

    # dm_farms.csv
    with (out / "dm_farms.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["farm_id", "farm_name", "region", "country", "lat", "lon",
                    "created_at", "is_active"])
        w.writerow([FARM_ID, FARM_NAME, "Васильковский район", "RU",
                    "55.123", "37.456", TODAY.isoformat(), "true"])

    # dm_animals.csv
    with (out / "dm_animals.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["animal_id", "farm_id", "ear_tag", "breed", "sex",
                    "birth_date", "is_alive", "status"])
        for a in data["animals"]:
            w.writerow([a["animal_id"], a["farm_id"], a["animal_id"],
                        a.get("breed", "Holstein"), "F",
                        a.get("birth_date", ""), "true", a.get("status", "active")])

    # dm_lactations.csv
    with (out / "dm_lactations.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["animal_id", "lactation_no", "calving_date", "dryoff_date",
                    "days_in_milk", "milk_305d_kg", "fat_pct", "protein_pct"])
        for a in data["animals"]:
            calv = a.get("calving_date", "")
            if calv:
                dry_d = (date.fromisoformat(calv) + timedelta(days=305)).isoformat()
            else:
                dry_d = ""
            w.writerow([a["animal_id"], a.get("lactation_no", 1),
                        calv, dry_d, a.get("dim", 0),
                        a.get("milk_305d_kg", 9000), "3.80", "3.20"])

    # dm_health_events.csv  (only real health episodes, not sensor alerts / BCS)
    health_events = [e for e in data["events"] if e.get("event_type") in HEALTH_TYPES]
    with (out / "dm_health_events.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["tenant_id", "event_id", "animal_id", "event_date",
                    "event_type", "severity", "notes"])
        for e in health_events:
            raw_sev = e.get("severity", "medium")
            sev = SEV_MAP.get(raw_sev, "medium")
            ev_date = e["event_date"][:10] if "T" in e["event_date"] else e["event_date"]
            w.writerow([TENANT_ID, e["event_id"], e["animal_id"],
                        ev_date, e["event_type"], sev, ""])

    # dm_treatments.csv
    with (out / "dm_treatments.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["tenant_id", "treatment_id", "animal_id", "start_date",
                    "end_date", "treatment_type", "reason_event_id",
                    "withdrawal_end_date"])
        for t in data["treatments"]:
            ttype = "mastitis_protocol" if "MAST" in t["treatment_id"] else \
                    "lameness_protocol" if "LAM" in t["treatment_id"] else \
                    "ketosis_protocol"
            w.writerow([TENANT_ID, t["treatment_id"], t["animal_id"],
                        t.get("start_date", ""), t.get("end_date", ""),
                        ttype, t.get("reason_event_id", ""),
                        t.get("withdrawal_end_date", "")])


def _write_readme(out: Path, counts: dict[str, int]) -> None:
    lines = [
        "# Investor Demo Farm v1 — SYNTHETIC dataset",
        "",
        f"Farm: **{FARM_NAME}** ({HOLDING}), {ADDRESS}",
        f"Director: {DIRECTOR}",
        f"Generated: {TODAY.isoformat()} | seed=42 | mode=connecterra",
        "",
        "## Files",
        "",
        "| File | Records | Description |",
        "|------|---------|-------------|",
    ]
    desc = {
        "animals":               "350 active dairy cows",
        "events":                "Health/calving/pen-move events",
        "treatments":            "Drug treatments with withdrawal dates",
        "breedings":             "AI breeding records",
        "milk_yields":           "Daily milk yield (350 cows × 180 days)",
        "insights_seeded":       "12 seeded AI insights for demo acts",
        "timeline_events_seeded": "10–12 timeline events with impact",
        "morning_briefs_seeded": "3 morning briefings (today/yesterday/day before)",
        "weekly_briefs_seeded":  "2 weekly briefings",
        "impact_analyses_seeded": "Economic impact per timeline event",
        "operator_tasks":        "Act 5: 8 operator worklist tasks",
        "culling_candidates":    "Act 3: 15 culling candidates (5 sell/5 watch/5 keep)",
    }
    for key, cnt in counts.items():
        lines.append(f"| `{key}.json` | {cnt} | {desc.get(key, '')} |")

    lines += [
        "",
        "## Seeded Demo Cases",
        "",
        "### Акт 2 — Звёздочка (ID 4821)",
        "- 3-я лактация, 156 DIM",
        "- Мастит -42 дня, лечение Цефквином, перевод в группу 3",
        "- Удой упал с 36 до 28 кг/день (-22%)",
        "",
        "### Акт 3 — Малина (ID 3891)",
        "- 3-я лактация, 285 DIM, 2 эпизода мастита за 60 дней",
        "- Open 145 дней, NPV -$180, рекомендация SELL",
        "",
        "### Акт 4 — Ночка (ID 3142)",
        "- 2-я лактация, 45 DIM",
        "- Активность снизилась 3 дня, СКК 450k, нет открытого лечения",
        "",
        "### Акт 5 — Worklist оператора",
        "- 8 задач: 3 проверки стельности, 2 осеменения, 2 наблюдения, 1 DMI",
        "",
        "## KPI Dashboard (Акт 1)",
        "- avg_milk_yield: 28.5 кг/гол/день",
        "- health_index: 94%",
        "- pregnancy_rate_21d: 24%",
        "- cows_need_attention_today: 3",
        "",
        "---",
        "SYNTHETIC DATA — not for production use.",
    ]
    (out / "README.md").write_text("\n".join(lines), encoding="utf-8")


# ─── main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Build investor-grade demo farm dataset v2")
    ap.add_argument("--mode", default="connecterra",
                    choices=["connecterra"], help="Generation mode")
    ap.add_argument("--with-ai-seeds", action="store_true",
                    help="Include extended AI narrative seeds")
    ap.add_argument("--output-dir",
                    default=str(ROOT / "data" / "demo" / "investor_v1"))
    args = ap.parse_args()

    random.seed(SEED)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    print(f"Building demo farm dataset → {out}", flush=True)
    data = build_dataset(with_ai_seeds=args.with_ai_seeds)

    counts: dict[str, int] = {}
    for key, value in data.items():
        counts[key] = _write_json(out / f"{key}.json", value)
        print(f"  {key}.json: {counts[key]} records")

    _write_csvs(data, out)
    print(f"  CSV fixtures: dm_farms, dm_animals, dm_lactations, dm_health_events, dm_treatments")

    (out / "seed.sql").write_text(_build_sql(data), encoding="utf-8")
    print(f"  seed.sql: written")

    _write_readme(out, counts)
    print(f"  README.md: written")

    manifest = {
        "dataset_id":   "investor_v1",
        "synthetic":    True,
        "synthetic_note": "Investor-grade synthetic demo farm. Never mix with production data.",
        "generated_at": TODAY.isoformat(),
        "generator":    "scripts/build_demo_farm_investor.py",
        "mode":         args.mode,
        "farm_id":      FARM_ID,
        "farm_name":    FARM_NAME,
        "holding":      HOLDING,
        "director":     DIRECTOR,
        "total_cows":   len(data["animals"]),
        "history_days": 180,
        "history_start": HISTORY_START.isoformat(),
        "history_end":   TODAY.isoformat(),
        "seeded_cows": {
            "zvezdochka": {"id": "4821", "act": 2},
            "malina":     {"id": "3891", "act": 3},
            "nochka":     {"id": "3142", "act": 4},
        },
        "kpis_act1": {
            "avg_milk_yield_kg": 28.5,
            "health_index_pct": 94,
            "pregnancy_rate_21d_pct": 24,
            "cows_need_attention_today": 3,
        },
        "row_counts": counts,
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  manifest.json: written")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
