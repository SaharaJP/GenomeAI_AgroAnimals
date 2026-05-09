"""Tool definitions + executors for Anthropic tool use (MVP-N12)."""
from __future__ import annotations

import datetime
from typing import Any, Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Anthropic tool definition dicts
# ---------------------------------------------------------------------------

COW_HISTORY_TOOL = {
    "name": "get_animal_profile",
    "description": (
        "Получить полную историю коровы: события за N дней, лечения, удой по дням, BCS, "
        "переводы групп. Используй когда нужны детали конкретной коровы."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "cow_id": {"type": "string", "description": "ID коровы"},
            "days_back": {
                "type": "integer",
                "description": "Глубина истории в днях",
                "default": 30,
            },
        },
        "required": ["cow_id"],
    },
}

GROUP_METRICS_TOOL = {
    "name": "get_kpi_summary",
    "description": (
        "Получить агрегированные метрики по группе/стаду за период: удой, SCC, "
        "события здоровья, воспроизводство. Используй для сравнения групп или "
        "анализа динамики в группе."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "group_id": {
                "type": "string",
                "description": "ID группы/пера, или 'all' для всего стада",
            },
            "period": {
                "type": "string",
                "enum": ["7d", "14d", "30d"],
                "description": "Период анализа",
                "default": "7d",
            },
        },
        "required": ["group_id"],
    },
}

EVENT_SEARCH_TOOL = {
    "name": "search_events_timeline",
    "description": (
        "Поиск событий по ферме с фильтрацией: болезни, лечения, осеменения, "
        "отёлы, выбраковки. Используй когда нужно найти конкретный тип событий "
        "за период или по конкретным коровам."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "event_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Типы событий: mastitis, treatment, insemination, calving, culling, scc_spike, health, repro",
            },
            "cow_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Опциональный фильтр по коровам",
            },
            "date_from": {
                "type": "string",
                "description": "Начало периода ISO-8601 (YYYY-MM-DD)",
            },
            "date_to": {
                "type": "string",
                "description": "Конец периода ISO-8601 (YYYY-MM-DD)",
            },
            "limit": {
                "type": "integer",
                "description": "Максимум результатов",
                "default": 50,
            },
        },
    },
}

TREATMENT_TOOL = {
    "name": "get_treatment_records",
    "description": (
        "Получить список лечений и withdrawal-статусов. "
        "Используй для проверки активных withdrawals или истории лечений."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["active", "completed", "all"],
                "description": "Фильтр по статусу",
                "default": "all",
            },
            "cow_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Опциональный фильтр по коровам",
            },
        },
    },
}

REPRODUCTION_TOOL = {
    "name": "get_reproduction_status",
    "description": (
        "Получить статус воспроизводства: последняя охота, осеменение, "
        "результат проверки стельности, DIM, VWP. "
        "Используй для анализа эффективности воспроизводства."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "cow_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Список ID коров (опционально)",
            },
            "group_id": {
                "type": "string",
                "description": "ID группы для агрегации (опционально)",
            },
        },
    },
}

MILK_QUALITY_TOOL = {
    "name": "get_milk_quality_trend",
    "description": (
        "Получить тренды качества молока: SCC, conductivity, жир, белок. "
        "Работает на уровне коровы или группы за период."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "cow_id": {"type": "string", "description": "ID коровы (или null для группы/стада)"},
            "group_id": {"type": "string", "description": "ID группы (или null для отдельной коровы)"},
            "period": {
                "type": "string",
                "enum": ["7d", "14d", "30d"],
                "default": "30d",
            },
        },
    },
}

ECONOMICS_TOOL = {
    "name": "get_economics_snapshot",
    "description": (
        "Получить экономику: NPV, дневной cash flow, break-even прогноз. "
        "На уровне коровы или всей фермы. Используй для оценки целесообразности выбраковки."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "cow_id": {
                "type": "string",
                "description": "ID коровы для индивидуального NPV (или null для фермы)",
            },
        },
    },
}

# ── Canonical aliases (point to existing dicts; introduced for P1-1 registry split) ──
ANIMAL_PROFILE_TOOL = COW_HISTORY_TOOL
KPI_SUMMARY_TOOL = GROUP_METRICS_TOOL
SEARCH_EVENTS_TIMELINE_TOOL = EVENT_SEARCH_TOOL

