"""GET /api/animals/{animal_id}/cull-recommendation — thesis §3.1.6 endpoint #5.

Implements the full §3.2.4 NPV cull/keep decision via web_cabinet/ai/npv_cull.py.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ..ai.context_helpers.demo_loader import DemoDataStore
from ..ai.npv_cull import recommend
from ..rbac import require_permissions

logger = logging.getLogger("genomeai.animals.cull_recommendation")

router = APIRouter(prefix="/api/animals", tags=["animals"])

_STORE: DemoDataStore | None = None


def _get_store() -> DemoDataStore:
    global _STORE
    if _STORE is None:
        _STORE = DemoDataStore()
    return _STORE


@router.get("/{animal_id}/cull-recommendation")
def cull_recommendation(
    animal_id: str,
    user=Depends(require_permissions("kpi.view")),
) -> dict[str, Any]:
    """Return §3.2.4 NPV cull/keep recommendation for the given animal.

    404 if animal not found in DemoDataStore (canonical investor_v1 dataset).
    Requires kpi.view permission.
    """
    store = _get_store()
    df = store.animals()
    if df is None or df.empty:
        raise HTTPException(
            status_code=404,
            detail={"error": "animal_not_found", "animal_id": animal_id},
        )
    if str(animal_id) not in df["animal_id"].astype(str).tolist():
        raise HTTPException(
            status_code=404,
            detail={"error": "animal_not_found", "animal_id": animal_id},
        )
    return recommend(animal_id=str(animal_id), store=store)
