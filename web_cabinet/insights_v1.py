from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from packages.contracts.api_boundary_v1 import (
    InsightItem,
    InsightRecommendation,
    InsightsListResponse,
    InsightTransitionRequest,
)
from core.infra.web_db import get_settings


def _demo_seed_path() -> Path:
    settings = get_settings()
    return settings.project_root / 'data' / 'demo' / 'investor_v1' / 'insights_seeded.json'


def _load_demo_insights() -> list[dict[str, Any]]:
    path = _demo_seed_path()
    if not path.exists():
        return []
    with path.open('r', encoding='utf-8') as f:
        return json.load(f)


_DEMO_STATUSES: dict[str, str] = {
    'INS_001': 'to_check',
    'INS_002': 'to_check',
    'INS_003': 'to_check',
    'INS_004': 'done',
    'INS_005': 'to_check',
    'INS_006': 'to_follow_up',
    'INS_007': 'to_check',
    'INS_008': 'done',
    'INS_009': 'to_follow_up',
    'INS_010': 'to_follow_up',
    'INS_011': 'done',
    'INS_012': 'to_follow_up',
}

_in_memory_statuses: dict[str, str] = dict(_DEMO_STATUSES)


def _build_insight_item(raw: dict[str, Any]) -> InsightItem:
    iid = raw.get('insight_id', '')
    return InsightItem(
        insight_id=iid,
        type=raw.get('type', ''),
        severity=raw.get('severity', 'info'),
        status=_in_memory_statuses.get(iid, 'to_check'),
        date=raw.get('date', ''),
        animal_ids=raw.get('animal_ids', []),
        title=raw.get('title', ''),
        body=raw.get('body', ''),
        action=raw.get('action', ''),
        tags=raw.get('tags', []),
        farm_label='Демо-ферма',
        recommendations=[],
    )


def list_insights(status: Optional[str] = None) -> InsightsListResponse:
    raws = _load_demo_insights()
    items = [_build_insight_item(r) for r in raws]
    if status:
        items = [i for i in items if i.status == status]
    return InsightsListResponse(total=len(items), items=items)


def get_insight(insight_id: str) -> Optional[InsightItem]:
    raws = _load_demo_insights()
    for raw in raws:
        if raw.get('insight_id') == insight_id:
            return _build_insight_item(raw)
    return None


def transition_insight(insight_id: str, new_status: str) -> Optional[InsightItem]:
    allowed = {'to_check', 'to_follow_up', 'done'}
    if new_status not in allowed:
        return None
    raws = _load_demo_insights()
    found = next((r for r in raws if r.get('insight_id') == insight_id), None)
    if not found:
        return None
    _in_memory_statuses[insight_id] = new_status
    return _build_insight_item(found)
