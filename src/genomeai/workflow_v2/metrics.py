from __future__ import annotations

from dataclasses import dataclass

from core.domain import TASK_ACTIVE_STATUSES, TASK_CLOSED_STATUSES
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _parse_iso_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        ss = str(s).replace("Z", "+00:00")
        dt = datetime.fromisoformat(ss)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _pct(values: list[float], p: int) -> Optional[float]:
    if not values:
        return None
    if p <= 0:
        return float(min(values))
    if p >= 100:
        return float(max(values))
    xs = sorted(values)
    # linear interpolation
    k = (len(xs) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    if f == c:
        return float(xs[f])
    d0 = xs[f] * (c - k)
    d1 = xs[c] * (k - f)
    return float(d0 + d1)


def _is_closed(status: str) -> bool:
    return str(status or "").strip() in TASK_CLOSED_STATUSES


def _is_active(status: str) -> bool:
    return str(status or "").strip() in TASK_ACTIVE_STATUSES


def _is_overdue(task: dict[str, Any], *, now: Optional[datetime] = None) -> bool:
    try:
        if not _is_active(str(task.get("status") or "")):
            return False
        dt_due = _parse_iso_dt(task.get("due_at"))
        if not dt_due:
            return False
        nn = now or _utcnow()
        return dt_due < nn
    except Exception:
        return False


@dataclass
class MetricsConfig:
    window_days: int = 30
    percentiles: tuple[int, ...] = (50, 90)


def compute_tasks_metrics(
    tasks: Iterable[dict[str, Any]],
    *,
    now: Optional[datetime] = None,
    config: Optional[MetricsConfig] = None,
) -> dict[str, Any]:
    """Compute workflow execution metrics.

    Definitions:
      - lead_time_hours: closed_at - created_at (for closed tasks)
      - overdue_rate_active: overdue(active)/active_total
      - sla_on_time_rate_closed_window: on_time(closed with due_at)/total(closed with due_at)

    Input rows are plain dicts (e.g., from sqlite rows).

    Notes:
      - This function is pure (no DB access). Web cabinet/UI pass rows in.
      - Fields used when present: status, domain, assignee_team, stage, priority,
        created_at, closed_at, due_at.
    """

    cfg = config or MetricsConfig()
    nn = now or _utcnow()
    cutoff = nn - timedelta(days=int(cfg.window_days))

    # active
    active_total = 0
    active_overdue = 0

    # closed window
    closed_window_total = 0
    lead_times_h: list[float] = []

    # SLA adherence (closed tasks with due_at)
    sla_closed_due_total = 0
    sla_closed_on_time = 0
    sla_closed_late = 0

    def _key(v: Any, *, empty: str = "(none)") -> str:
        s = str(v or "").strip()
        return s if s else empty

    by_domain: dict[str, dict[str, Any]] = {}
    by_team: dict[str, dict[str, Any]] = {}
    by_stage: dict[str, dict[str, Any]] = {}
    by_priority: dict[str, dict[str, Any]] = {}

    sla_by_domain: dict[str, dict[str, int]] = {}
    sla_by_stage: dict[str, dict[str, int]] = {}

    for t in tasks:
        status = str(t.get("status") or "")
        domain = _key(t.get("domain"))
        team = _key(t.get("assignee_team"))
        stage = _key(t.get("stage"))
        try:
            pr_key = str(int(t.get("priority") or 0)) if t.get("priority") is not None else "(none)"
        except Exception:
            pr_key = _key(t.get("priority"))

        # active
        if _is_active(status):
            active_total += 1
            is_ov = _is_overdue(t, now=nn)
            if is_ov:
                active_overdue += 1

            by_domain.setdefault(domain, {"active": 0, "overdue": 0, "closed_window": 0, "lead_times_h": []})
            by_domain[domain]["active"] += 1
            if is_ov:
                by_domain[domain]["overdue"] += 1

            by_team.setdefault(team, {"active": 0, "overdue": 0})
            by_team[team]["active"] += 1
            if is_ov:
                by_team[team]["overdue"] += 1

            by_stage.setdefault(stage, {"active": 0, "overdue": 0, "closed_window": 0, "lead_times_h": []})
            by_stage[stage]["active"] += 1
            if is_ov:
                by_stage[stage]["overdue"] += 1

            by_priority.setdefault(pr_key, {"active": 0, "overdue": 0, "closed_window": 0, "lead_times_h": []})
            by_priority[pr_key]["active"] += 1
            if is_ov:
                by_priority[pr_key]["overdue"] += 1

        # closed window
        if _is_closed(status):
            dt_closed = _parse_iso_dt(t.get("closed_at"))
            if dt_closed and dt_closed >= cutoff:
                closed_window_total += 1
                dt_created = _parse_iso_dt(t.get("created_at"))
                if dt_created and dt_closed >= dt_created:
                    lt_h = (dt_closed - dt_created).total_seconds() / 3600.0
                    lead_times_h.append(float(lt_h))

                    by_domain.setdefault(domain, {"active": 0, "overdue": 0, "closed_window": 0, "lead_times_h": []})
                    by_domain[domain]["closed_window"] += 1
                    by_domain[domain]["lead_times_h"].append(float(lt_h))

                    by_stage.setdefault(stage, {"active": 0, "overdue": 0, "closed_window": 0, "lead_times_h": []})
                    by_stage[stage]["closed_window"] += 1
                    by_stage[stage]["lead_times_h"].append(float(lt_h))

                    by_priority.setdefault(pr_key, {"active": 0, "overdue": 0, "closed_window": 0, "lead_times_h": []})
                    by_priority[pr_key]["closed_window"] += 1
                    by_priority[pr_key]["lead_times_h"].append(float(lt_h))

                # SLA adherence for closed tasks with due
                dt_due = _parse_iso_dt(t.get("due_at"))
                if dt_due:
                    sla_closed_due_total += 1
                    is_on_time = dt_closed <= dt_due
                    if is_on_time:
                        sla_closed_on_time += 1
                    else:
                        sla_closed_late += 1

                    sla_by_domain.setdefault(domain, {"due_total": 0, "on_time": 0, "late": 0})
                    sla_by_domain[domain]["due_total"] += 1
                    sla_by_domain[domain]["on_time"] += 1 if is_on_time else 0
                    sla_by_domain[domain]["late"] += 0 if is_on_time else 1

                    sla_by_stage.setdefault(stage, {"due_total": 0, "on_time": 0, "late": 0})
                    sla_by_stage[stage]["due_total"] += 1
                    sla_by_stage[stage]["on_time"] += 1 if is_on_time else 0
                    sla_by_stage[stage]["late"] += 0 if is_on_time else 1

    overdue_rate = (active_overdue / active_total) if active_total > 0 else 0.0
    lead_time_mean = (sum(lead_times_h) / len(lead_times_h)) if lead_times_h else None

    lead_time_p: dict[str, Optional[float]] = {}
    for p in cfg.percentiles:
        lead_time_p[f"p{int(p)}"] = _pct(lead_times_h, int(p))

    # finalize breakdowns
    def _finalize_breakdown(map_: dict[str, dict[str, Any]], key_name: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for k, v in sorted(map_.items(), key=lambda kv: kv[0]):
            a = int(v.get("active") or 0)
            o = int(v.get("overdue") or 0)
            dom_lt = list(v.get("lead_times_h") or [])
            out.append(
                {
                    key_name: k,
                    "active": a,
                    "overdue": o,
                    "overdue_rate": (o / a) if a else 0.0,
                    "closed_window": int(v.get("closed_window") or 0),
                    "lead_time_p50_h": _pct(dom_lt, 50),
                }
            )
        return out

    by_domain_out = _finalize_breakdown(by_domain, "domain")
    by_stage_out = _finalize_breakdown(by_stage, "stage")
    by_priority_out = _finalize_breakdown(by_priority, "priority")

    by_team_out: list[dict[str, Any]] = []
    for team, v in sorted(by_team.items(), key=lambda kv: kv[0]):
        a = int(v.get("active") or 0)
        o = int(v.get("overdue") or 0)
        by_team_out.append({"assignee_team": team, "active": a, "overdue": o, "overdue_rate": (o / a) if a else 0.0})

    # add SLA to breakdowns where possible
    def _sla_rate(due_total: int, on_time: int) -> float:
        return (on_time / due_total) if due_total > 0 else 0.0

    sla_summary = {
        "closed_with_due_window": int(sla_closed_due_total),
        "closed_on_time_window": int(sla_closed_on_time),
        "closed_late_window": int(sla_closed_late),
        "on_time_rate_closed_window": float(_sla_rate(sla_closed_due_total, sla_closed_on_time)),
    }

    # attach per-domain SLA stats into by_domain_out
    dom_index = {d["domain"]: d for d in by_domain_out if "domain" in d}
    for dom, s in sla_by_domain.items():
        row = dom_index.get(dom)
        if not row:
            continue
        due_total = int(s.get("due_total") or 0)
        on_time = int(s.get("on_time") or 0)
        late = int(s.get("late") or 0)
        row["sla_due_total_closed_window"] = due_total
        row["sla_on_time_closed_window"] = on_time
        row["sla_late_closed_window"] = late
        row["sla_on_time_rate_closed_window"] = float(_sla_rate(due_total, on_time))

    stage_index = {d["stage"]: d for d in by_stage_out if "stage" in d}
    for stg, s in sla_by_stage.items():
        row = stage_index.get(stg)
        if not row:
            continue
        due_total = int(s.get("due_total") or 0)
        on_time = int(s.get("on_time") or 0)
        row["sla_due_total_closed_window"] = due_total
        row["sla_on_time_closed_window"] = on_time
        row["sla_on_time_rate_closed_window"] = float(_sla_rate(due_total, on_time))

    return {
        "window_days": int(cfg.window_days),
        "active_total": int(active_total),
        "active_overdue": int(active_overdue),
        "overdue_rate_active": float(overdue_rate),
        "closed_window_total": int(closed_window_total),
        "lead_time_mean_h": lead_time_mean,
        "lead_time_percentiles_h": lead_time_p,
        "sla_adherence": sla_summary,
        "by_domain": by_domain_out,
        "by_team": by_team_out,
        "by_stage": by_stage_out,
        "by_priority": by_priority_out,
    }


def rank_overdue_tasks(
    tasks: Iterable[dict[str, Any]],
    *,
    now: Optional[datetime] = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return top overdue active tasks.

    Output keeps selected original fields and adds:
      - overdue_hours
      - overdue_days

    This function is pure and can be used by web-cabinet and offline exports.
    """

    nn = now or _utcnow()
    items: list[dict[str, Any]] = []
    for t in tasks:
        try:
            if not _is_active(str(t.get("status") or "")):
                continue
            dt_due = _parse_iso_dt(t.get("due_at"))
            if not dt_due or dt_due >= nn:
                continue
            dh = (nn - dt_due).total_seconds() / 3600.0
            out = dict(t)
            out["overdue_hours"] = float(dh)
            out["overdue_days"] = float(dh) / 24.0
            items.append(out)
        except Exception:
            continue

    items.sort(key=lambda x: float(x.get("overdue_hours") or 0.0), reverse=True)
    return items[: int(limit or 20)]