ANALYZE_EVENT_IMPACT_TOOL = {
    "name": "analyze_event_impact",
    "description": (
        "Запустить импакт-анализ влияния события (смена рациона, лечение, "
        "перевод группы) на KPI стада. Возвращает дельту KPI и доверительный "
        "интервал."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "event_id": {"type": "string", "description": "ID события для анализа"},
            "kpi": {
                "type": "string",
                "enum": ["milk_kg", "scc", "fat_pct", "protein_pct"],
                "default": "milk_kg",
                "description": "KPI для импакт-анализа",
            },
            "window_days": {
                "type": "integer",
                "default": 14,
                "description": "Окно (дней) до/после события",
            },
        },
        "required": ["event_id"],
    },
}

FIND_ATTENTION_COWS_TOOL = {
    "name": "find_attention_cows",
    "description": (
        "Топ-N коров «под наблюдением» по комбинированному скору: высокий SCC, "
        "падение надоя, активные лечения, отклонения BCS. Используй когда оператор "
        "спрашивает «кто требует внимания» или «кого посмотреть сегодня»."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "threshold_count": {
                "type": "integer",
                "default": 10,
                "description": "Сколько коров вернуть",
            },
        },
    },
}

CALCULATE_CULL_NPV_TOOL = {
    "name": "calculate_cull_npv",
    "description": (
        "Расчёт NPV для выбраковки конкретной коровы: сравнение NPV_keep и NPV_cull с рекомендацией. "
        "Используй когда оператор спрашивает, стоит ли выбраковать корову."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "animal_id": {"type": "string", "description": "ID коровы"},
        },
        "required": ["animal_id"],
    },
}

FORECAST_MILK_YIELD_TOOL = {
    "name": "forecast_milk_yield",
    "description": (
        "Прогноз надоя на 7–30 дней вперёд на уровне коровы или группы "
        "(укажи ровно одно из animal_id или group_id). Линейная регрессия по DIM."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "animal_id": {"type": "string", "description": "ID коровы (укажи если нужен прогноз по одному животному; иначе укажи group_id)"},
            "group_id": {"type": "string", "description": "ID группы (укажи если нужен групповой прогноз; иначе укажи animal_id)"},
            "horizon_days": {
                "type": "integer",
                "default": 7,
                "description": "Горизонт прогноза (7–30 дней)",
            },
        },
    },
}

# Канонические 7 инструментов соответствуют разделу 3.1.4 ВКР
# (Таблица 3.1.4 — 7 канонических tools со специфичными именами).
CANONICAL_TOOLS = [
    ANIMAL_PROFILE_TOOL,
    ANALYZE_EVENT_IMPACT_TOOL,
    FORECAST_MILK_YIELD_TOOL,
    CALCULATE_CULL_NPV_TOOL,
    FIND_ATTENTION_COWS_TOOL,
    KPI_SUMMARY_TOOL,
    SEARCH_EVENTS_TIMELINE_TOOL,
]

# Дополнительные 3 — production-расширения, не упоминаются в дипломе как часть
# канонических 7, но оставляются в реестре для совместимости.
EXTRA_TOOLS = [
    TREATMENT_TOOL,
    REPRODUCTION_TOOL,
    MILK_QUALITY_TOOL,
]

ALL_TOOLS = CANONICAL_TOOLS + EXTRA_TOOLS  # 10 total

# ---------------------------------------------------------------------------
# Tool executor
# ---------------------------------------------------------------------------

_MAX_OUTPUT_TOKENS = 5000
_APPROX_CHARS_PER_TOKEN = 4


def _truncate(data: Any, label: str = "") -> Any:
    """Truncate serialised output to stay under _MAX_OUTPUT_TOKENS."""
    import json
    text = json.dumps(data, ensure_ascii=False, default=str)
    limit = _MAX_OUTPUT_TOKENS * _APPROX_CHARS_PER_TOKEN
    if len(text) <= limit:
        return data
    # Return truncated rows
    if isinstance(data, dict) and "rows" in data:
        rows = data["rows"]
        while len(json.dumps(data, ensure_ascii=False, default=str)) > limit and rows:
            rows = rows[:-1]
        data["rows"] = rows
        data["truncated"] = True
        return data
    return {"truncated_text": text[:limit], "truncated": True}


