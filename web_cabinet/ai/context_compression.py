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
import json
import math
from typing import Any


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
