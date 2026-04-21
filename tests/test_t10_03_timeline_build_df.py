from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd


def test_timeline_build_df_includes_overlays_and_is_sorted():
    """T10-03: timeline = fact events + tasks + decisions (no recalculation)."""

    from streamlit_app.components.timeline_v1 import build_timeline_df

    now = datetime(2026, 2, 8, 12, 0, 0)

    events = pd.DataFrame(
        [
            {"date": (now - timedelta(days=2)).isoformat(), "category": "milk", "event_type": "milk", "details": "yield=32"},
            {"date": (now - timedelta(days=1)).isoformat(), "category": "health", "event_type": "mastitis", "details": "suspected"},
        ]
    )

    tasks = [
        {
            "task_id": "t1",
            "title": "Check cow",
            "priority": 2,
            "status": "open",
            "created_at": (now - timedelta(hours=1)).isoformat(),
        }
    ]

    decisions = [
        {
            "decision_id": "d1",
            "action": "recommendation.confirm",
            "reason": "ok",
            "created_at": (now - timedelta(hours=2)).isoformat(),
        }
    ]

    df = build_timeline_df(events=events, tasks=tasks, decisions=decisions, max_rows=300)
    assert not df.empty

    cats = set(df["category"].astype(str).unique().tolist())
    assert "milk" in cats
    assert "health" in cats
    assert "task" in cats
    assert "decision" in cats

    # Sorted descending by timestamp
    ts = pd.to_datetime(df["ts"], errors="coerce")
    assert ts.is_monotonic_decreasing


def test_timeline_build_df_truncates():
    from streamlit_app.components.timeline_v1 import build_timeline_df

    now = datetime(2026, 2, 8, 12, 0, 0)
    events = pd.DataFrame([{"date": (now - timedelta(days=i)).isoformat(), "category": "milk", "details": str(i)} for i in range(50)])
    df = build_timeline_df(events=events, tasks=[], decisions=[], max_rows=10)
    assert len(df) == 10