def execute_tool(tool_name: str, tool_input: dict, store: Any) -> dict:
    """
    Dispatch a tool call to the appropriate executor.

    Parameters
    ----------
    tool_name:   One of the tool names in ALL_TOOLS.
    tool_input:  Parsed input dict from Claude tool_use block.
    store:       DemoDataStore (or future DB-backed store).

    Returns
    -------
    JSON-serialisable dict, max ~5000 tokens.
    """
    # Public tool names follow thesis §3.1.4 canonical naming; internal _exec_*
    # function names retain pre-rename identifiers (deferred rename — P1-1b).
    handlers = {
        "get_animal_profile": _exec_cow_history,
        "get_kpi_summary": _exec_group_metrics,
        "search_events_timeline": _exec_search_events,
        "get_treatment_records": _exec_treatment_records,
        "get_reproduction_status": _exec_reproduction_status,
        "get_milk_quality_trend": _exec_milk_quality_trend,
        "get_economics_snapshot": _exec_economics_snapshot,
        "analyze_event_impact": _exec_analyze_event_impact,
        "find_attention_cows": _exec_find_attention_cows,
        "calculate_cull_npv": _exec_calculate_cull_npv,
        "forecast_milk_yield": _exec_forecast_milk_yield,
    }
    handler = handlers.get(tool_name)
    if handler is None:
        return {"error": f"unknown tool: {tool_name}"}
    try:
        result = handler(tool_input, store)
    except NotImplementedError as exc:
        return {"error": f"not_implemented: {exc}"}
    return _truncate(result, tool_name)


# ---------------------------------------------------------------------------
# Individual executors
# ---------------------------------------------------------------------------

def _exec_cow_history(inp: dict, store: Any) -> dict:
    cow_id = str(inp["cow_id"])
    days_back = int(inp.get("days_back", 30))
    as_ts = pd.Timestamp(datetime.date.today())
    window = as_ts - pd.Timedelta(days=days_back)

    rows_mk = _filter_df(
        store.milkings(), "animal_id", cow_id,
        date_col="date", date_from=window,
    )
    rows_he = _filter_df(
        store.health_events(), "animal_id", cow_id,
        date_col="event_date", date_from=window,
    )
    rows_tr = _filter_df(
        store.treatments(), "animal_id", cow_id,
        date_col="start_date", date_from=window,
    )
    rows_repro = _filter_df(
        store.repro_events(), "animal_id", cow_id,
        date_col="event_date", date_from=window,
    )
    rows_moves = _filter_df(
        store.pen_moves(), "animal_id", cow_id,
        date_col="move_date", date_from=window,
    )

    return {
        "cow_id": cow_id,
        "days_back": days_back,
        "rows": {
            "milkings": _df_to_records(rows_mk),
            "health_events": _df_to_records(rows_he),
            "treatments": _df_to_records(rows_tr),
            "repro_events": _df_to_records(rows_repro),
            "pen_moves": _df_to_records(rows_moves),
        },
    }


def _exec_group_metrics(inp: dict, store: Any) -> dict:
    group_id = str(inp.get("group_id", "all"))
    period = inp.get("period", "7d")
    days_back = int(period.rstrip("d")) if period else 7

    as_ts = pd.Timestamp(datetime.date.today())
    window = as_ts - pd.Timedelta(days=days_back)

    animals = store.animals()
    if group_id != "all" and not animals.empty and "current_pen_id" in animals.columns:
        group_animals = animals[animals["current_pen_id"] == group_id]["animal_id"].tolist()
    else:
        group_animals = animals["animal_id"].tolist() if not animals.empty else []

    milkings = store.milkings()
    avg_yield = scc_avg = 0.0
    if not milkings.empty and group_animals:
        mk = milkings.copy()
        mk["date"] = pd.to_datetime(mk["date"], errors="coerce")
        gm = mk[(mk["animal_id"].isin(group_animals)) & (mk["date"] >= window)]
        if not gm.empty:
            avg_yield = float(gm["milk_kg"].mean()) if "milk_kg" in gm else 0.0
            scc_avg = float(gm["scc_cells_ml"].mean()) / 1000 if "scc_cells_ml" in gm else 0.0

    he = store.health_events()
    health_event_count = 0
    if not he.empty and group_animals:
        h = he.copy()
        h["event_date"] = pd.to_datetime(h["event_date"], errors="coerce")
        health_event_count = int(
            len(h[(h["animal_id"].isin(group_animals)) & (h["event_date"] >= window)])
        )

    return {
        "group_id": group_id,
        "period": period,
        "cow_count": len(group_animals),
        "avg_milk_yield_kg": round(avg_yield, 2),
        "scc_avg_k": round(scc_avg, 1),
        "health_event_count": health_event_count,
    }


