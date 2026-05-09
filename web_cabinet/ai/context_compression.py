"""§3.2.1 farm-context compression — explicit 0/1-knapsack by value-density.

Thesis formula 3.5: select segments maximising Σ w_i·x_i subject to Σ t_i·x_i ≤ B,
solved with the standard greedy heuristic on density w_i / t_i (table 3.2.1).

Token estimate (cyrillic-aware): t_i ≈ |c_i| / 2.5 + 8.

Category weights (§3.2.1):
  1.0 — KPI хозяйства (надой, жирность, SCC, выбраковка)
  0.9 — attention cows (хромота, мастит, низкий надой)
  0.7 — события за последние 7 дней
  0.5 — средняя группа коров / full profile
  0.4 — когортные сводки + сезонные тренды
  0.2 — события давности 7-30 дней
"""
from __future__ import annotations

import dataclasses
import datetime
import json
import math
from typing import Any, Optional


CATEGORY_WEIGHTS: dict[str, float] = {
    "farm_summary":     1.0,
    "today_kpi":        1.0,
    "period_trends":    0.4,
    "active_insights":  0.4,
    "attention_cow":    0.9,
    "recent_event_7d":  0.7,
    "recent_event_30d": 0.2,
    "groups_summary":   0.5,
    "full_profile":     0.5,
}


@dataclasses.dataclass(frozen=True)
class Segment:
    name: str            # category label, e.g. "today_kpi" or "attention_cow:3891"
    weight: float        # priority per §3.2.1 table 3.2.1
    content: Any         # JSON-serialisable payload
    token_estimate: int  # cached cyrillic-aware estimate


def estimate_tokens(content: Any) -> int:
    """Cyrillic-aware token estimate per thesis §3.2.1: |c| / 2.5 + 8.

    Rounds up since tokenizers split partial syllables; floor would
    systematically under-budget for short strings.
    """
    if isinstance(content, str):
        text = content
    else:
        text = json.dumps(content, ensure_ascii=False, default=str)
    return math.ceil(len(text) / 2.5) + 8


def _segment(name: str, weight: float, content: Any) -> Segment:
    return Segment(
        name=name, weight=weight, content=content,
        token_estimate=estimate_tokens(content),
    )


def _event_date(event: dict) -> Optional[datetime.date]:
    raw = event.get("event_date") or event.get("date")
    if not raw:
        return None
    try:
        return datetime.date.fromisoformat(str(raw)[:10])
    except (TypeError, ValueError):
        return None


def segment_farm_context(
    ctx: dict, *, as_of: Optional[datetime.date] = None
) -> list[Segment]:
    """Split a built farm-context dict into knapsack-ready segments.

    Cell-cohesive top-level keys (farm_summary, today_kpi, period_trends,
    active_insights, groups_summary) become one segment each. attention_cows
    splits per cow (weight 0.9). recent_events split by age:
    ≤7 days → 0.7, 7–30 days → 0.2. full_profiles split per cow.
    """
    today = as_of or datetime.date.today()
    out: list[Segment] = []

    for key in ("farm_summary", "today_kpi", "period_trends",
                "active_insights", "groups_summary"):
        if ctx.get(key) is None:
            continue
        out.append(_segment(key, CATEGORY_WEIGHTS[key], ctx[key]))

    for cow in ctx.get("attention_cows") or []:
        cid = str(cow.get("animal_id") or cow.get("cow_id") or cow.get("id") or "?")
        out.append(_segment(
            f"attention_cow:{cid}", CATEGORY_WEIGHTS["attention_cow"], cow,
        ))

    for ev in ctx.get("recent_events") or []:
        eid = str(ev.get("event_id") or ev.get("id") or "?")
        d = _event_date(ev)
        age_days = (today - d).days if d else 0
        if age_days <= 7:
            out.append(_segment(
                f"recent_event_7d:{eid}", CATEGORY_WEIGHTS["recent_event_7d"], ev,
            ))
        else:
            out.append(_segment(
                f"recent_event_30d:{eid}", CATEGORY_WEIGHTS["recent_event_30d"], ev,
            ))

    for cow_id, profile in (ctx.get("full_profiles") or {}).items():
        out.append(_segment(
            f"full_profile:{cow_id}", CATEGORY_WEIGHTS["full_profile"], profile,
        ))

    return out


def reconstruct_ctx(kept: list[Segment]) -> dict:
    """Aggregate kept segments back into the dict shape build_farm_context returns."""
    out: dict[str, Any] = {}
    attention: list = []
    events: list = []
    profiles: dict = {}
    for s in kept:
        if s.name.startswith("attention_cow:"):
            attention.append(s.content)
        elif s.name.startswith("recent_event_7d:") or s.name.startswith("recent_event_30d:"):
            events.append(s.content)
        elif s.name.startswith("full_profile:"):
            cow_id = s.name.split(":", 1)[1]
            profiles[cow_id] = s.content
        else:
            out[s.name] = s.content
    if attention:
        out["attention_cows"] = attention
    if events:
        out["recent_events"] = events
    if profiles:
        out["full_profiles"] = profiles
    return out


def compression_stats(kept: list[Segment], *, budget: int) -> dict:
    """Produce the compression_stats sidecar for the API response."""
    by_cat: dict[str, int] = {}
    for s in kept:
        prefix = s.name.split(":", 1)[0]
        by_cat[prefix] = by_cat.get(prefix, 0) + 1
    return {
        "budget_tokens":   int(budget),
        "used_tokens":     int(sum(s.token_estimate for s in kept)),
        "kept_segments":   len(kept),
        "segments_by_category": by_cat,
    }


def compress_farm_context(
    segments: list[Segment], *, budget: int = 3000
) -> list[Segment]:
    """Greedy 0/1-knapsack by value-density (weight / token_estimate).

    Sort segments by w_i / t_i desc, walk in order, take each that fits.
    Equivalent to the textbook fractional-knapsack heuristic; for
    integer-only items (segments are atomic) this is the standard
    greedy approximation used in §3.2.1.
    """
    ordered = sorted(
        segments,
        key=lambda s: s.weight / max(1, s.token_estimate),
        reverse=True,
    )
    kept: list[Segment] = []
    used = 0
    for s in ordered:
        if used + s.token_estimate <= budget:
            kept.append(s)
            used += s.token_estimate
    return kept
