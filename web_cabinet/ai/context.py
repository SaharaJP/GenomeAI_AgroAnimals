"""Farm context builder — skeleton, расширяется в N12."""
from __future__ import annotations

import json
from typing import Any, Optional


class FarmContext:
    """Снимок состояния фермы для инъекции в LLM-промпты."""

    def __init__(
        self,
        farm_id: str,
        kpi: Optional[dict] = None,
        active_insights: Optional[list] = None,
        recent_events: Optional[list] = None,
        herd_summary: Optional[dict] = None,
    ) -> None:
        self.farm_id = farm_id
        self.kpi = kpi or {}
        self.active_insights = active_insights or []
        self.recent_events = recent_events or []
        self.herd_summary = herd_summary or {}

    def to_text(self, max_chars: int = 3000) -> str:
        """Сериализует контекст в текст для system prompt."""
        parts = [
            f"Ферма: {self.farm_id}",
        ]
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


def build_farm_context(
    farm_id: str,
    db: Any = None,
    *,
    include_kpi: bool = True,
    include_insights: bool = True,
    include_events: bool = True,
    event_limit: int = 20,
) -> FarmContext:
    """Собирает farm_context из БД. Skeleton — реальные запросы добавляются в N12."""
    # N12: здесь будут запросы к DB для реальных данных фермы
    return FarmContext(
        farm_id=farm_id,
        kpi={},
        active_insights=[],
        recent_events=[],
        herd_summary={},
    )


def build_demo_farm_context() -> FarmContext:
    """Демо-контекст с реалистичными данными для инвесторского показа."""
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