def _exec_search_events(inp: dict, store: Any) -> dict:
    event_types = [str(t) for t in inp.get("event_types", [])]
    cow_ids = [str(c) for c in inp.get("cow_ids", [])] if inp.get("cow_ids") else []
    date_from = pd.Timestamp(inp["date_from"]) if inp.get("date_from") else pd.Timestamp("2020-01-01")
    date_to = pd.Timestamp(inp["date_to"]) if inp.get("date_to") else pd.Timestamp(datetime.date.today())
    limit = int(inp.get("limit", 50))

    results: list[dict] = []

    # Health events
    if not event_types or any(t in event_types for t in ("mastitis", "health", "all")):
        he = store.health_events()
        if not he.empty:
            h = he.copy()
            h["event_date"] = pd.to_datetime(h["event_date"], errors="coerce")
            mask = (h["event_date"] >= date_from) & (h["event_date"] <= date_to)
            if cow_ids:
                mask &= h["animal_id"].isin(cow_ids)
            if event_types and "all" not in event_types and "health" not in event_types:
                mask &= h["event_type"].isin(event_types)
            for _, row in h[mask].iterrows():
                results.append({
                    "source": "health_events",
                    "evidence_id": str(row.get("event_id", "")),
                    "cow_id": str(row.get("animal_id", "")),
                    "date": str(row["event_date"].date()) if pd.notna(row["event_date"]) else "",
                    "type": str(row.get("event_type", "")),
                    "severity": str(row.get("severity", "")),
                    "notes": str(row.get("notes", "")),
                })

    # Treatments
    if not event_types or any(t in event_types for t in ("treatment", "all")):
        tr = store.treatments()
        if not tr.empty:
            t = tr.copy()
            t["start_date"] = pd.to_datetime(t["start_date"], errors="coerce")
            mask = (t["start_date"] >= date_from) & (t["start_date"] <= date_to)
            if cow_ids:
                mask &= t["animal_id"].isin(cow_ids)
            for _, row in t[mask].iterrows():
                results.append({
                    "source": "treatments",
                    "evidence_id": str(row.get("treatment_id", "")),
                    "cow_id": str(row.get("animal_id", "")),
                    "date": str(row["start_date"].date()) if pd.notna(row["start_date"]) else "",
                    "type": "treatment",
                    "treatment_type": str(row.get("treatment_type", "")),
                    "withdrawal_end": str(row.get("withdrawal_end_date", "")),
                })

    # Repro events
    repro_types = {"insemination", "calving", "repro"}
    if not event_types or any(t in event_types for t in repro_types | {"all"}):
        repro = store.repro_events()
        if not repro.empty:
            r = repro.copy()
            r["event_date"] = pd.to_datetime(r["event_date"], errors="coerce")
            mask = (r["event_date"] >= date_from) & (r["event_date"] <= date_to)
            if cow_ids:
                mask &= r["animal_id"].isin(cow_ids)
            if event_types and "all" not in event_types and "repro" not in event_types:
                mask &= r["event_type"].isin(event_types)
            for _, row in r[mask].iterrows():
                results.append({
                    "source": "repro_events",
                    "evidence_id": str(row.get("repro_event_id", "")),
                    "cow_id": str(row.get("animal_id", "")),
                    "date": str(row["event_date"].date()) if pd.notna(row["event_date"]) else "",
                    "type": str(row.get("event_type", "")),
                    "result": str(row.get("result", "")),
                    "notes": str(row.get("notes", "")),
                })

    results.sort(key=lambda e: e.get("date", ""), reverse=True)
    return {"rows": results[:limit], "total_found": len(results)}


