"""Farm context builder — full implementation (MVP-N12)."""
from __future__ import annotations

import datetime
import json
from typing import Any, Optional

import pandas as pd

try:
    import tiktoken
    _enc = tiktoken.get_encoding("cl100k_base")

    def _count_tokens(text: str) -> int:
        return len(_enc.encode(text))
except Exception:
    def _count_tokens(text: str) -> int:  # type: ignore[misc]
        return max(1, len(text) // 4)


# ---------------------------------------------------------------------------
# Legacy FarmContext (used by existing endpoints/tests — keep as-is)
# ---------------------------------------------------------------------------

class FarmContext:
    """Снимок состояния фермы для инъекции в LLM-промпты."""

    def __init__(
        self,
        farm_id: str,
        kpi: Optional[Any] = None,
        active_insights: Optional[list] = None,
        recent_events: Optional[list] = None,
        herd_summary: Optional[dict] = None,
        sensor_anomalies: Optional[list] = None,
        attention_cows: Optional[list] = None,
    ) -> None:
        self.farm_id = farm_id
        self.kpi = kpi
        self.active_insights = active_insights or []
        self.recent_events = recent_events or []
        self.herd_summary = herd_summary or {}
        self.sensor_anomalies = sensor_anomalies
        self.attention_cows = attention_cows or []

    def to_text(self, max_chars: int = 3000) -> str:
        parts = [f"Ферма: {self.farm_id}"]
        if self.herd_summary:
            parts.append(f"Стадо: {json.dumps(self.herd_summary, ensure_ascii=False)}")
        if self.kpi:
            parts.append(f"KPI: {json.dumps(self.kpi, ensure_ascii=False)}")
        if self.active_insights:
            parts.append(f"Активные инсайты: {json.dumps(self.active_insights, ensure_ascii=False)}")
        if self.recent_events:
            parts.append(f"Последние события: {json.dumps(self.recent_events, ensure_ascii=False)}")
        text = "\n".join(parts)
        if len(text) > max_chars:
            suffix = "\n...[усечён]"
            text = text[:max(0, max_chars - len(suffix))] + suffix
        return text


# ---------------------------------------------------------------------------
# Full build_farm_context (N12)
# ---------------------------------------------------------------------------

def build_farm_context(
    farm_id: str,
    db: Any = None,
    *,
    settings: Any = None,
    store: Any = None,
    include_cow_details: bool = False,
    specific_cow_ids: Optional[list[str]] = None,
    period_days: int = 7,
) -> Any:
    """
    Build farm snapshot for Claude injection.

    Parameters
    ----------
    farm_id:
        Farm identifier (e.g. "demo-farm-v1" or a real UUID).
    db:
        SQLAlchemy session for production Postgres queries (not yet wired in N12).
    store:
        DemoDataStore instance. If None, a new store is created from the demo CSV files.
    include_cow_details:
        If True, add full_profile for specific_cow_ids.
    specific_cow_ids:
        List of cow IDs to include full profiles for.
    period_days:
        KPI comparison window in days.

    Returns
    -------
    dict with keys: farm_summary, today_kpi, period_trends, active_insights,
    recent_events, attention_cows, groups_summary, [full_profiles], token_count.
    """
    # Settings-based dispatch: real bridge mode vs legacy demo/dict mode
    if settings is not None:
        if settings.GENOMEAI_AI_DEMO_MODE:
            return _build_seeded_context(farm_id)
        return _build_bridge_context(farm_id)

    from web_cabinet.ai.context_helpers.demo_loader import DemoDataStore
    from web_cabinet.ai.context_helpers.kpi import compute_today_kpi, compute_period_trends
    from web_cabinet.ai.context_helpers.attention import flag_attention_cows

    if store is None:
        store = DemoDataStore()

    as_of = _detect_data_as_of(store) or datetime.date.today()

    # ---- farm_summary ----
    animals = store.animals()
    total_cows = len(animals)
    active_cows = len(animals[animals.get("status", pd.Series(["active"] * len(animals))) == "active"]) if not animals.empty else 0
    # If status col missing, treat all as active
    if "status" not in animals.columns:
        active_cows = total_cows

    farms_df = store.farms()
    farm_name = farm_id
    if not farms_df.empty and "farm_name" in farms_df.columns:
        row = farms_df.iloc[0]
        farm_name = str(row.get("farm_name", farm_id))

    farm_summary = {
        "farm_id": farm_id,
        "name": farm_name,
        "total_cows": int(total_cows),
        "active_cows_count": int(active_cows),
        "date_as_of": as_of.isoformat(),
    }

    # ---- today_kpi ----
    today_kpi = compute_today_kpi(store, farm_id, as_of)

    # ---- period_trends ----
    period_trends = compute_period_trends(store, farm_id, as_of, period_days)

    # ---- active_insights (from alerts) ----
    active_insights = _build_active_insights(store)

    # ---- recent_events ----
    recent_events = _build_recent_events(store, as_of, period_days)

    # ---- attention_cows ----
    attention_cows = flag_attention_cows(store, farm_id, as_of, period_days)

    # ---- groups_summary (by pen) ----
    groups_summary = _build_groups_summary(store)

    ctx: dict = {
        "farm_summary": farm_summary,
        "today_kpi": today_kpi,
        "period_trends": period_trends,
        "active_insights": active_insights,
        "recent_events": recent_events,
        "attention_cows": attention_cows,
        "groups_summary": groups_summary,
    }

    # ---- optional full_profiles ----
    if include_cow_details and specific_cow_ids:
        ctx["full_profiles"] = {
            cow_id: _build_cow_profile(store, cow_id, days_back=period_days * 4)
            for cow_id in specific_cow_ids
        }

    # ---- token count ----
    ctx_text = json.dumps(ctx, ensure_ascii=False, default=str)
    ctx["token_count"] = _count_tokens(ctx_text)

    return ctx


# ---------------------------------------------------------------------------
# Settings-dispatch helpers
# ---------------------------------------------------------------------------

def _build_seeded_context(farm_id: str) -> FarmContext:
    """Demo mode: return the hardcoded seeded FarmContext (no bridges called)."""
    ctx = build_demo_farm_context()
    ctx.farm_id = farm_id
    return ctx


def _build_bridge_context(farm_id: str) -> FarmContext:
    """Real mode: assemble FarmContext from kpi_bridge, alerts_bridge, sensor_bridge."""
    from datetime import date as _date

    from web_cabinet.analytics.kpi_bridge import compute_dashboard_kpi
    from web_cabinet.analytics.alerts_bridge import list_active_alerts
    from web_cabinet.analytics.sensor_bridge import detect_recent_sensor_anomalies

    kpi = compute_dashboard_kpi(farm_id, _date.today())
    alerts = list_active_alerts(farm_id)
    sensor_anomalies = detect_recent_sensor_anomalies(farm_id, lookback_days=14)

    return FarmContext(
        farm_id=farm_id,
        kpi=kpi,
        active_insights=alerts,
        sensor_anomalies=sensor_anomalies,
        recent_events=_query_recent_events(farm_id, days=14),
        attention_cows=_query_attention_cows(farm_id),
    )


def _query_recent_events(farm_id: str, days: int = 14) -> list:
    """Stub: returns DB events when DB is wired; empty list until then."""
    return []


def _query_attention_cows(farm_id: str) -> list:
    """Stub: returns DB-queried attention cows; empty list until DB is wired."""
    return []


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _detect_data_as_of(store: Any) -> Optional[datetime.date]:
    """Returns max date found in milkings or health_events; None if data is empty."""
    import pandas as pd
    candidates: list[datetime.date] = []
    for getter, col in [("milkings", "date"), ("health_events", "event_date")]:
        try:
            df = getattr(store, getter)()
            if not df.empty and col in df.columns:
                max_ts = pd.to_datetime(df[col], errors="coerce").max()
                if pd.notna(max_ts):
                    candidates.append(max_ts.date())
        except Exception:
            pass
    return max(candidates) if candidates else None


def _build_active_insights(store: Any) -> list[dict]:
    alerts = store.alerts()
    if alerts.empty:
        return []
    result = []
    priority_map = {"high": "high", "critical": "critical", "warn": "medium", "info": "low"}
    for _, row in alerts.iterrows():
        sev = str(row.get("severity", "info")).lower()
        if sev in ("info",):
            continue  # skip low-priority for context brevity
        result.append({
            "id": str(row.get("alert_id", "")),
            "priority": priority_map.get(sev, "medium"),
            "description": str(row.get("message", "")),
            "entity_id": str(row.get("entity_id", "")),
            "status": "to_check",
        })
    return result[:10]


def _build_recent_events(
    store: Any,
    as_of: datetime.date,
    period_days: int,
) -> list[dict]:
    as_ts = pd.Timestamp(as_of)
    window_start = as_ts - pd.Timedelta(days=period_days)
    events: list[dict] = []

    he = store.health_events()
    if not he.empty:
        he = he.copy()
        he["event_date"] = pd.to_datetime(he["event_date"], errors="coerce")
        recent_he = he[he["event_date"] >= window_start].sort_values("event_date", ascending=False)
        for _, row in recent_he.head(20).iterrows():
            events.append({
                "date": str(row["event_date"].date()) if pd.notna(row["event_date"]) else "",
                "type": str(row.get("event_type", "")),
                "title": str(row.get("notes", row.get("event_type", ""))),
                "cow_id": str(row.get("animal_id", "")),
                "evidence_id": str(row.get("event_id", "")),
            })

    tr = store.treatments()
    if not tr.empty:
        tr = tr.copy()
        tr["start_date"] = pd.to_datetime(tr["start_date"], errors="coerce")
        recent_tr = tr[tr["start_date"] >= window_start].sort_values("start_date", ascending=False)
        for _, row in recent_tr.head(10).iterrows():
            events.append({
                "date": str(row["start_date"].date()) if pd.notna(row["start_date"]) else "",
                "type": "treatment",
                "title": str(row.get("treatment_type", "лечение")),
                "cow_id": str(row.get("animal_id", "")),
                "evidence_id": str(row.get("treatment_id", "")),
            })

    repro = store.repro_events()
    if not repro.empty:
        repro = repro.copy()
        repro["event_date"] = pd.to_datetime(repro["event_date"], errors="coerce")
        recent_repro = repro[repro["event_date"] >= window_start].sort_values("event_date", ascending=False)
        for _, row in recent_repro.head(10).iterrows():
            events.append({
                "date": str(row["event_date"].date()) if pd.notna(row["event_date"]) else "",
                "type": str(row.get("event_type", "")),
                "title": str(row.get("notes", row.get("event_type", ""))),
                "cow_id": str(row.get("animal_id", "")),
                "evidence_id": str(row.get("repro_event_id", "")),
            })

    # Sort by date desc, limit to 50
    events.sort(key=lambda e: e.get("date", ""), reverse=True)
    return events[:50]


def _build_groups_summary(store: Any) -> list[dict]:
    pens = store.pens()
    animals = store.animals()
    milkings = store.milkings()

    if pens.empty or animals.empty:
        return []

    result = []
    for _, pen in pens.iterrows():
        pen_id = str(pen.get("pen_id", ""))
        pen_name = str(pen.get("pen_name", pen_id))

        if "current_pen_id" in animals.columns:
            pen_animals = animals[animals["current_pen_id"] == pen_id]
        else:
            pen_animals = pd.DataFrame()

        cow_count = len(pen_animals)
        avg_yield = 0.0

        if not milkings.empty and not pen_animals.empty and "milk_kg" in milkings.columns:
            pen_mk = milkings[milkings["animal_id"].isin(pen_animals["animal_id"])]
            if not pen_mk.empty:
                avg_yield = float(pen_mk["milk_kg"].mean())

        result.append({
            "group_id": pen_id,
            "group_name": pen_name,
            "cow_count": int(cow_count),
            "avg_yield": round(avg_yield, 2),
            "health_status_summary": "ok",
        })

    return result


def _build_cow_profile(store: Any, cow_id: str, days_back: int = 30) -> dict:
    """Full profile for a specific cow (used when specific_cow_ids requested)."""
    as_ts = pd.Timestamp(datetime.date.today())
    window = as_ts - pd.Timedelta(days=days_back)

    milkings = store.milkings()
    cow_mk: list[dict] = []
    if not milkings.empty:
        mk = milkings.copy()
        mk["date"] = pd.to_datetime(mk["date"], errors="coerce")
        cow_mk = (
            mk[(mk["animal_id"] == cow_id) & (mk["date"] >= window)]
            .sort_values("date")
            .to_dict("records")
        )

    he = store.health_events()
    cow_he: list[dict] = []
    if not he.empty:
        h = he.copy()
        h["event_date"] = pd.to_datetime(h["event_date"], errors="coerce")
        cow_he = (
            h[(h["animal_id"] == cow_id) & (h["event_date"] >= window)]
            .sort_values("event_date")
            .to_dict("records")
        )

    tr = store.treatments()
    cow_tr: list[dict] = []
    if not tr.empty:
        t = tr.copy()
        t["start_date"] = pd.to_datetime(t["start_date"], errors="coerce")
        cow_tr = (
            t[(t["animal_id"] == cow_id) & (t["start_date"] >= window)]
            .sort_values("start_date")
            .to_dict("records")
        )

    return {
        "cow_id": cow_id,
        "milkings": cow_mk,
        "health_events": cow_he,
        "treatments": cow_tr,
    }


# ---------------------------------------------------------------------------
# Legacy demo context — kept for backward-compat
# ---------------------------------------------------------------------------

def build_demo_farm_context() -> FarmContext:
    """Демо-контекст (legacy). Используется там, где ещё ожидается FarmContext."""
    return FarmContext(
        farm_id="demo-farm-v1",
        herd_summary={
            "total_cows": 350,
            "lactating": 285,
            "dry": 45,
            "heifers": 20,
        },
        kpi={
            "avg_milk_yield_kg": 28.4,
            "scc_avg": 215000,
            "conception_rate_pct": 42,
            "culling_rate_pct": 18,
        },
        active_insights=[
            {
                "id": "insight_001",
                "type": "mastitis_risk",
                "cow_id": "4821",
                "name": "Звёздочка",
                "scc_trend": [230000, 310000, 450000],
                "days": 9,
                "severity": "critical",
            }
        ],
        recent_events=[
            {
                "event_id": "event_4821_scc_spike",
                "type": "scc_spike",
                "cow_id": "4821",
                "date": "2026-04-19",
                "value": 450000,
            },
            {
                "event_id": "event_heat_batch_20260421",
                "type": "heat_detected",
                "count": 8,
                "date": "2026-04-21",
            },
        ],
    )
