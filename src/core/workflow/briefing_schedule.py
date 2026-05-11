from __future__ import annotations

from typing import Any, Optional

DEFAULT_SCHEDULE: dict[str, Any] = {
    'periodicity': 'weekly',
    'time_of_day': '07:00',
    'auto_create_tasks': False,
}

ALLOWED_PERIODICITIES = {'daily', 'weekly', 'monthly'}


def _row_to_dict(row: Any, *, tenant_id: str) -> dict[str, Any]:
    if row is None:
        return {
            'tenant_id': tenant_id,
            **DEFAULT_SCHEDULE,
            'updated_at': None,
            'updated_by': None,
        }
    d = dict(row)
    updated_at = d.get('updated_at')
    return {
        'tenant_id': str(d.get('tenant_id') or tenant_id),
        'periodicity': str(d.get('periodicity') or DEFAULT_SCHEDULE['periodicity']),
        'time_of_day': str(d.get('time_of_day') or DEFAULT_SCHEDULE['time_of_day']),
        'auto_create_tasks': bool(d.get('auto_create_tasks')),
        'updated_at': updated_at.isoformat() if hasattr(updated_at, 'isoformat') else (str(updated_at) if updated_at else None),
        'updated_by': int(d['updated_by']) if d.get('updated_by') is not None else None,
    }


def get_briefing_schedule(conn: Any, *, tenant_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT tenant_id, periodicity, time_of_day, auto_create_tasks, updated_at, updated_by "
        "FROM briefing_schedule_v1 WHERE tenant_id=?",
        (tenant_id,),
    ).fetchone()
    return _row_to_dict(row, tenant_id=tenant_id)


def validate_schedule_input(*, periodicity: str, time_of_day: str) -> Optional[str]:
    if periodicity not in ALLOWED_PERIODICITIES:
        return f"periodicity_invalid (expected one of {sorted(ALLOWED_PERIODICITIES)})"
    if not (len(time_of_day) == 5 and time_of_day[2] == ':' and time_of_day[:2].isdigit() and time_of_day[3:].isdigit()):
        return "time_of_day_invalid (expected HH:MM)"
    hh, mm = int(time_of_day[:2]), int(time_of_day[3:])
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        return "time_of_day_out_of_range"
    return None


def upsert_briefing_schedule(
    conn: Any,
    *,
    tenant_id: str,
    periodicity: str,
    time_of_day: str,
    auto_create_tasks: bool,
    user_id: Optional[int] = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Returns (before, after) dicts for audit trail."""
    before = get_briefing_schedule(conn, tenant_id=tenant_id)
    conn.execute(
        """
        INSERT INTO briefing_schedule_v1 (tenant_id, periodicity, time_of_day, auto_create_tasks, updated_at, updated_by)
        VALUES (?, ?, ?, ?, NOW(), ?)
        ON CONFLICT (tenant_id) DO UPDATE SET
            periodicity=excluded.periodicity,
            time_of_day=excluded.time_of_day,
            auto_create_tasks=excluded.auto_create_tasks,
            updated_at=NOW(),
            updated_by=excluded.updated_by
        """,
        (tenant_id, periodicity, time_of_day, bool(auto_create_tasks), user_id),
    )
    after = get_briefing_schedule(conn, tenant_id=tenant_id)
    return before, after