def _exec_treatment_records(inp: dict, store: Any) -> dict:
    status = str(inp.get("status", "all")).lower()
    cow_ids = [str(c) for c in inp.get("cow_ids", [])] if inp.get("cow_ids") else []

    tr = store.treatments()
    if tr.empty:
        return {"rows": [], "status_filter": status}

    t = tr.copy()
    today = pd.Timestamp(datetime.date.today())
    t["start_date"] = pd.to_datetime(t["start_date"], errors="coerce")
    t["end_date"] = pd.to_datetime(t["end_date"], errors="coerce")
    t["withdrawal_end_date"] = pd.to_datetime(t["withdrawal_end_date"], errors="coerce")

    mask = pd.Series([True] * len(t), index=t.index)
    if cow_ids:
        mask &= t["animal_id"].isin(cow_ids)

    if status == "active":
        mask &= (t["start_date"] <= today) & (t["end_date"] >= today)
    elif status == "completed":
        mask &= t["end_date"] < today

    rows = []
    for _, row in t[mask].iterrows():
        wd = row.get("withdrawal_end_date")
        in_withdrawal = pd.notna(wd) and pd.Timestamp(wd) >= today if pd.notna(wd) else False
        rows.append({
            "treatment_id": str(row.get("treatment_id", "")),
            "cow_id": str(row.get("animal_id", "")),
            "start_date": str(row["start_date"].date()) if pd.notna(row["start_date"]) else "",
            "end_date": str(row["end_date"].date()) if pd.notna(row["end_date"]) else "",
            "treatment_type": str(row.get("treatment_type", "")),
            "reason_event_id": str(row.get("reason_event_id", "")),
            "withdrawal_end_date": str(wd.date()) if pd.notna(wd) else None,
            "in_withdrawal": bool(in_withdrawal),
            "evidence_id": str(row.get("treatment_id", "")),
        })

    return {"rows": rows, "status_filter": status, "count": len(rows)}


def _exec_reproduction_status(inp: dict, store: Any) -> dict:
    cow_ids = [str(c) for c in inp.get("cow_ids", [])] if inp.get("cow_ids") else []
    group_id = inp.get("group_id")

    animals = store.animals()
    repro = store.repro_events()
    milkings = store.milkings()

    # Resolve cow list
    if cow_ids:
        target_ids = cow_ids
    elif group_id and not animals.empty and "current_pen_id" in animals.columns:
        target_ids = animals[animals["current_pen_id"] == group_id]["animal_id"].tolist()
    else:
        target_ids = animals["animal_id"].tolist() if not animals.empty else []

    rows = []
    for cow_id in target_ids:
        rec: dict = {"cow_id": str(cow_id)}

        if not repro.empty:
            r = repro[repro["animal_id"] == cow_id].copy()
            r["event_date"] = pd.to_datetime(r["event_date"], errors="coerce")
            r = r.sort_values("event_date", ascending=False)

            last_heat = r[r["event_type"] == "heat"]
            rec["last_heat_date"] = str(last_heat.iloc[0]["event_date"].date()) if not last_heat.empty else None

            last_ins = r[r["event_type"] == "insemination"]
            rec["last_breeding_date"] = str(last_ins.iloc[0]["event_date"].date()) if not last_ins.empty else None

            preg = r[r["event_type"].isin(["preg_check", "preg_check_due"])]
            if not preg.empty:
                rec["preg_check_status"] = str(preg.iloc[0].get("result", "unknown"))
            else:
                rec["preg_check_status"] = None

        # DIM from latest milking
        if not milkings.empty:
            mk = milkings[milkings["animal_id"] == cow_id].copy()
            if not mk.empty:
                mk["date"] = pd.to_datetime(mk["date"], errors="coerce")
                latest_date = mk["date"].max()
                if pd.notna(latest_date):
                    today = pd.Timestamp(datetime.date.today())
                    rec["dim_approx"] = int((today - latest_date).days)

        rows.append(rec)

    return {
        "rows": rows,
        "group_id": group_id,
        "cow_count": len(rows),
    }


def _exec_milk_quality_trend(inp: dict, store: Any) -> dict:
    cow_id = inp.get("cow_id")
    group_id = inp.get("group_id")
    period = inp.get("period", "30d")
    days_back = int(str(period).rstrip("d")) if period else 30

    as_ts = pd.Timestamp(datetime.date.today())
    window = as_ts - pd.Timedelta(days=days_back)

    milkings = store.milkings()
    if milkings.empty:
        return {"rows": [], "cow_id": cow_id, "group_id": group_id, "period": period}

    mk = milkings.copy()
    mk["date"] = pd.to_datetime(mk["date"], errors="coerce")
    mask = mk["date"] >= window

    if cow_id:
        mask &= mk["animal_id"] == cow_id
    elif group_id:
        animals = store.animals()
        if not animals.empty and "current_pen_id" in animals.columns:
            group_cows = animals[animals["current_pen_id"] == group_id]["animal_id"].tolist()
            mask &= mk["animal_id"].isin(group_cows)

    subset = mk[mask].sort_values("date")
    cols = ["date", "animal_id", "milk_kg", "fat_pct", "protein_pct", "scc_cells_ml"]
    available = [c for c in cols if c in subset.columns]

    rows = []
    for _, row in subset[available].iterrows():
        entry = {c: (str(row[c].date()) if c == "date" and pd.notna(row[c]) else row.get(c)) for c in available}
        if "scc_cells_ml" in entry:
            entry["scc_k"] = round(float(entry["scc_cells_ml"]) / 1000, 1) if entry["scc_cells_ml"] else None
        rows.append(entry)

    return {
        "rows": rows,
        "cow_id": cow_id,
        "group_id": group_id,
        "period": period,
        "count": len(rows),
    }


def _exec_economics_snapshot(inp: dict, store: Any) -> dict:
    cow_id = inp.get("cow_id")

    econ = store.economics()
    prices = store.prices()
    milkings = store.milkings()

    if econ.empty:
        return {"cow_id": cow_id, "npv": None, "daily_cash_flow": None, "note": "no economics data"}

    ec = econ.copy()
    ec["date"] = pd.to_datetime(ec["date"], errors="coerce")
    latest = ec.sort_values("date", ascending=False).head(1).iloc[0]

    milk_price = float(latest.get("milk_price_per_kg", 0.5))
    feed_cost = float(latest.get("feed_cost_per_kg_dm", 0.3))
    other_cost = float(latest.get("other_cost_eur", 0))

    if cow_id and not milkings.empty:
        mk = milkings[milkings["animal_id"] == cow_id].copy()
        if not mk.empty:
            avg_yield = float(mk["milk_kg"].mean())
            daily_revenue = avg_yield * milk_price
            daily_feed_cost = avg_yield * 0.4 * feed_cost  # rough DMI estimate
            daily_cf = daily_revenue - daily_feed_cost - other_cost / max(len(milkings["animal_id"].unique()), 1)
            npv_30d = daily_cf * 30
            return {
                "cow_id": cow_id,
                "avg_yield_kg": round(avg_yield, 2),
                "milk_price_per_kg": milk_price,
                "daily_revenue_eur": round(daily_revenue, 2),
                "daily_cash_flow_eur": round(daily_cf, 2),
                "npv_30d_eur": round(npv_30d, 2),
                "break_even_yield_kg": round((daily_feed_cost + other_cost / max(len(milkings["animal_id"].unique()), 1)) / milk_price, 2) if milk_price else None,
                "evidence_id": str(latest.get("record_id", "")),
            }

    # Farm-level
    if not milkings.empty:
        avg_yield = float(milkings["milk_kg"].mean()) if "milk_kg" in milkings else 0.0
    else:
        avg_yield = 0.0
    n_cows = len(milkings["animal_id"].unique()) if not milkings.empty else 1
    farm_daily_revenue = avg_yield * n_cows * milk_price
    farm_daily_cost = avg_yield * n_cows * 0.4 * feed_cost + other_cost
    return {
        "cow_id": None,
        "farm_avg_yield_kg": round(avg_yield, 2),
        "n_cows_sampled": int(n_cows),
        "milk_price_per_kg": milk_price,
        "farm_daily_revenue_eur": round(farm_daily_revenue, 2),
        "farm_daily_cost_eur": round(farm_daily_cost, 2),
        "farm_daily_margin_eur": round(farm_daily_revenue - farm_daily_cost, 2),
        "evidence_id": str(latest.get("record_id", "")),
    }


# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------

def _filter_df(
    df: pd.DataFrame,
    id_col: str,
    id_val: str,
    date_col: Optional[str] = None,
    date_from: Optional[Any] = None,
) -> pd.DataFrame:
    if df.empty:
        return df
    mask = df[id_col] == id_val
    if date_col and date_from is not None and date_col in df.columns:
        df = df.copy()
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        mask &= df[date_col] >= pd.Timestamp(date_from)
    return df[mask]


def _df_to_records(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    return [
        {k: (str(v) if isinstance(v, pd.Timestamp) else v) for k, v in row.items()}
        for row in df.to_dict("records")
    ]


def _exec_analyze_event_impact(inp: dict, store: Any) -> dict:
    """P1-1 Task 2.1 — delegates to compute_event_impact."""
    from .endpoints.impact_narrative import compute_event_impact
    event_id = str(inp["event_id"])
    kpi = str(inp.get("kpi", "milk_kg"))
    window_days = int(inp.get("window_days", 14))
    farm_id = str(inp.get("farm_id", "demo-farm-v1"))
    return compute_event_impact(event_id=event_id, kpi=kpi, window_days=window_days, farm_id=farm_id)


def _exec_find_attention_cows(inp: dict, store: Any) -> dict:
    """P1-1 Task 2.2 — TOP-N cows by combined attention score.

    Score components:
      +min(scc/200000, 5.0)       if SCC > 200k (latest milking record)
      +1.0                         if BCS < 2.5 or > 4.0 (if column exists)
      +2.0                         if explicit attention flag (if column exists)
      +1.5                         if active treatment exists (start <= today <= end)
      +1.5                         if recent 7d milk delta < -10%

    Returns sorted top-N with reasons[] explaining the score.
    """
    n = max(1, min(50, int(inp.get("threshold_count", 10))))
    df_animals = store.animals()
    if df_animals is None or df_animals.empty:
        return {"cows": [], "total_scored": 0, "evidence_chips": []}

    df_milkings = store.milkings()
    df_treatments = store.treatments()

    today_ts = pd.Timestamp(datetime.date.today())

    scored: list[dict] = []
    for _, row in df_animals.iterrows():
        cow_id = str(row.get("animal_id"))
        score = 0.0
        reasons: list[str] = []

        # SCC component + 7-day milk delta
        if df_milkings is not None and not df_milkings.empty:
            cow_milk = df_milkings[df_milkings["animal_id"] == cow_id].copy()
            if not cow_milk.empty:
                cow_milk["date"] = pd.to_datetime(cow_milk["date"], errors="coerce")
                cow_milk = cow_milk.sort_values("date")

                # Latest SCC
                if "scc_cells_ml" in cow_milk.columns:
                    latest_scc = float(cow_milk.iloc[-1].get("scc_cells_ml", 0) or 0)
                    if latest_scc > 200_000:
                        inc = min(latest_scc / 200_000.0, 5.0)
                        score += inc
                        reasons.append(f"SCC {int(latest_scc):,}")

                # 7-day milk delta: compare avg of last 7 vs prior 7
                if "milk_kg" in cow_milk.columns and len(cow_milk) >= 7:
                    last_7 = cow_milk.tail(7)["milk_kg"].astype(float)
                    prior = cow_milk.iloc[-14:-7]["milk_kg"].astype(float) if len(cow_milk) >= 14 else None
                    if prior is not None and not prior.empty and prior.mean() > 0:
                        delta_pct = (last_7.mean() - prior.mean()) / prior.mean() * 100
                        if delta_pct < -10:
                            score += 1.5
                            reasons.append(f"надой -{abs(delta_pct):.0f}% (7д)")

        # BCS component (column may not exist in all fixtures)
        bcs_val = row.get("bcs") if "bcs" in df_animals.columns else None
        if bcs_val is not None:
            try:
                bcs = float(bcs_val)
                if bcs < 2.5 or bcs > 4.0:
                    score += 1.0
                    reasons.append(f"BCS {bcs}")
            except (TypeError, ValueError):
                pass

        # Explicit attention flag (column may not exist)
        if "attention" in df_animals.columns:
            attention = row.get("attention", False)
            if bool(attention):
                score += 2.0
                reasons.append("flag: attention")

        # Active treatment: start_date <= today <= end_date
        if df_treatments is not None and not df_treatments.empty:
            tr = df_treatments[df_treatments["animal_id"] == cow_id].copy()
            if not tr.empty:
                tr["start_date"] = pd.to_datetime(tr["start_date"], errors="coerce")
                tr["end_date"] = pd.to_datetime(tr["end_date"], errors="coerce")
                active = tr[(tr["start_date"] <= today_ts) & (tr["end_date"] >= today_ts)]
                if not active.empty:
                    score += 1.5
                    reasons.append("активное лечение")

        if score > 0:
            scored.append({"cow_id": cow_id, "score": round(score, 2), "reasons": reasons})

    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[:n]
    return {
        "cows": top,
        "total_scored": len(scored),
        "evidence_chips": [{"type": "cow", "id": c["cow_id"]} for c in top],
    }


def _exec_calculate_cull_npv(inp: dict, store: Any) -> dict:
    """P1-1 Task 2.3 stub. Full NPV_keep vs NPV_cull comes in P1-2."""
    animal_id = str(inp["animal_id"])
    snapshot = _exec_economics_snapshot({"cow_id": animal_id}, store)
    return {
        "animal_id": animal_id,
        "npv_snapshot": snapshot,
        "p1_1_stub": True,
        "note": "Полная модель NPV_keep vs NPV_cull появится в P1-2.",
        "evidence_chips": [{"type": "cow", "id": animal_id}],
    }


def _exec_forecast_milk_yield(inp: dict, store: Any) -> dict:
    """P1-1 Task 2.4 — linear regression on DIM (minimal model)."""
    import numpy as np

    animal_id = inp.get("animal_id")
    group_id = inp.get("group_id")
    horizon = int(inp.get("horizon_days", 7))
    horizon = max(7, min(30, horizon))

    if not animal_id and not group_id:
        return {"error": "either animal_id or group_id required"}

    df_milk = store.milkings()
    if df_milk is None or df_milk.empty:
        return {"error": "no milking data", "horizon_days": horizon, "forecast": []}

    if animal_id:
        cow_milk = df_milk[df_milk["animal_id"] == str(animal_id)].copy()
    else:
        # Group-level: resolve cows by pen/group column.
        df_animals = store.animals()
        if df_animals is None or df_animals.empty:
            return {"error": "no animals data for group", "horizon_days": horizon, "forecast": []}
        group_col = "current_pen_id" if "current_pen_id" in df_animals.columns else "group_id"
        cow_ids = df_animals[df_animals[group_col] == str(group_id)]["animal_id"].astype(str).tolist()
        cow_milk = df_milk[df_milk["animal_id"].astype(str).isin(cow_ids)].copy()

    if cow_milk.empty or len(cow_milk) < 3:
        return {"error": "need >= 3 milk records", "horizon_days": horizon, "forecast": []}

    # Compute DIM as days from earliest record in this cow's history.
    cow_milk["date"] = pd.to_datetime(cow_milk["date"], errors="coerce")
    cow_milk = cow_milk.sort_values("date")
    earliest = cow_milk["date"].min()
    cow_milk["dim"] = (cow_milk["date"] - earliest).dt.days

    x = cow_milk["dim"].astype(float).to_numpy()
    y = cow_milk["milk_kg"].astype(float).to_numpy()
    slope, intercept = np.polyfit(x, y, 1)
    last_dim = float(x.max())
    forecast = [
        {"dim": int(last_dim + d), "milk_kg": round(float(slope * (last_dim + d) + intercept), 2)}
        for d in range(1, horizon + 1)
    ]
    chips = [{"type": "cow" if animal_id else "group", "id": str(animal_id or group_id)}]
    return {
        "animal_id": animal_id,
        "group_id": group_id,
        "horizon_days": horizon,
        "forecast": forecast,
        "method": "linear_regression_dim",
        "slope_per_day": round(float(slope), 4),
        "evidence_chips": chips,
    }
